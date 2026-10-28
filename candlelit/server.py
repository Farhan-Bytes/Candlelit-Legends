"""Local FastAPI backend. Run with: uvicorn candlelit.server:app --port 8000"""

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .history import History
from .llm import LLMError, OllamaClient
from .pipeline import NoLegendFound, Pipeline, StoryRequest
from .search import Searcher
from .sounds import LIBRARY

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("candlelit")

history = History(config.DB_PATH)
llm = OllamaClient()
searcher = Searcher(history)

app = FastAPI(title="Candlelit Legends")


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Always revalidate the page's own files, so an edited app.js is never served stale."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/story")
def story(req: StoryRequest):
    pipeline = Pipeline(llm, searcher, history)

    def stream():
        try:
            for event, data in pipeline.run(req):
                yield sse(event, data)
        except NoLegendFound:
            yield sse("error", {"message": f"The records are silent about {req.place}. "
                                           "Try a nearby town, or a bigger region."})
        except LLMError as e:
            log.exception("Model step failed")
            yield sse("error", {"message": "The candle sputtered: the local model did not answer. "
                                           "Is Ollama running?", "detail": str(e)})
        except Exception as e:  # keep the page informed instead of dropping the stream
            log.exception("Story pipeline failed")
            yield sse("error", {"message": "Something went wrong in the dark.", "detail": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/history")
def list_history():
    return [{"id": s["id"], "created_at": s["created_at"], "place": s["place_input"], "title": s["title"],
             "location": s["location"], "narrator": s["narrator"], "tone": s["tone"]}
            for s in history.recent()]


@app.get("/api/history/{story_id}")
def get_story(story_id: int):
    s = history.get(story_id)
    if not s:
        raise HTTPException(404, "No such tale")
    return {"story": {"title": s["title"], "text": s["story"]}, "meta": s["meta"]}


@app.delete("/api/history")
def clear_history():
    history.clear()
    return {"cleared": True}


@app.get("/api/status")
def status():
    return {**llm.status(), "sounds": {sid: {"kind": kind, "caption": caption,
                                             "file": (config.SOUNDS_DIR / f"{sid}.ogg").exists()}
                                       for sid, (kind, caption) in LIBRARY.items()}}


app.mount("/sounds", StaticFiles(directory=config.SOUNDS_DIR), name="sounds")
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html")
