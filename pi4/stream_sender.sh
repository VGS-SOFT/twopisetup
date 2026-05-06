#!/bin/bash
# Pi4 Gate Camera - UDP Stream Sender
# Streams 720p30 H.264 via MPEG-TS to piANPR on port 5555

PIANPR_IP="192.168.137.200"
PORT="5555"

echo "[pi4] Starting UDP stream to ${PIANPR_IP}:${PORT}..."

rpicam-vid -t 0 \
  --nopreview \
  --inline \
  --width 1280 \
  --height 720 \
  --framerate 30 \
  --bitrate 8000000 \
  --codec libav \
  --libav-format mpegts \
  -o udp://${PIANPR_IP}:${PORT}
