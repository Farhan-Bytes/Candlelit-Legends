# Candlelit Legends

<img width="2000" height="840" alt="image" src="https://github.com/user-attachments/assets/442b5b7d-bc39-47a7-82bc-78b6c5576900" />

Name a place and get a real, sourced local legend, retold as a short spooky tale on a parchment scroll, with sound cues timed to the text. Everything runs on your laptop through Ollama. The only request that leaves the machine is the web search (DuckDuckGo, with Wikipedia as a fallback).

See [Candlelit Legends Design Doc.md](Candlelit%20Legends%20Design%20Doc.md) for the full design.

## Run it

```bash
# 1. Python deps (3.10+)
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. Models
ollama serve                      # if it isn't already running
ollama pull gemma4:e4b            # story model (or set CL_MODEL to another)
ollama pull nomic-embed-text      # optional: turns on the similarity check

# 3. Start the app, then open http://localhost:8000
uvicorn candlelit.server:app --port 8000
```

Terminal only (milestone 1 in the doc):

```bash
python -m candlelit.cli "Kingston, ON" --type ghost --length long -v
```

Tests: `python -m pytest -q`

## Settings

All optional, set as environment variables:

| Variable | Default | What it does |
| --- | --- | --- |
| `CL_MODEL` | `gemma4:e4b` | Story model. Any Ollama chat model works; bigger writes better, slower. |
| `CL_EMBED_MODEL` | `nomic-embed-text` | Embeddings for the repetition check. Skipped if not pulled. |
| `CL_NUM_CTX` | `8192` | Context window. The selection prompt needs about 7K tokens. |
| `CL_SIMILARITY` | `0.85` | Rewrite threshold. Tune on 20 to 30 real stories. |
| `CL_SEARCH_BACKEND` | `duckduckgo` | `auto` lets `ddgs` also query Brave, Yahoo, etc. More reliable, less private. |
| `CL_DB` | `data/candlelit.db` | SQLite file for history and the 24-hour search cache. |
| `CL_CONTACT_URL` | `https://localhost` | Put in the User-Agent; Wikipedia blocks agents without one. |

## How the code maps to the design

| Doc section | Code |
| --- | --- |
| 10-step pipeline, two loops | [candlelit/pipeline.py](candlelit/pipeline.py) (step list at the top of the file) |
| Prompts and JSON schemas (plan 0.2, select 0.2, write 0.9) | [candlelit/prompts.py](candlelit/prompts.py) |
| Search, cache, backoff, Wikipedia fallback, `trafilatura` | [candlelit/search.py](candlelit/search.py) |
| History table, duplicate legends, similarity | [candlelit/history.py](candlelit/history.py) |
| Style rotation pools | [candlelit/style.py](candlelit/style.py) |
| Sound whitelist and cue spacing rules | [candlelit/sounds.py](candlelit/sounds.py) |
| API: `POST /api/story` (SSE), `GET/DELETE /api/history`, `/sounds/{id}.ogg` | [candlelit/server.py](candlelit/server.py) |
| Candlelit UI, typewriter, end card | [web/](web/) |

Extras beyond the doc: `GET /api/history/{id}` (reopen a past tale), and `GET /api/status`, which lets the page warn when Ollama or a model is missing.

## Sounds

`sounds/` is empty on purpose. Any sound without a file is **synthesised in the browser** (`web/audio.js`), so the app has sound from the first run. To use real recordings, download CC0 files from [Freesound](https://freesound.org) or [OpenGameArt](https://opengameart.org), save them as `sounds/<id>.ogg` (`fire`, `wind`, `water`, `creak`, `door`, `footsteps`, `bell`, `whisper`, `knock`, `crow`, `chains`, `heartbeat`), and fill in [sounds/credits.json](sounds/credits.json). Safari can't decode Ogg, so it always uses the synthesised versions.

## Notes from the first real runs

These answer some of the doc's open questions. Tested on a GTX 1050 (4 GB) with `gemma4:e4b`:

- **Time per story:** a short tale takes about **3.5 to 4 minutes**, and most of that is the select and write model calls. Ways to speed it up: `CL_MODEL=gemma4:e2b`, a smaller `CL_NUM_CTX`, or a bigger GPU.
- **Small models cite lazily.** They often cite one page for every fact, so code adds any other page that names the same legend as corroboration. The search widens only when fewer than 2 usable pages are found, as the doc says. An earlier version widened whenever the model cited fewer than 2 pages, and it drifted from Salem, MA to Salem, NJ.
- **`ddgs` v9** is a metasearch, so it is pinned to DuckDuckGo (see `CL_SEARCH_BACKEND`). Lookups that return no results are not retried; only rate limits and timeouts are.
- **`trafilatura`** needs `lxml_html_clean` on current lxml. It's in `requirements.txt`, and the app now fails loudly if it's missing.

The page and fonts are self-hosted (Cinzel and IM Fell English, both SIL OFL), so opening the page makes no Google requests.
