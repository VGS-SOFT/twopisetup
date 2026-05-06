# ============================================================
# StreamIngest — reads UDP MPEG-TS stream from Pi4
# Runs ANPR detection on each frame independently
# Does NOT touch the MediaMTX video path
# ============================================================

import asyncio
import logging
import time

import cv2
import numpy as np

log = logging.getLogger("stream_ingest")

# MPEG-TS over UDP — must match how Pi4 sends it
# ffmpeg wraps H.264 in MPEG-TS, so we tell OpenCV to expect mpegts
UDP_URL = "udp://@:5555"
CV_OPTS  = [
    "protocol_whitelist", "udp,rtp,file,crypto",
    "fflags", "nobuffer",
    "flags", "low_delay",
    "max_delay", "0",
    "reorder_queue_size", "0",
]
ANPR_INTERVAL = 0.5         # run ANPR at most every 500 ms


class StreamIngest:
    def __init__(self):
        self.cap = None
        self._last_anpr = 0.0

    def _open(self):
        log.info(f"[StreamIngest] Connecting to {UDP_URL}")
        # Build GStreamer-style ffmpeg pipeline string for OpenCV
        # Using CAP_FFMPEG with explicit low-latency options via env isn't
        # possible directly, so we use the pipe URL with options embedded
        url = (
            f"udp://@:5555"
            f"?fifo_size=1000000"
            f"&overrun_nonfatal=1"
            f"&timeout=5000000"
        )
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open stream: {url}")
        return cap

    async def run(self, db, broadcast):
        """Main loop — opens stream, reads frames, triggers ANPR."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                self.cap = await loop.run_in_executor(None, self._open)
                log.info("[StreamIngest] Stream opened")
                await self._read_loop(db, broadcast, loop)
            except Exception as e:
                log.warning(f"[StreamIngest] Stream error: {e} — reconnecting in 2s")
                if self.cap:
                    self.cap.release()
                await asyncio.sleep(2)

    async def _read_loop(self, db, broadcast, loop):
        while True:
            ret, frame = await loop.run_in_executor(None, self.cap.read)
            if not ret:
                log.warning("[StreamIngest] Frame read failed")
                break

            now = time.monotonic()
            if now - self._last_anpr >= ANPR_INTERVAL:
                self._last_anpr = now
                asyncio.create_task(
                    self._run_anpr(frame, db, broadcast)
                )

    async def _run_anpr(self, frame, db, broadcast):
        """Placeholder — wire in your YOLO + OCR pipeline here."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _detect_plate, frame)
        if result:
            db.save(result)
            await broadcast({"type": "plate", "data": result})


def _detect_plate(frame: np.ndarray) -> dict | None:
    """
    Replace this stub with your YOLO + OCR logic.
    Return a dict like:
      {"plate": "GJ01AB1234", "confidence": 0.91, "ts": time.time()}
    or None if no plate found.
    """
    return None
