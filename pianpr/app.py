"""
app.py

FastAPI application for the piANPR cabin node.

Endpoints:
  GET  /              -> Serve dashboard HTML
  POST /offer         -> WebRTC SDP signalling (browser sends offer, we return answer)
  WS   /ws/plates     -> WebSocket: push plate detection results to browser
  GET  /api/recent    -> Last 20 plate detections from SQLite
  GET  /health        -> Stream + detection health status
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aiortc import RTCPeerConnection, RTCSessionDescription

from stream_ingest import stream
from webrtc_track import UDPVideoTrack
from database import init_db, get_recent
import anpr_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Active WebRTC peer connections
peer_connections = set()

# Queue for pushing ANPR results to WebSocket clients
result_queue: asyncio.Queue = asyncio.Queue()

# Active WebSocket clients
ws_clients: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    await init_db()

    stream.start()
    logger.info("[App] Stream ingest started.")

    anpr_pipeline.init_queue(result_queue)
    asyncio.create_task(anpr_pipeline.run_pipeline())
    logger.info("[App] ANPR pipeline started.")

    asyncio.create_task(broadcast_results())
    logger.info("[App] WebSocket broadcaster started.")

    yield

    # ── Shutdown ──
    stream.stop()
    for pc in peer_connections:
        await pc.close()


app = FastAPI(title="piANPR Dashboard", lifespan=lifespan)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/offer")
async def offer(request: Request):
    """
    WebRTC signalling endpoint.
    Browser sends SDP offer -> we return SDP answer.
    """
    params = await request.json()
    offer_sdp = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    peer_connections.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        logger.info(f"[WebRTC] Connection state: {pc.connectionState}")
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            peer_connections.discard(pc)

    pc.addTrack(UDPVideoTrack())

    await pc.setRemoteDescription(offer_sdp)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return JSONResponse({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


@app.websocket("/ws/plates")
async def plate_websocket(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info(f"[WS] Client connected. Total: {len(ws_clients)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(ws_clients)}")


@app.get("/api/recent")
async def recent_detections():
    rows = await get_recent(20)
    return JSONResponse(rows)


@app.get("/health")
async def health():
    return JSONResponse({
        "stream_connected": stream.is_connected,
        "active_webrtc_peers": len(peer_connections),
        "active_ws_clients": len(ws_clients),
    })


# ── Background Tasks ─────────────────────────────────────────────────────────

async def broadcast_results():
    while True:
        result = await result_queue.get()
        dead = []
        for ws in ws_clients:
            try:
                await ws.send_json(result)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_clients.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
