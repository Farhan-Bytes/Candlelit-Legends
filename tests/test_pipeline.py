"""The whole pipeline with a fake model and fake search, checking the two loops and the event stream."""

from candlelit import prompts
from candlelit.history import History
from candlelit.pipeline import NoLegendFound, Pipeline, StoryRequest

PAGE = ("The lighthouse keeper vanished in 1815 and his ghost is said to haunt the stairs. " * 20).strip()


class FakeSearcher:
    def __init__(self, pages_by_round):
        self.pages_by_round = pages_by_round
        self.round = -1

    def search(self, query):
        return [{"title": f"Result {i}", "url": f"https://site{i}.example/{self.round}", "snippet": ""}
                for i in range(3)]

    def extract_many(self, results):
        self.round += 1
        n = self.pages_by_round[min(self.round, len(self.pages_by_round) - 1)]
        return [{**r, "text": PAGE, "words": len(PAGE.split())} for r in results[:n]]


class FakeLLM:
    model = "fake:7b"

    def __init__(self, legends=("The Keeper's Ghost",), stories=None, embeddings=None):
        self.legends = list(legends)
        self.stories = list(stories or ["The fog came in. It was cold. [[sound:bell]] Then a step. And another. [[sound:footsteps]] Silence."])
        self.embeddings = list(embeddings or [[1.0, 0.0]])
        self.calls = []

    def chat_json(self, system, user, schema, temperature):
        self.calls.append(schema)
        if schema is prompts.PLAN_SCHEMA:
            return {"is_broad": True, "queries": ["haunted lighthouse", "ghost story"]}
        if schema is prompts.SELECT_SCHEMA:
            legend = self.legends.pop(0) if len(self.legends) > 1 else self.legends[0]
            return {"found": True, "location": "Gibraltar Point Lighthouse, Toronto", "legend": legend,
                    "label": "local legend", "category": "water and shipwreck",
                    "facts": [{"text": "The keeper vanished in 1815.", "source": 1, "kind": "documented"},
                              {"text": "Footsteps are heard on the stairs.", "source": 2, "kind": "legend"},
                              {"text": "Bogus citation.", "source": 99, "kind": "legend"}]}
        story = self.stories.pop(0) if len(self.stories) > 1 else self.stories[0]
        return {"title": "The Keeper", "story": story, "summary": "A keeper vanishes. His steps remain."}

    def embed(self, text):
        return self.embeddings.pop(0) if len(self.embeddings) > 1 else self.embeddings[0]


def run(pipeline, **kw):
    return list(pipeline.run(StoryRequest(place="Ontario, Canada", **kw)))


def test_events_and_saved_history():
    h = History(":memory:")
    events = run(Pipeline(FakeLLM(), FakeSearcher([3]), h))
    kinds = [e for e, _ in events]
    assert kinds[-2:] == ["story", "meta"] and set(kinds[:-2]) == {"status"}
    assert [d["stage"] for e, d in events if e == "status"][:5] == [0, 1, 2, 3, 3]

    meta = events[-1][1]
    assert meta["location"] == "Gibraltar Point Lighthouse, Toronto"
    assert meta["ambient"] == "water"
    assert meta["sounds"] == ["bell", "footsteps"]
    assert all(f["source"] in (1, 2) for f in meta["facts"])  # the bogus source id was dropped
    assert len(meta["sources"]) == 3            # page 3 names the legend too, so it corroborates
    assert h.recent()[0]["title"] == "The Keeper"


def test_thin_sources_widen_and_keep_earlier_pages():
    # One page per round: the wider round adds to the first instead of replacing it.
    events = run(Pipeline(FakeLLM(), FakeSearcher([1, 1, 1]), History(":memory:")))
    texts = [d["text"] for e, d in events if e == "status" and d["stage"] == 0]
    assert len(texts) == 2 and "nearby towns" in texts[1]
    meta = events[-1][1]
    assert meta["widened"] is True
    assert {s["url"] for s in meta["sources"]} == {"https://site0.example/-1", "https://site0.example/0"}


def test_no_sources_at_all_raises():
    try:
        run(Pipeline(FakeLLM(), FakeSearcher([0]), History(":memory:")))
    except NoLegendFound:
        return
    raise AssertionError("expected NoLegendFound")


def test_told_legend_is_rejected_in_code():
    h = History(":memory:")
    run(Pipeline(FakeLLM(), FakeSearcher([3]), h))
    llm = FakeLLM(legends=["The Keeper's Ghost", "The Drowned Bride of the Bay"], embeddings=[[0.0, 1.0]])
    events = run(Pipeline(llm, FakeSearcher([3]), h))
    assert events[-1][1]["legend"] == "The Drowned Bride of the Bay"


def test_similar_story_is_rewritten_then_best_kept():
    h = History(":memory:")
    run(Pipeline(FakeLLM(), FakeSearcher([3]), h))
    llm = FakeLLM(legends=["Another Tale Entirely"], stories=["A. B. Too similar.", "C. D. Fresh one."],
                  embeddings=[[1.0, 0.0], [0.0, 1.0]])
    events = run(Pipeline(llm, FakeSearcher([3]), h))
    assert sum(1 for s in llm.calls if s is prompts.WRITE_SCHEMA) == 2
    assert "Fresh one." in events[-2][1]["text"]


def test_style_rotates_between_tales():
    h = History(":memory:")
    first = run(Pipeline(FakeLLM(), FakeSearcher([3]), h))[-1][1]
    second = run(Pipeline(FakeLLM(legends=["A Different Legend"], embeddings=[[0.0, 1.0]]),
                          FakeSearcher([3]), h))[-1][1]
    for k in ("narrator", "tone", "opening_style", "ending_style"):
        assert first[k] != second[k]
