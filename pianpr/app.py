# ============================================================
# piANPR — FastAPI app
# Serves browser UI on :8000
# Reads UDP stream for ANPR (independent of MediaMTX)
# WebSocket pushes ANPR results live to browser
# MediaMTX (separate process) handles WebRTC video on :8889
# ============================================================

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from database import Database
from stream_ingest import StreamIngest

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger("app")

db  = Database()
ingest = StreamIngest()

# ── connected WebSocket clients ──────────────────────────────
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

# ── lifespan: start/stop background tasks ───────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("[DB] Initialising database")
    db.init()
    log.info("[StreamIngest] Starting ANPR loop")
    task = asyncio.create_task(ingest.run(db, broadcast))
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            await ws.receive_text()   # keep alive — browser sends pings
    except WebSocketDisconnect:
        clients.remove(ws)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
