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
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole

from stream_ingest import stream
from webrtc_track import UDPVideoTrack
from database import init_db, get_recent
import anpr_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="piANPR Dashboard")

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Active WebRTC peer connections
peer_connections = set()

# Queue for pushing ANPR results to WebSocket clients
result_queue: asyncio.Queue = asyncio.Queue()

# Active WebSocket clients
ws_clients: list[WebSocket] = []


@app.on_event("startup")
async def startup():
    # Initialise database
    await init_db()

    # Start UDP stream ingest
    stream.start()
    logger.info("[App] Stream ingest started.")

    # Pass queue to ANPR pipeline
    anpr_pipeline.init_queue(result_queue)

    # Start ANPR pipeline as background task
    asyncio.create_task(anpr_pipeline.run_pipeline())
    logger.info("[App] ANPR pipeline started.")

    # Start WebSocket broadcaster
    asyncio.create_task(broadcast_results())
    logger.info("[App] WebSocket broadcaster started.")


@app.on_event("shutdown")
async def shutdown():
    stream.stop()
    for pc in peer_connections:
        await pc.close()


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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

    # Add the live video track from UDP stream
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
    """
    WebSocket endpoint.
    Browser connects here to receive real-time plate detection results.
    """
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info(f"[WS] Client connected. Total: {len(ws_clients)}")
    try:
        while True:
            # Keep connection alive, data is pushed by broadcaster
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(ws_clients)}")


@app.get("/api/recent")
async def recent_detections():
    """Returns last 20 plate detections from SQLite."""
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
    """
    Reads from result_queue and pushes to all connected WebSocket clients.
    """
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
