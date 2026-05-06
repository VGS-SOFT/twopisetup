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

UDP_URL = "udp://@:5555"   # same port as Pi4 sends to
ANPR_INTERVAL = 0.5         # run ANPR at most every 500 ms


class StreamIngest:
    def __init__(self):
        self.cap = None
        self._last_anpr = 0.0

    def _open(self):
        log.info(f"[StreamIngest] Connecting to {UDP_URL}")
        cap = cv2.VideoCapture(
            f"{UDP_URL}",
            cv2.CAP_FFMPEG
        )
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep buffer minimal
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open stream: {UDP_URL}")
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
