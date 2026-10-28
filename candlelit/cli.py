"""Terminal version: python -m candlelit.cli "Kingston, ON" [--type ghost] [--length long] ..."""

import argparse
import logging
import sys

from . import config
from .history import History
from .llm import OllamaClient
from .pipeline import NoLegendFound, Pipeline, StoryRequest
from .search import Searcher
from .sounds import LIBRARY, TAG_RE


def main(argv=None):
    p = argparse.ArgumentParser(description="Tell a real local legend from the terminal.")
    p.add_argument("place")
    p.add_argument("--type", dest="story_type", default="any")
    p.add_argument("--spookiness", default="campfire")
    p.add_argument("--narrator", default="auto")
    p.add_argument("--length", default="short")
    p.add_argument("--truth", dest="truth_level", default="close")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    req = StoryRequest(**{k: v for k, v in vars(args).items() if k != "verbose"})
    history = History(config.DB_PATH)
    pipeline = Pipeline(OllamaClient(), Searcher(history), history)
    try:
        for event, data in pipeline.run(req):
            if event == "status":
                print(f"  … {data['text']}" + (f"  [{data['location']}]" if data.get("location") else ""))
            elif event == "story":
                text = TAG_RE.sub(lambda m: f"({LIBRARY.get(m.group(1).lower(), ('', m.group(1)))[1]})",
                                  data["text"])
                print(f"\n{data['title'].upper()}\n\n{text}\n")
            elif event == "meta":
                print(f"{data['location']} · {data['label']} · told by {data['narrator']}, {data['tone']}")
                for i, s in enumerate(data["sources"], 1):
                    print(f"  [{i}] {s['title']}  {s['url']}")
    except NoLegendFound as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
