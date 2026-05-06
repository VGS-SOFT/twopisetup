# ============================================================
# StreamIngest — uses PyAV (not OpenCV) for RTSP frame grab
# OpenCV VideoCapture segfaults on Pi ARM when RTSP drops mid-read
# PyAV handles reconnects cleanly without crashing the process
# Browser video is served directly by MediaMTX WebRTC — unaffected
# ============================================================

import asyncio
import logging
import time
import av
import numpy as np

log = logging.getLogger("stream_ingest")

RTSP_URL      = "rtsp://localhost:8554/gate"
ANPR_INTERVAL = 0.5   # seconds between ANPR checks


class StreamIngest:
    def __init__(self):
        self._last_anpr = 0.0

    async def run(self, db, broadcast):
        loop = asyncio.get_event_loop()
        while True:
            try:
                await loop.run_in_executor(None, self._blocking_loop, db, broadcast)
            except Exception as exc:
                log.warning(f"[StreamIngest] {exc} — reconnecting in 3 s")
            await asyncio.sleep(3)

    def _blocking_loop(self, db, broadcast):
        """Runs entirely in a thread executor — no asyncio calls inside."""
        log.info(f"[StreamIngest] Connecting to {RTSP_URL}")
        container = av.open(
            RTSP_URL,
            options={
                "rtsp_transport": "tcp",
                "fflags":         "nobuffer",
                "flags":          "low_delay",
                "max_delay":      "0",
            },
            timeout=8.0,
        )
        log.info("[StreamIngest] Stream opened")
        try:
            for packet in container.demux(video=0):
                for frame in packet.decode():
                    now = time.monotonic()
                    if now - self._last_anpr < ANPR_INTERVAL:
                        continue
                    self._last_anpr = now
                    # convert to numpy BGR for OpenCV-based ANPR
                    img = frame.to_ndarray(format="bgr24")
                    result = _detect_plate(img)
                    if result:
                        # Schedule broadcast back on the event loop
                        asyncio.get_event_loop().call_soon_threadsafe(
                            lambda r=result: asyncio.ensure_future(
                                _broadcast_result(r, db, broadcast)
                            )
                        )
        except Exception as exc:
            raise RuntimeError(f"Stream read error: {exc}") from exc
        finally:
            container.close()


async def _broadcast_result(result, db, broadcast):
    try:
        db.save(result)
        await broadcast({"type": "plate", "data": result})
    except Exception as exc:
        log.warning(f"[ANPR] broadcast error: {exc}")


def _detect_plate(frame: np.ndarray) -> dict | None:
    """
    Stub — replace with YOLO + OCR.
    Return: {"plate": "GJ01AB1234", "confidence": 0.91, "ts": time.time()}
    or None.
    """
    return None
