"""The story pipeline: ten steps, two loops.

 1. Plan searches            (model, JSON, temp 0.2)
 2. Search DuckDuckGo        (code)
 3. Skip legends already told (code)
 4. Read pages               (trafilatura)
 5. Choose legend + facts    (model, JSON, temp 0.2)   -- loop A: fewer than 2 sources -> widen, back to 1
 6. Rotate style             (code)
 7. Write the tale           (model, JSON, temp 0.9)
 8. Validate sound cues      (code)
 9. Similarity check         (local embeddings)        -- loop B: too close to a past tale -> back to 7
10. Save to history          (SQLite)

`Pipeline.run` is a generator of (event, data) pairs: several "status", then "story", then "meta".
"""

import logging
import random
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from . import config, prompts, sounds, style
from .history import legend_tokens, normalize, same_legend

log = logging.getLogger(__name__)

STAGES = [
    "Searching the old records…",
    "Setting aside tales already told…",
    "Reading what the townsfolk wrote…",
    "Choosing a legend and checking its facts…",
    "Dipping the quill…",
]
WIDEN_LINES = {
    1: "The records are thin here. Asking in the nearby towns…",
    2: "Still too quiet. Listening across the whole region…",
}
SPOOKY_WORDS = re.compile(
    r"\b(ghost|haunt\w*|legend\w*|spirit|apparition|phantom|curse\w*|monster|creature|sighting\w*|"
    r"folklore|mystery|mysterious|shipwreck\w*|wreck|vanish\w*|disappear\w*|murder\w*|spectre|specter|"
    r"paranormal|eerie|witch\w*|tale)\b", re.I)
FORUM_HOSTS = ("reddit.", "quora.", "blogspot.", "wordpress.", "medium.com", "tumblr.", "forum", "fandom.")


class StoryRequest(BaseModel):
    place: str = Field(min_length=1, max_length=120)
    story_type: Literal["any", "ghost", "cryptid", "cursed place", "water and shipwreck",
                        "folklore", "historical mystery"] = "any"
    spookiness: Literal["cozy", "campfire", "unsettling"] = "campfire"
    narrator: Literal["auto", "old innkeeper", "lighthouse keeper", "skeptical historian",
                      "the ghost itself"] = "auto"
    length: Literal["short", "long"] = "short"
    truth_level: Literal["close", "dramatic"] = "close"


class NoLegendFound(Exception):
    pass


def status(stage, text=None, **extra):
    return "status", {"stage": stage, "text": text or STAGES[stage], **extra}


def relevance(page):
    return len(SPOOKY_WORDS.findall(page["text"]))


def mentions(text, legend):
    """True when a page names the legend: at least two thirds of its distinctive words appear."""
    words = legend_tokens(normalize(legend))
    if not words:
        return False
    present = set(normalize(text).split())
    return sum(w in present for w in words) >= max(1, round(len(words) * 2 / 3))


