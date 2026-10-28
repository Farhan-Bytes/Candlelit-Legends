"""Style rotation: code picks a narrator, tone, opening and ending the recent stories did not use."""

import random

from . import config

POOLS = {
    "narrator": ["old innkeeper", "lighthouse keeper", "skeptical historian", "the ghost itself",
                 "a child's diary", "a night-shift worker"],
    "tone": ["slow dread", "wistful and sad", "folksy and warm", "cold and clinical", "frantic"],
    "opening_style": ["starts with a date", "starts with a sound", "starts mid-conversation",
                      "starts with a warning", "starts with a place description"],
    "ending_style": ["unresolved question", "quiet twist", "direct address to the reader",
                     "a detail that doesn't add up"],
}


def pick(dimension, recent_values, chosen=None, rng=random):
    """Use the user's choice if given; otherwise a value none of the last few stories used.

    The window shrinks for small pools so there is always a fresh option; ties fall back to
    the least recently used value.
    """
    if chosen:
        return chosen
    pool = POOLS[dimension]
    window = min(config.STYLE_WINDOW, len(pool) - 1)
    recent = [v for v in recent_values if v][:window]
    fresh = [v for v in pool if v not in recent]
    if fresh:
        return rng.choice(fresh)
    # Every value appeared recently: take the one used longest ago.
    return max(pool, key=lambda v: recent.index(v) if v in recent else len(recent))


def rotate(recent_stories, narrator=None, rng=random):
    """recent_stories is newest first. `narrator` is the user's pick, or None for auto."""
    def history_of(field):
        return [s.get(field) for s in recent_stories]

    return {
        "narrator": pick("narrator", history_of("narrator"), narrator, rng),
        "tone": pick("tone", history_of("tone"), None, rng),
        "opening_style": pick("opening_style", history_of("opening_style"), None, rng),
        "ending_style": pick("ending_style", history_of("ending_style"), None, rng),
    }
