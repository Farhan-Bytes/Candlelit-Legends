"""Settings, read from environment variables so models can be swapped without code changes."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLLAMA_URL = os.environ.get("CL_OLLAMA_URL", "http://localhost:11434").rstrip("/")
STORY_MODEL = os.environ.get("CL_MODEL", "gemma4:e4b")
EMBED_MODEL = os.environ.get("CL_EMBED_MODEL", "nomic-embed-text")
NUM_CTX = int(os.environ.get("CL_NUM_CTX", "8192"))

DB_PATH = Path(os.environ.get("CL_DB", ROOT / "data" / "candlelit.db"))
WEB_DIR = ROOT / "web"
SOUNDS_DIR = ROOT / "sounds"

# Sampling per step: planning and selection want reliable JSON, writing wants surprise.
PLAN_TEMPERATURE = 0.2
WRITE_TEMPERATURE = 0.9

# Anti-repetition. 0.85 is a starting guess; tune it on 20-30 real stories.
SIMILARITY_THRESHOLD = float(os.environ.get("CL_SIMILARITY", "0.85"))
MAX_REWRITES = 2
STYLE_WINDOW = 5

# Search and grounding. ddgs can also fan out to other engines ("auto"), but then queries
# reach Brave, Yahoo and others too, so DuckDuckGo alone is the default.
SEARCH_BACKEND = os.environ.get("CL_SEARCH_BACKEND", "duckduckgo")
RESULTS_PER_QUERY = 8
CONTACT_URL = os.environ.get("CL_CONTACT_URL", "https://localhost")  # sent in the User-Agent
MAX_PAGES = 8
PAGE_WORD_CAP = 1500
PROMPT_SOURCES = 6            # pages shown to the selection step
PROMPT_WORDS_PER_SOURCE = 700  # keeps the selection prompt inside a laptop-sized context
MIN_SOURCE_WORDS = 120
MIN_SOURCES = 2
MAX_WIDEN = 2
SEARCH_CACHE_HOURS = 24

LENGTHS = {"short": 250, "long": 600}
MAX_CUES = {"short": 6, "long": 10}
