"""
stream_ingest.py

Continuously ingests the UDP/MPEG-TS stream from Pi4.
Always keeps only the FRESHEST frame available.
Uses grab+retrieve pattern to prevent stale frame buildup.
"""

import cv2
import threading
import time
import logging

logger = logging.getLogger(__name__)

UDP_URL = "udp://@:5555"


class StreamIngest:
    def __init__(self):
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self._thread = None
        self.cap = None
        self.connected = False

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._ingest_loop, daemon=True)
        self._thread.start()
        logger.info("[StreamIngest] Started ingest thread")

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        logger.info("[StreamIngest] Stopped")

    def _ingest_loop(self):
        while self.running:
            logger.info(f"[StreamIngest] Connecting to {UDP_URL}...")
            self.cap = cv2.VideoCapture(UDP_URL, cv2.CAP_FFMPEG)

            if not self.cap.isOpened():
                logger.warning("[StreamIngest] Could not open stream. Retrying in 3s...")
                time.sleep(3)
                continue

            self.connected = True
            logger.info("[StreamIngest] Stream connected.")

            while self.running:
                # grab() flushes the buffer - always gets the newest frame
                grabbed = self.cap.grab()
                if not grabbed:
                    logger.warning("[StreamIngest] Lost stream. Reconnecting...")
                    self.connected = False
                    break

                ret, frame = self.cap.retrieve()
                if ret and frame is not None:
                    with self.lock:
                        self.frame = frame

            self.cap.release()
            time.sleep(2)  # brief pause before reconnect attempt

    def get_frame(self):
        """Returns the latest frame, or None if not yet available."""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    @property
    def is_connected(self):
        return self.connected


# Global singleton — shared across app.py, webrtc_track.py, anpr_pipeline.py
stream = StreamIngest()
