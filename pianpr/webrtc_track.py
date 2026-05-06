"""
webrtc_track.py

Wraps the StreamIngest frame source as an aiortc VideoStreamTrack.
Feeds the latest UDP frame into the WebRTC peer connection.
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
VIDEO_PTIME = 1 / 30  # 30 fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)


class UDPVideoTrack(VideoStreamTrack):
    """
    Pulls the latest frame from StreamIngest and delivers it
    to the WebRTC peer as a VideoFrame.
    """

    kind = "video"

    def __init__(self):
        super().__init__()
        self._timestamp = 0

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        frame = stream.get_frame()

        if frame is None:
            # Return a black frame if stream not yet ready
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Convert BGR (OpenCV) to RGB (av/WebRTC)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame
