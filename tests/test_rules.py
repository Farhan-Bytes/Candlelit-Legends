"""The plain-code rules the model can't override: sound cues, style rotation, duplicate legends."""

import random

from candlelit import style
from candlelit.history import History, cosine, normalize, same_legend
from candlelit.sounds import ambient_for, clean_cues, strip_cues


def test_unknown_sound_ids_are_dropped():
    text, kept = clean_cues("One. Two. [[sound:bell]] Three. Four. [[sound:trumpet]] Five.", 6)
    assert kept == ["bell"]
    assert "trumpet" not in text


def test_no_cue_in_first_sentence():
    text, kept = clean_cues("[[sound:wind]] The lake was calm. [[sound:bell]] Then it rang.", 6)
    assert kept == ["bell"]
    assert text.startswith("The lake was calm.")


def test_two_sentences_between_cues():
    story = "A. B. [[sound:wind]] C. [[sound:bell]] D. E. [[sound:creak]] F."
    _, kept = clean_cues(story, 6)
    assert kept == ["wind", "creak"]


def test_cue_cap_and_malformed_tags():
    story = " ".join(f"S{i}. S{i}b. [[ Sound: Knock ]]" for i in range(10))
    text, kept = clean_cues(story, 3)
    assert kept == ["knock"] * 3
    assert text.count("[[sound:knock]]") == 3


def test_strip_cues():
    assert strip_cues("Calm. [[sound:wind]] Then.") == "Calm. Then."


def test_ambient_by_story_type():
    assert ambient_for("water and shipwreck") == "water"
    assert ambient_for("cursed place") == "wind"
    assert ambient_for("ghost") == "fire"


def test_rotation_avoids_recent_values():
    used = {"narrator": 5, "tone": 4, "opening_style": 4, "ending_style": 3}
    recent = [{k: style.POOLS[k][i] if i < n else None for k, n in used.items()} for i in range(5)]
    picked = style.rotate(recent, rng=random.Random(1))
    assert picked["narrator"] == style.POOLS["narrator"][5]
    assert picked["tone"] == style.POOLS["tone"][4]
    assert picked["opening_style"] == style.POOLS["opening_style"][4]
    assert picked["ending_style"] == style.POOLS["ending_style"][3]


def test_rotation_respects_user_narrator():
    recent = [{"narrator": "lighthouse keeper"}]
    assert style.rotate(recent, narrator="lighthouse keeper")["narrator"] == "lighthouse keeper"


def test_legend_matching():
    assert normalize("The Ghost of J.P. Radelmüller!") == "the ghost of j p radelmuller"
    assert same_legend(normalize("Ghost of keeper J.P. Radelmüller"), normalize("The ghost of J.P. Radelmuller, keeper"))
    assert not same_legend(normalize("The Lady in Grey"), normalize("The Drowned Sailor"))


def test_history_roundtrip_and_similarity():
    h = History(":memory:")
    sid = h.add(place_input="Toronto", location="Gibraltar Point Lighthouse, Toronto",
                legend="Ghost of J.P. Radelmüller", source_urls=["https://a.example"], story_type="ghost",
                narrator="lighthouse keeper", tone="slow dread", opening_style="starts with a date",
                ending_style="quiet twist", sounds_used=["bell"], summary="A keeper vanishes.",
                embedding=[1.0, 0.0, 0.0], title="The Keeper", story="Text", meta={"legend": "x"})
    assert h.get(sid)["sounds_used"] == ["bell"]
    assert h.told_urls() == {"https://a.example"}
    assert h.is_told("The ghost of JP Radelmuller")
    sim, row = h.most_similar([0.9, 0.1, 0.0])
    assert row["id"] == sid and sim > 0.99
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
    h.clear()
    assert h.recent() == []


def test_corroborating_pages_must_name_the_legend():
    from candlelit.pipeline import mentions
    assert mentions("In 1692 the witch trials gripped Salem Town.", "The Salem Witch Trials")
    assert not mentions("Salem's harbour and its customs house.", "The Salem Witch Trials")


def test_search_cache_expiry():
    h = History(":memory:")
    h.cache_put("q:x", [1, 2])
    assert h.cache_get("q:x", 24) == [1, 2]
    assert h.cache_get("q:x", 0) is None
