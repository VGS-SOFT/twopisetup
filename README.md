# twopisetup

Two-Pi live video pipeline for ANPR.

## Architecture

```
Pi4 (4GB) — Camera Sender
  Camera v2 → CSI-2 → ISP → Hardware H.264 Encoder → UDP → LAN

piANPR (8GB) — Receiver + ANPR + Browser
  UDP → MediaMTX → WebRTC/WHEP → Browser
              ↓
        Python ANPR pipeline (reads same UDP stream independently)
```

## Folders

| Folder | Device | Job |
|--------|--------|-----|
| `pi4/` | Pi4 4GB | Capture + encode + send |
| `pianpr/` | piANPR 8GB | Receive + MediaMTX + ANPR + browser |

## Quick Start

### Pi4 (sender)
```bash
cd ~/twopisetup/pi4
bash stream_sender.sh
```

### piANPR (receiver)
```bash
cd ~/twopisetup/pianpr
./mediamtx mediamtx.yml &
python3 app.py
```
Browser: `http://<piANPR-IP>:8889/gate`
