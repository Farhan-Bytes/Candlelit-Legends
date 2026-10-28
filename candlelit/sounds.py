"""The sound library and the code that keeps the model's sound tags honest."""

import re

# id -> (kind, caption shown in the text so the story works with sound off)
LIBRARY = {
    "fire": ("ambient", "the hearth crackles"),
    "wind": ("ambient", "wind at the shutters"),
    "water": ("ambient", "waves against the dock"),
    "creak": ("oneshot", "a floorboard creaks"),
    "door": ("oneshot", "a heavy door closes"),
    "footsteps": ("oneshot", "slow footsteps"),
    "bell": ("oneshot", "a bell tolls"),
    "whisper": ("oneshot", "a faint whisper"),
    "knock": ("oneshot", "three knocks"),
    "crow": ("oneshot", "a crow calls"),
    "chains": ("oneshot", "chains rattle"),
    "heartbeat": ("oneshot", "a slow heartbeat"),
}
SOUND_IDS = list(LIBRARY)

# Accepts slightly malformed tags ("[[ Sound: Bell ]]", "[sound:bell]") so they can be normalised or dropped.
TAG_RE = re.compile(r"\[\[?\s*sound\s*:\s*([a-z_-]+)\s*\]?\]", re.I)
# A sentence ends at . ! ? or … (optionally followed by closing quotes/brackets) before whitespace or the end.
SENTENCE_END_RE = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s|$)")


def ambient_for(category):
    """One quiet loop under the whole story, chosen by story type."""
    c = (category or "").lower()
    if "water" in c or "shipwreck" in c:
        return "water"
    if "cursed" in c:
        return "wind"
    return "fire"


def clean_cues(text, max_cues):
    """Enforce the cue rules in code, whatever the model did.

    Drops unknown sound IDs, any cue inside the first sentence, cues with fewer than two
    sentences since the previous kept cue, and cues beyond `max_cues`. Returns the cleaned
    text and the list of sound IDs kept, in order.
    """
    out, kept = [], []
    last = 0
    sentences_since_cue = 0
    first_cue = True
    for m in TAG_RE.finditer(text):
        before = text[last:m.start()]
        out.append(before)
        sentences_since_cue += len(SENTENCE_END_RE.findall(before.rstrip() + " "))
        last = m.end()
        sid = m.group(1).lower()
        needed = 1 if first_cue else 2
        if sid in LIBRARY and sentences_since_cue >= needed and len(kept) < max_cues:
            out.append(f"[[sound:{sid}]]")
            kept.append(sid)
            sentences_since_cue = 0
            first_cue = False
    out.append(text[last:])
    cleaned = "".join(out)
    # Tidy spaces left behind by dropped tags.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return cleaned.strip(), kept


def strip_cues(text):
    return re.sub(r"\s{2,}", " ", TAG_RE.sub(" ", text)).strip()
