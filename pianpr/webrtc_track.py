"""
webrtc_track.py

Wraps the StreamIngest frame source as an aiortc VideoStreamTrack.
Timestamps managed manually at 60fps target.
"""

import asyncio
import fractions
import time
import cv2
import numpy as np
from av import VideoFrame
from aiortc import VideoStreamTrack

from stream_ingest import stream

VIDEO_CLOCK_RATE = 90000
TARGET_FPS       = 60
VIDEO_PTIME      = 1 / TARGET_FPS
VIDEO_TIME_BASE  = fractions.Fraction(1, VIDEO_CLOCK_RATE)
PTS_INCREMENT    = int(VIDEO_CLOCK_RATE * VIDEO_PTIME)  # 1500 ticks per frame @ 60fps


class UDPVideoTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self):
        super().__init__()
        self._pts   = 0
        self._start = None

    async def recv(self):
        # Initialise wall-clock on first call
        if self._start is None:
            self._start = time.monotonic()

        # Calculate deadline for this frame
        deadline = self._start + (self._pts / VIDEO_CLOCK_RATE)
        now      = time.monotonic()
        wait     = deadline - now

        # Sleep only if we're ahead of schedule
        # Use a tight sleep to minimise latency at 60fps
        if wait > 0.002:  # > 2ms headroom
            await asyncio.sleep(wait - 0.001)  # wake 1ms early

        frame = stream.get_frame()

        if frame is None:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        video_frame           = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        video_frame.pts       = self._pts
        video_frame.time_base = VIDEO_TIME_BASE

        self._pts += PTS_INCREMENT

        return video_frame
