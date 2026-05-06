# ============================================================
# piANPR — FastAPI app
# :8000  browser UI + WebSocket ANPR results
# :8554  RTSP  (MediaMTX) — Python reads frames here
# :8889  WebRTC (MediaMTX) — browser watches video here
# ============================================================

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import Database
from stream_ingest import StreamIngest

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("app")

db     = Database()
ingest = StreamIngest()
clients: list[WebSocket] = []


async def broadcast(data: dict):
    dead = []
    for ws in clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)


def _handle_task_exception(task: asyncio.Task):
    """Prevent unhandled task exceptions from silently dying."""
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        log.error(f"[Task] unhandled exception: {exc}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("[DB] Initialising database")
    db.init()
    log.info("[StreamIngest] Starting ANPR loop")
    task = asyncio.create_task(ingest.run(db, broadcast))
    task.add_done_callback(_handle_task_exception)
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # New Starlette API — request= kwarg avoids Jinja2 unhashable dict bug
    return templates.TemplateResponse(request=request, name="index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in clients:
            clients.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
