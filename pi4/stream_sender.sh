#!/bin/bash
# ============================================================
# Pi4 Camera Sender — 180p30 H.264 over UDP
# Target: piANPR at PIANPR_IP:5555
# Codec:  Hardware H.264 via V4L2 (no software encode)
# Bitrate: 2000000 (2 Mbps — highest useful for 320x180)
# Low-latency: intra-refresh every 30 frames, no B-frames
# ============================================================

PIANPR_IP="${1:-192.168.1.100}"   # pass IP as argument or edit default
PORT=5555
BITRATE=2000000                    # 2 Mbps — overkill for 180p, crystal clear
FPS=30
WIDTH=320
HEIGHT=180

echo "[Pi4 Sender] Starting 180p30 H.264 UDP stream"
echo "  Target  : udp://${PIANPR_IP}:${PORT}"
echo "  Bitrate : ${BITRATE} bps"
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
