# pianpr — Receiver + ANPR + Browser

This folder runs on the **piANPR 8GB** board.

## Architecture on this Pi

```
UDP:5555 (from Pi4)
    │
    ├──► MediaMTX  ──► WebRTC WHEP :8889/gate  ──► Browser
    │     (Go binary, zero Python CPU for video delivery)
    │
    └──► stream_ingest.py  ──► _detect_plate()  ──► database.py
              (reads same UDP independently)         (SQLite)
                                 │
                           FastAPI WebSocket :8000/ws
                                 │
                              Browser overlay
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app — browser UI + WebSocket |
| `stream_ingest.py` | Reads UDP stream, calls ANPR every 500ms |
| `database.py` | SQLite — saves every detected plate |
| `mediamtx.yml` | MediaMTX config — UDP in, WebRTC WHEP out |
| `requirements.txt` | Python dependencies |
| `templates/index.html` | Browser UI — WebRTC player + live stats + plate log |

## Setup (run once)

```bash
# 1. Clone repo
git clone https://github.com/VGS-SOFT/twopisetup.git ~/twopisetup
cd ~/twopisetup/pianpr

# 2. Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python deps
pip install -r requirements.txt

# 4. Download MediaMTX (ARM64)
wget -O ~/twopisetup/mediamtx.tar.gz \
  https://github.com/bluenviron/mediamtx/releases/download/v1.9.3/mediamtx_v1.9.3_linux_arm64v8.tar.gz
tar -xzf ~/twopisetup/mediamtx.tar.gz -C ~/twopisetup/
rm ~/twopisetup/mediamtx.tar.gz
```

## Run

```bash
# Terminal 1 — MediaMTX (video relay)
cd ~/twopisetup
./mediamtx pianpr/mediamtx.yml

# Terminal 2 — FastAPI (ANPR + browser)
cd ~/twopisetup/pianpr
source .venv/bin/activate
python3 app.py
```

## Browser

Open on any device on the same network:
```
http://<piANPR-IP>:8889/gate        ← raw WebRTC (MediaMTX)
http://<piANPR-IP>:8000             ← full UI with stats + plate log
```

## Live stats — how they work

The browser calls `RTCPeerConnection.getStats()` every 1 second.
This is a **browser-native call** — it reads directly from the WebRTC
engine with no server involved, giving true live metrics:
- FPS decoded
- Incoming bitrate (kbps)
- Packet loss count
- Jitter (ms)
- Resolution
- Estimated playout latency

## Adding your ANPR model

Edit `stream_ingest.py` → replace the `_detect_plate()` stub at the bottom
with your YOLO + OCR logic. The rest of the pipeline (DB, WebSocket broadcast,
browser overlay) is already wired.