class Pipeline:
    def __init__(self, llm, searcher, history, rng=None):
        self.llm = llm
        self.searcher = searcher
        self.history = history
        self.rng = rng or random.Random()

    def run(self, req: StoryRequest):
        place = req.place.strip()
        told_here = [s for s in self.history.recent() if normalize(s["place_input"]) == normalize(place)]
        told_locations = list(dict.fromkeys(s["location"] for s in told_here))[:10]
        avoid = [s["meta"].get("legend") or s["legend_key"] for s in self.history.recent(30)]

        # Steps 1-5, with loop A: widen the search when sources are thin. Each wider round adds
        # to the pages already read rather than starting over.
        selection, widened = None, 0
        pool = {}
        for widen in range(config.MAX_WIDEN + 1):
            widened = widen
            for page in (yield from self._gather(req, place, widen, told_locations)):
                pool.setdefault(page["url"], page)
            sources = sorted(pool.values(), key=relevance, reverse=True)[:config.PROMPT_SOURCES]
            if len(sources) < config.MIN_SOURCES and widen < config.MAX_WIDEN:
                continue
            if not sources:
                continue
            yield status(3)
            selection = self._select(req, place, sources, avoid, told_locations)
            if selection is not None:
                break
        if selection is None:
            raise NoLegendFound(f"No usable legend found for {place}.")
        yield status(3, "Choosing a legend and checking its facts…", location=selection["location"])

        # Step 6: style rotation in code.
        recent = self.history.recent(config.STYLE_WINDOW)
        chosen = None if req.narrator == "auto" else req.narrator
        picked = style.rotate(recent, narrator=chosen, rng=self.rng)

        # Steps 7-9, with loop B: rewrite when the tale is too close to a past one.
        yield status(4)
        best, note = None, None
        for attempt in range(config.MAX_REWRITES + 1):
            draft = self._write(req, place, selection, picked, recent, note)
            vec = self.llm.embed(sounds.strip_cues(draft["story"]))
            sim, similar = self.history.most_similar(vec) if vec else (0.0, None)
            draft.update(embedding=vec, similarity=sim)
            if best is None or sim < best["similarity"]:
                best = draft
            if sim <= config.SIMILARITY_THRESHOLD:
                break
            log.info("Draft %d too similar (%.3f) to '%s'; rewriting", attempt + 1, sim, similar["title"])
            note = (f"the last draft read too much like an earlier tale, \"{similar['title']}\" "
                    f"({similar['summary']}). Use a different opening scene, different images, a different "
                    f"structure and a different ending.")
            if attempt < config.MAX_REWRITES:
                yield status(4, "The quill hesitates… that tale sounds familiar. Starting afresh…")

        # Step 10: save and send.
        ambient = sounds.ambient_for(selection["category"])
        meta = {
            "title": best["title"],
            "place": place,
            "location": selection["location"],
            "legend": selection["legend"],
            "label": selection["label"],
            "category": selection["category"],
            "facts": selection["facts"],
            "sources": [{"title": s["title"], "url": s["url"]} for s in selection["sources"]],
            "narrator": picked["narrator"],
            "tone": picked["tone"],
            "opening_style": picked["opening_style"],
            "ending_style": picked["ending_style"],
            "sounds": best["sounds"],
            "ambient": ambient,
            "length": req.length,
            "spookiness": req.spookiness,
            "embellished": req.truth_level == "dramatic",
            "widened": widened > 0,
            "model": getattr(self.llm, "model", "local model"),
        }
        meta["id"] = self.history.add(
            place_input=place, location=selection["location"], legend=selection["legend"],
            source_urls=[s["url"] for s in selection["sources"]], story_type=selection["category"],
            narrator=picked["narrator"], tone=picked["tone"], opening_style=picked["opening_style"],
            ending_style=picked["ending_style"], sounds_used=best["sounds"], summary=best["summary"],
            embedding=best["embedding"], title=best["title"], story=best["story"], meta=meta)
        yield "story", {"title": best["title"], "text": best["story"]}
        yield "meta", meta

    # Steps 1-4

    def _gather(self, req, place, widen, told_locations):
        yield status(0, WIDEN_LINES.get(widen))
        plan = self.llm.chat_json(prompts.PLAN_SYSTEM,
                                  prompts.plan_user(place, req.story_type, widen, told_locations),
                                  prompts.PLAN_SCHEMA, config.PLAN_TEMPERATURE)
        queries = [q.strip() for q in plan.get("queries", []) if q.strip()][:4]
        if not queries:
            queries = [f"{place} haunted legend ghost story"]
        log.info("Search plan (widen %d): %s", widen, queries)
        results, seen = [], set()
        for q in queries:
            for r in self.searcher.search(q):
                if r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)

        # Step 3: drop anything we've already told, before the model sees it.
        yield status(1)
        told_urls = self.history.told_urls()
        told_keys = self.history.told_legends()
        fresh = []
        for r in results:
            if r["url"] in told_urls:
                continue
            title_key = normalize(r["title"])
            if any(k and (k in title_key or same_legend(k, title_key)) for k in told_keys):
                continue
            fresh.append(r)

        yield status(2)
        pages = self.searcher.extract_many(fresh[:config.MAX_PAGES])
        return [p for p in pages if p["words"] >= config.MIN_SOURCE_WORDS and relevance(p) > 0]

    # Step 5

    def _select(self, req, place, sources, avoid, told_locations):
        avoid = list(avoid)
        for _ in range(2):
            raw = self.llm.chat_json(
                prompts.SELECT_SYSTEM,
                prompts.select_user(place, req.story_type, sources, avoid, told_locations,
                                    config.PROMPT_WORDS_PER_SOURCE),
                prompts.SELECT_SCHEMA, config.PLAN_TEMPERATURE)
            if not raw.get("found") or not raw.get("legend"):
                return None
            # The model can't be trusted to skip told legends, so code checks again.
            if self.history.is_told(raw["legend"]):
                log.info("Model picked an already-told legend (%s); asking again", raw["legend"])
                avoid.append(raw["legend"])
                continue
            facts = [f for f in raw.get("facts", [])
                     if isinstance(f.get("source"), int) and 1 <= f["source"] <= len(sources) and f.get("text")]
            if not facts:
                return None
            used_ids = sorted({f["source"] for f in facts})
            # Models often cite one page for everything; any other page that names the same
            # legend corroborates it, so list it too.
            used_ids += [i for i, s in enumerate(sources, 1)
                         if i not in used_ids and mentions(s["text"], raw["legend"])]
            used = [sources[i - 1] for i in used_ids]
            renumber = {old: new for new, old in enumerate(used_ids, 1)}
            label = raw.get("label") if raw.get("label") in prompts.LABELS else "local legend"
            if all(any(h in urlparse(s["url"]).netloc for h in FORUM_HOSTS) for s in used):
                label = "internet lore"
            return {
                "location": raw.get("location") or place,
                "legend": raw["legend"],
                "label": label,
                "category": raw.get("category") if raw.get("category") in prompts.CATEGORIES else "ghost",
                "facts": [{"text": f["text"], "kind": f.get("kind", "legend"), "source": renumber[f["source"]]}
                          for f in facts],
                "sources": used,
            }
        return None

    # Steps 7-8

    def _write(self, req, place, selection, picked, recent, rewrite_note):
        max_cues = config.MAX_CUES[req.length]
        raw = self.llm.chat_json(
            prompts.WRITE_SYSTEM,
            prompts.write_user(
                place=place, location=selection["location"], legend=selection["legend"],
                facts=selection["facts"], style=picked, length_words=config.LENGTHS[req.length],
                spookiness=req.spookiness, truth=req.truth_level, max_cues=max_cues, length=req.length,
                past_summaries=[s["summary"] for s in recent if s.get("summary")],
                rewrite_note=rewrite_note),
            prompts.WRITE_SCHEMA, config.WRITE_TEMPERATURE)
        text, kept = sounds.clean_cues(raw.get("story", ""), max_cues)
        if not text:
            raise RuntimeError("The model returned an empty story.")
        title = (raw.get("title") or selection["legend"]).strip().strip('"')
        return {"title": title, "story": text, "summary": raw.get("summary", "").strip(), "sounds": kept}
