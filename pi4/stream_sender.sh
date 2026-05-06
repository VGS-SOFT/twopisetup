#!/bin/bash
# ============================================================
# Pi4 Camera Sender — 1080p30 H.264 over UDP
# Target: piANPR at PIANPR_IP:5555
# Codec:  Hardware H.264 via V4L2 (no software encode)
# Bitrate: 8000000 (8 Mbps — highest stable for 1080p30 on Pi4)
# Low-latency: intra-refresh every 30 frames, baseline profile
# ============================================================

PIANPR_IP="${1:-192.168.137.200}"   # pass IP as argument: bash stream_sender.sh <IP>
PORT=5555
BITRATE=8000000                      # 8 Mbps — excellent quality for 1080p30
FPS=30
WIDTH=1920
HEIGHT=1080

echo "[Pi4 Sender] Starting 1080p30 H.264 UDP stream"
echo "  Target  : udp://${PIANPR_IP}:${PORT}"
echo "  Bitrate : ${BITRATE} bps  (8 Mbps)"
echo "  Size    : ${WIDTH}x${HEIGHT} @ ${FPS}fps"
echo ""

rpicam-vid \
  --width  ${WIDTH} \
  --height ${HEIGHT} \
  --framerate ${FPS} \
  --bitrate ${BITRATE} \
  --intra 30 \
  --profile baseline \
  --level 4.0 \
  --codec h264 \
  --nopreview \
  --timeout 0 \
  --output - | \
ffmpeg -loglevel warning \
  -f h264 \
  -i pipe:0 \
  -c:v copy \
  -f mpegts \
  "udp://${PIANPR_IP}:${PORT}?pkt_size=1316&buffer_size=0"
