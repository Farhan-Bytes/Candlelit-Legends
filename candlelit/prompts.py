"""Prompts and JSON schemas for the three steps that call the open model: plan, select, write."""

from .sounds import LIBRARY

CATEGORIES = ["ghost", "cryptid", "cursed place", "water and shipwreck", "folklore", "historical mystery"]
LABELS = ["documented history", "local legend", "internet lore"]

# Step 1: plan searches

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "is_broad": {"type": "boolean"},
        "queries": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
    },
    "required": ["is_broad", "queries"],
}

PLAN_SYSTEM = """You plan web searches that find real, documented spooky legends tied to a place: ghosts, \
cryptids, cursed places, shipwrecks, folklore and historical mysteries.

Write 3 or 4 short search queries (under 10 words each) a person would type into a search engine.
- Make them specific: name the place, and use words like "haunted", "ghost story", "legend", "folklore".
- If the place is a province, state, region or country, set is_broad to true and aim the queries at \
specific towns, buildings, lighthouses, roads or lakes inside it, not the place as a whole.
- Never target sacred Indigenous beliefs or ceremonies.
Answer only with JSON."""

WIDEN_HINTS = {
    0: "Search the place itself.",
    1: "Earlier searches found too little. Widen to nearby towns and the surrounding county or district.",
    2: "Still too little. Widen to the whole surrounding region, province or state.",
}


def plan_user(place, story_type, widen, told_locations):
    lines = [f"Place: {place}",
             f"Story type wanted: {story_type if story_type != 'any' else 'any kind'}",
             WIDEN_HINTS[widen]]
    if told_locations:
        lines.append("Already told for this place, so look elsewhere: " + "; ".join(told_locations))
    return "\n".join(lines)


# Step 5: choose a legend and extract facts with source IDs

SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "location": {"type": "string"},
        "legend": {"type": "string"},
        "label": {"type": "string", "enum": LABELS},
        "category": {"type": "string", "enum": CATEGORIES},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["documented", "legend"]},
                },
                "required": ["text", "source", "kind"],
            },
        },
    },
    "required": ["found", "location", "legend", "label", "category", "facts"],
}

SELECT_SYSTEM = """You are a careful folklore researcher. From numbered web sources, choose ONE spooky legend \
and list its facts. Only use what the sources say.

Rules:
- Choose one specific site (a building, lighthouse, road, lake, cemetery, town) and name it in "location" \
as "Site, Town" or similar. For a big region, pick one site inside it.
- The site must be in, or near, the place asked for. Ignore sources about a different town that shares \
its name in another state, province or country.
- "legend" is the short name of the tale, e.g. "The ghost of keeper J.P. Radelmüller".
- List 4 to 8 facts. Each fact is one short sentence that comes from the source whose number you give.
  kind "documented": the source presents it as real history (a recorded death, fire, wreck, date, building).
  kind "legend": the source presents it as a story, sighting, rumour or belief.
- Prefer a legend that two or more sources mention, and cite them all.
- label: "documented history" if the sources describe real recorded events; "local legend" if they report \
a known local tale; "internet lore" if only blogs or forums mention it.
- Do not name private individuals who are not historical figures (e.g. a present-day witness).
- Skip legends from Indigenous traditions and sacred beliefs unless the source presents them as a public \
story told for that purpose.
- Skip any legend in the "already told" list.
- If no source contains a usable spooky legend, set found to false.
Answer only with JSON."""


def select_user(place, story_type, sources, told_legends, told_locations, words_per_source):
    parts = [f"Place asked for: {place}",
             f"Story type wanted: {story_type if story_type != 'any' else 'any kind'}"]
    if told_legends:
        parts.append("Already told (do not choose): " + "; ".join(told_legends[:30]))
    if told_locations:
        parts.append("Sites already used for this place (choose a different one if you can): "
                     + "; ".join(told_locations))
    parts.append("\nSources:")
    for i, s in enumerate(sources, 1):
        text = " ".join(s["text"].split()[:words_per_source])
        parts.append(f"\n[{i}] {s['title']}\nURL: {s['url']}\n{text}")
    return "\n".join(parts)


