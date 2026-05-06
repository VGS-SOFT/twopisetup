# ============================================================
# StreamIngest — reads stream via RTSP from MediaMTX
# MediaMTX owns UDP:5555 (receives from Pi4)
# Python reads rtsp://localhost:8554/gate (no port conflict)
# Runs ANPR detection independently every ANPR_INTERVAL seconds
# ============================================================

import asyncio
import logging
import time

import cv2
import numpy as np

log = logging.getLogger("stream_ingest")

# Read from MediaMTX RTSP — avoids UDP:5555 port conflict
RTSP_URL     = "rtsp://localhost:8554/gate"
ANPR_INTERVAL = 0.5   # run ANPR at most every 500 ms


class StreamIngest:
    def __init__(self):
        self.cap = None
        self._last_anpr = 0.0

    def _open(self):
        log.info(f"[StreamIngest] Connecting to {RTSP_URL}")
        os_env = {
            "OPENCV_FFMPEG_CAPTURE_OPTIONS":
            "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
        }
        import os
        for k, v in os_env.items():
            os.environ[k] = v

        cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open RTSP stream: {RTSP_URL}")
        return cap

    async def run(self, db, broadcast):
        loop = asyncio.get_event_loop()
        while True:
            try:
                self.cap = await loop.run_in_executor(None, self._open)
                log.info("[StreamIngest] Stream opened")
                await self._read_loop(db, broadcast, loop)
            except Exception as e:
                log.warning(f"[StreamIngest] Stream error: {e} — reconnecting in 3s")
                if self.cap:
                    self.cap.release()
                await asyncio.sleep(3)

    async def _read_loop(self, db, broadcast, loop):
        while True:
            ret, frame = await loop.run_in_executor(None, self.cap.read)
            if not ret:
                log.warning("[StreamIngest] Frame read failed")
                break

            now = time.monotonic()
            if now - self._last_anpr >= ANPR_INTERVAL:
                self._last_anpr = now
                asyncio.create_task(self._run_anpr(frame, db, broadcast))

    async def _run_anpr(self, frame, db, broadcast):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _detect_plate, frame)
        if result:
            db.save(result)
            await broadcast({"type": "plate", "data": result})


def _detect_plate(frame: np.ndarray) -> dict | None:
    """
    Replace with YOLO + OCR logic.
    Return: {"plate": "GJ01AB1234", "confidence": 0.91, "ts": time.time()}
    or None if no plate found.
    """
    return None
