# pi4 — Camera Sender

This folder runs on the **Pi4 4GB** with Camera Module v2 attached.

## What it does

1. Captures 320×180 at 30 fps using `rpicam-vid`.
2. Hardware H.264 encode via V4L2 (VideoCore path — no CPU software encode).
3. Pipes the raw H.264 stream into `ffmpeg` which wraps it in MPEG-TS.
4. Sends over UDP to piANPR on port 5555.

## Why this setup

| Choice | Reason |
|--------|--------|
| Hardware H.264 | CPU stays free for networking, no software encode overhead |
| MPEG-TS wrapper | MediaMTX on piANPR can ingest MPEG-TS UDP natively |
| 2 Mbps bitrate | Maximum useful quality for 320×180 — no compression artifacts |
| `intra 30` | Keyframe every 30 frames = 1 second — decoder recovers fast on loss |
| `baseline profile` | Lowest decode complexity, no B-frames = lowest latency |
| `pkt_size=1316` | Safe below 1500-byte MTU, avoids fragmentation on Wi-Fi |

## Usage

```bash
# Pass piANPR IP as argument
bash stream_sender.sh 192.168.1.XXX
```

## Run as systemd service (optional)

```bash
# Edit service file — replace <PIANPR_IP> with actual IP
nano stream_sender.service

# Install
sudo cp stream_sender.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stream_sender
sudo systemctl start stream_sender

# Check status
sudo systemctl status stream_sender
journalctl -u stream_sender -f
```

## Dependencies (install once)

```bash
sudo apt update
sudo apt install -y ffmpeg
# rpicam-vid is pre-installed on Raspberry Pi OS
```
