"""Web search (DuckDuckGo, Wikipedia as fallback) and main-text extraction for result pages.

This is the only part of the app that sends anything off the laptop.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx

from . import config

log = logging.getLogger(__name__)

# Wikimedia rejects agents without a contact URL and library name.
USER_AGENT = f"CandlelitLegends/1.0 ({config.CONTACT_URL}; local storytelling app) httpx/{httpx.__version__}"

# Pages that rarely yield readable text about a legend.
SKIP_DOMAINS = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com",
                "pinterest.", "x.com", "twitter.com", "amazon.", "tripadvisor.", "yelp.")


def _skip(url):
    host = urlparse(url).netloc.lower()
    return any(d in host for d in SKIP_DOMAINS)


class Searcher:
    def __init__(self, history, results_per_query=config.RESULTS_PER_QUERY):
        self.history = history
        self.results_per_query = results_per_query
        self._http = httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def search(self, query):
        """Return [{title, url, snippet}] for a query, cached per query for 24 hours."""
        key = "q:" + query.lower().strip()
        cached = self.history.cache_get(key, config.SEARCH_CACHE_HOURS)
        if cached is not None:
            return cached
        results = self._ddg(query)
        if not results:
            results = self._wikipedia(query)
        results = [r for r in results if r["url"].startswith("http") and not _skip(r["url"])]
        if results:
            self.history.cache_put(key, results)
        return results

    def _ddg(self, query):
        try:
            from ddgs import DDGS
            from ddgs.exceptions import RatelimitException, TimeoutException
        except ImportError:
            log.warning("ddgs is not installed; using Wikipedia only")
            return []
        for attempt in range(3):
            try:
                hits = DDGS().text(query, max_results=self.results_per_query,
                                   backend=config.SEARCH_BACKEND) or []
                return [{"title": h.get("title", ""), "url": h.get("href", ""), "snippet": h.get("body", "")}
                        for h in hits]
            except (RatelimitException, TimeoutException) as e:
                # Only rate limits and timeouts are worth waiting out.
                log.warning("DuckDuckGo search failed (attempt %d): %s", attempt + 1, e)
                time.sleep(1.5 * 2 ** attempt)
            except Exception as e:  # "No results found" and friends: retrying won't help
                log.info("DuckDuckGo found nothing for %r: %s", query, e)
                return []
        return []

    def _wikipedia(self, query):
        try:
            r = self._http.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "list": "search", "srsearch": query,
                "srlimit": self.results_per_query, "format": "json"})
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("Wikipedia search failed: %s", e)
            return []
        out = []
        for h in r.json().get("query", {}).get("search", []):
            title = h["title"]
            out.append({"title": title,
                        "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                        "snippet": _strip_tags(h.get("snippet", ""))})
        return out

    def extract_many(self, results):
        """Fetch pages in parallel and attach clean main text (capped) to each result."""
        with ThreadPoolExecutor(max_workers=6) as pool:
            texts = list(pool.map(self.extract, [r["url"] for r in results]))
        out = []
        for r, text in zip(results, texts):
            text = text or r.get("snippet", "")
            out.append({**r, "text": text, "words": len(text.split())})
        return out

    def extract(self, url):
        key = "p:" + url
        cached = self.history.cache_get(key, config.SEARCH_CACHE_HOURS)
        if cached is not None:
            return cached
        try:
            import trafilatura
        except ImportError as e:
            raise RuntimeError(f"trafilatura cannot load ({e}). Run: pip install -r requirements.txt") from e
        try:
            r = self._http.get(url)
            r.raise_for_status()
            text = trafilatura.extract(r.text, url=url, include_comments=False, include_tables=False) or ""
        except Exception as e:  # network errors, bad encodings, parser failures
            log.info("Could not read %s: %s", url, e)
            text = ""
        words = text.split()
        if len(words) > config.PAGE_WORD_CAP:
            text = " ".join(words[:config.PAGE_WORD_CAP])
        if text:  # a failed fetch may be transient, so only successes are cached
            self.history.cache_put(key, text)
        return text


def _strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)
