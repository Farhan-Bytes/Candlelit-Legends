"""Story history and search cache, both in one local SQLite file."""

import array
import json
import math
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    place_input TEXT NOT NULL,
    location TEXT NOT NULL,
    legend_key TEXT NOT NULL,
    source_urls TEXT NOT NULL,
    story_type TEXT,
    narrator TEXT,
    tone TEXT,
    opening_style TEXT,
    ending_style TEXT,
    sounds_used TEXT,
    summary TEXT,
    embedding BLOB,
    title TEXT,
    story TEXT,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS search_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


def normalize(name):
    """Lowercase, strip accents and punctuation, collapse spaces: used for duplicate legend checks."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_STOPWORDS = {"the", "of", "a", "an", "and", "at", "in", "on", "s", "ghost", "legend", "haunted", "haunting", "story"}


def legend_tokens(key):
    """Distinctive words of a normalized name, with runs of initials joined ("j p" -> "jp")."""
    out, initials = [], ""
    for w in key.split():
        if len(w) == 1:
            initials += w
            continue
        if initials:
            out.append(initials)
            initials = ""
        out.append(w)
    if initials:
        out.append(initials)
    return set(out) - _STOPWORDS


def same_legend(key_a, key_b):
    """True when two normalized legend names refer to the same tale (exact, or most distinctive words shared)."""
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    a, b = legend_tokens(key_a), legend_tokens(key_b)
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.6


def cosine(u, v):
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0


def _pack(vec):
    return array.array("f", vec).tobytes() if vec else None


def _unpack(blob):
    if not blob:
        return None
    a = array.array("f")
    a.frombytes(blob)
    return a.tolist()


class History:
    def __init__(self, path):
        if str(path) != ":memory:":
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    # Stories

    def add(self, *, place_input, location, legend, source_urls, story_type, narrator, tone,
            opening_style, ending_style, sounds_used, summary, embedding, title, story, meta):
        with self._lock:
            cur = self._db.execute(
                """INSERT INTO stories (created_at, place_input, location, legend_key, source_urls,
                   story_type, narrator, tone, opening_style, ending_style, sounds_used, summary,
                   embedding, title, story, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), place_input, location,
                 normalize(legend), json.dumps(source_urls), story_type, narrator, tone,
                 opening_style, ending_style, json.dumps(sounds_used), summary, _pack(embedding),
                 title, story, json.dumps(meta)))
            self._db.commit()
            return cur.lastrowid

    def recent(self, n=None):
        """Past stories, newest first."""
        sql = "SELECT * FROM stories ORDER BY id DESC" + (" LIMIT ?" if n else "")
        with self._lock:
            rows = self._db.execute(sql, (n,) if n else ()).fetchall()
        return [self._row(r) for r in rows]

    def get(self, story_id):
        with self._lock:
            r = self._db.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        return self._row(r) if r else None

    def told_urls(self):
        urls = set()
        for s in self.recent():
            urls.update(s["source_urls"])
        return urls

    def told_legends(self):
        return [s["legend_key"] for s in self.recent()]

    def is_told(self, legend):
        key = normalize(legend)
        return any(same_legend(key, k) for k in self.told_legends())

    def most_similar(self, vec):
        """Highest cosine similarity to any past story, with that story's row."""
        best, best_row = 0.0, None
        for s in self.recent():
            if s["embedding"]:
                sim = cosine(vec, s["embedding"])
                if sim > best:
                    best, best_row = sim, s
        return best, best_row

    def clear(self):
        with self._lock:
            self._db.execute("DELETE FROM stories")
            self._db.execute("DELETE FROM search_cache")
            self._db.commit()

    @staticmethod
    def _row(r):
        d = dict(r)
        d["source_urls"] = json.loads(d["source_urls"] or "[]")
        d["sounds_used"] = json.loads(d["sounds_used"] or "[]")
        d["meta"] = json.loads(d["meta"] or "{}")
        d["embedding"] = _unpack(d["embedding"])
        return d

    # Search cache

    def cache_get(self, key, max_age_hours):
        with self._lock:
            r = self._db.execute("SELECT value, fetched_at FROM search_cache WHERE key = ?", (key,)).fetchone()
        if r and time.time() - r["fetched_at"] < max_age_hours * 3600:
            return json.loads(r["value"])
        return None

    def cache_put(self, key, value):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO search_cache (key, value, fetched_at) VALUES (?, ?, ?)",
                             (key, json.dumps(value), time.time()))
            self._db.commit()