# Step 7: write the tale

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "story": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["title", "story", "summary"],
}

SPOOKINESS = {
    "cozy": "Cozy: gentle and atmospheric, more wonder than fear. Fine for anyone.",
    "campfire": "Campfire: a classic tale told around a fire, a few real chills, nothing graphic.",
    "unsettling": "Unsettling: deep, lingering dread that stays after the last line. Dread, not gore.",
}

TRUTH = {
    "close": ("Close to sources: use only the facts below for events, names, dates and places. You may add "
              "atmosphere (weather, light, sound, the narrator's feelings) but no new events, names or dates."),
    "dramatic": ("Dramatic embellishment: you may invent scenes, dialogue and details around the facts to make "
                 "it more dramatic, but never contradict them."),
}

NARRATOR_VOICE = {
    "old innkeeper": "an old innkeeper telling it across the bar to a late guest",
    "lighthouse keeper": "a lighthouse keeper writing it down during a long night watch",
    "skeptical historian": "a skeptical historian who keeps trying to explain it away, and can't quite",
    "the ghost itself": "the ghost itself, speaking in first person about its own death and what came after",
    "a child's diary": "a child's diary, in a child's words, dated entries",
    "a night-shift worker": "a night-shift worker who has seen things on the late shift there",
}

WRITE_SYSTEM = """You are a master teller of ghost stories in the tradition of M.R. James and old fireside \
tales. You retell real local legends as short, atmospheric stories. You never mock real victims: \
the eeriness belongs to the legend, and the dead are remembered with respect.
Answer only with JSON: a title (2-7 words, evocative, no colon), the story, and a two-sentence summary \
of the story's plot and framing."""


def sound_rules(max_cues, length):
    lines = [f"- {sid}: {caption}" for sid, (_, caption) in LIBRARY.items()]
    low = 3 if length == "short" else 5
    return (
        "Sound cues. Place tags like [[sound:bell]] between sentences, where that sound would happen.\n"
        "Allowed sound IDs (use no others):\n" + "\n".join(lines) + "\n"
        f"- Use {low} to {max_cues} cues in total.\n"
        "- Leave at least two full sentences between cues.\n"
        "- Never put a cue in the first sentence, so the silence lands first.\n"
        "- A tag goes right after the sentence's final punctuation, e.g. "
        "\"The lake was calm. [[sound:wind]] Then the bell rang.\""
    )


def write_user(*, place, location, legend, facts, style, length_words, spookiness, truth,
               max_cues, length, past_summaries, rewrite_note=None):
    facts_text = "\n".join(f"- ({f['kind']}) {f['text']}" for f in facts)
    parts = [
        f"Legend: {legend}",
        f"Where: {location} (the user asked about {place})",
        f"Facts (your only source of events, names and dates):\n{facts_text}",
        "",
        f"Narrator: {NARRATOR_VOICE.get(style['narrator'], style['narrator'])}.",
        f"Tone: {style['tone']}.",
        f"Opening: the story {style['opening_style']}.",
        f"Ending: end with {style['ending_style']}.",
        f"Length: about {length_words} words, in short paragraphs separated by blank lines.",
        f"Spookiness: {SPOOKINESS[spookiness]}",
        f"Truth level: {TRUTH[truth]}",
        "",
        sound_rules(max_cues, length),
    ]
    if past_summaries:
        parts += ["", "Recent stories already told. Do not echo their openings, endings, images or structure:"]
        parts += [f"- {s}" for s in past_summaries]
    if rewrite_note:
        parts += ["", f"IMPORTANT, this is a rewrite: {rewrite_note}"]
    return "\n".join(parts)
