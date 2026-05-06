"""
webrtc_track.py

Wraps the StreamIngest frame source as an aiortc VideoStreamTrack.
Feeds the latest UDP frame into the WebRTC peer connection.

Timestamps are managed manually to avoid the _start AttributeError
that occurs when aiortc's next_timestamp() is called before the
internal clock is initialised.
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
VIDEO_PTIME      = 1 / 30          # 30 fps target
VIDEO_TIME_BASE  = fractions.Fraction(1, VIDEO_CLOCK_RATE)


class UDPVideoTrack(VideoStreamTrack):
    """
    Pulls the latest frame from StreamIngest and delivers it
    to the WebRTC peer as a VideoFrame at ~30 fps.
    """

    kind = "video"

    def __init__(self):
        super().__init__()
        self._pts       = 0
        self._start     = None   # wall-clock time of first frame

    async def recv(self):
        # Pace delivery to ~30 fps
        if self._start is None:
            self._start = time.time()

        # Calculate how long until the next frame should be sent
        next_frame_time = self._start + (self._pts / VIDEO_CLOCK_RATE)
        wait = next_frame_time - time.time()
        if wait > 0:
            await asyncio.sleep(wait)

        # Grab the freshest frame from the ingest thread
        frame = stream.get_frame()

        if frame is None:
            # Black frame while stream is connecting
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # OpenCV is BGR — av/WebRTC expects RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        video_frame          = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        video_frame.pts      = self._pts
        video_frame.time_base = VIDEO_TIME_BASE

        # Advance timestamp by one frame period
        self._pts += int(VIDEO_CLOCK_RATE * VIDEO_PTIME)

        return video_frame
