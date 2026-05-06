# ============================================================
# StreamIngest — reads RTSP from MediaMTX for ANPR frames
# Uses a dedicated thread so read timeouts never block asyncio
# ============================================================

import asyncio
import logging
import os
import threading
import time

import cv2
import numpy as np

log = logging.getLogger("stream_ingest")

RTSP_URL      = "rtsp://localhost:8554/gate"
ANPR_INTERVAL = 0.5   # seconds between ANPR checks
READ_TIMEOUT  = 5000  # ms — opencv read timeout (not 30s)
OPEN_TIMEOUT  = 8000  # ms — opencv open timeout

# Low-latency RTSP options for OpenCV/ffmpeg
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp"
    "|fflags;nobuffer"
    "|flags;low_delay"
    "|max_delay;0"
    "|reorder_queue_size;0"
    "|max_interleave_delta;0"
)


class StreamIngest:
    def __init__(self):
        self._last_anpr = 0.0
        self._stop      = threading.Event()

    # ── public entry point called by app.py lifespan ──────────
    async def run(self, db, broadcast):
        loop = asyncio.get_event_loop()
        while True:
            try:
                cap = await loop.run_in_executor(None, self._open)
                log.info("[StreamIngest] Stream opened")
                await self._read_loop(cap, db, broadcast, loop)
            except Exception as exc:
                log.warning(f"[StreamIngest] {exc} — reconnecting in 3 s")
            await asyncio.sleep(3)

    # ── open with short timeout ────────────────────────────────
    def _open(self) -> cv2.VideoCapture:
        log.info(f"[StreamIngest] Connecting to {RTSP_URL}")
        cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,         1)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,  OPEN_TIMEOUT)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC,  READ_TIMEOUT)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {RTSP_URL}")
        return cap

    # ── read frames in executor thread ────────────────────────
    async def _read_loop(self, cap, db, broadcast, loop):
        try:
            while True:
                # run_in_executor with 5 s read timeout — never blocks longer
                ret, frame = await asyncio.wait_for(
                    loop.run_in_executor(None, cap.read),
                    timeout=READ_TIMEOUT / 1000 + 1
                )
                if not ret:
                    log.warning("[StreamIngest] Frame read failed — reconnecting")
                    break

                now = time.monotonic()
                if now - self._last_anpr >= ANPR_INTERVAL:
                    self._last_anpr = now
                    asyncio.create_task(self._run_anpr(frame, db, broadcast))
        finally:
            cap.release()

    # ── ANPR task (replace stub with real pipeline) ───────────
    async def _run_anpr(self, frame, db, broadcast):
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, _detect_plate, frame)
            if result:
                db.save(result)
                await broadcast({"type": "plate", "data": result})
        except Exception as exc:
            log.warning(f"[ANPR] task error: {exc}")


def _detect_plate(frame: np.ndarray) -> dict | None:
    """
    Stub — replace with YOLO + OCR.
    Return {"plate": "GJ01AB1234", "confidence": 0.91, "ts": time.time()}
    or None.
    """
    return None
