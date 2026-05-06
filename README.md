# 🚗 Two-Pi ANPR System — `twopisetup`

> **Project Goal:** A real-time Automatic Number Plate Recognition (ANPR) system split across two Raspberry Pis. Pi 4 at the gate captures and streams live video internally; piANPR inside the cabin receives that stream, runs vehicle detection + OCR, and serves a live web dashboard accessible from any browser on the LAN.

---

## 📦 Table of Contents

1. [What We Are Trying to Achieve](#1-what-we-are-trying-to-achieve)
2. [Hardware](#2-hardware)
3. [Network Setup](#3-network-setup)
4. [Final Architecture Decision](#4-final-architecture-decision)
5. [Role Split Between the Two Pis](#5-role-split-between-the-two-pis)
6. [Internal Stream: Pi4 → piANPR](#6-internal-stream-pi4--pianpr)
7. [Web Dashboard: piANPR → Browser](#7-web-dashboard-pianpr--browser)
8. [ANPR Detection Pipeline (on piANPR)](#8-anpr-detection-pipeline-on-pianpr)
9. [Why We Chose Web-Based Viewing](#9-why-we-chose-web-based-viewing)
10. [Performance Targets](#10-performance-targets)
11. [What's Built Next (Phase Roadmap)](#11-whats-built-next-phase-roadmap)
12. [Project Structure (Planned)](#12-project-structure-planned)
13. [Key Technical Decisions Log](#13-key-technical-decisions-log)

---

## 1. What We Are Trying to Achieve

We have a **vehicle gate** at a premises. Every vehicle that enters or exits must have its number plate read automatically without any manual input from the operator.

The operator sits **inside a cabin** away from the gate. They need to:
- See a live view of the gate camera.
- See the detected number plate text in real-time as cars pass.
- Have the whole thing work fast enough to handle real gate traffic (estimated 12–15 cars per minute).

Instead of relying on expensive CCTV NVR systems or cloud-based ANPR APIs, we are building this ourselves using two Raspberry Pi 4 boards, open-source computer vision (YOLO), OCR, and a web server — all running on a local private network.

The end result: the operator opens a browser, sees the live camera feed from the gate, and every time a car passes, the plate number appears on screen — all processed locally, no internet required.

---

## 2. Hardware

| Component | Details |
|---|---|
| **Pi4** (Gate Pi) | Raspberry Pi 4B — 4 GB RAM |
| **Camera** | Raspberry Pi Camera Module v2 (Sony IMX219, 8 MP) |
| **piANPR** (Cabin Pi) | Raspberry Pi 4B — 8 GB RAM |
| **Network** | Both Pis on same LAN via `vitthalshringar` Wi-Fi router |
| **Access method** | SSH into both Pis; piANPR also accessible via VS Code Remote SSH |

### Camera Specs (Pi Camera Module v2)
- Sensor: Sony IMX219
- Max resolution: 3280 × 2464 px still
- Video modes: 1080p @ 30fps, **720p @ 60fps**, 640×480 @ 90fps
- Interface: CSI ribbon cable directly to Pi4's camera port
- Status: Physically connected and confirmed working on Pi4

---

## 3. Network Setup

Both Pis are connected to the same Wi-Fi router (`vitthalshringar`) and have **DHCP reservations** configured on the router so their IPs never change across reboots.

| Device | Hostname | Reserved IP |
|---|---|---|
| Gate Pi | `vraj@pi4` | `192.168.137.174` |
| Cabin Pi | `vraj@anpr` | `192.168.137.200` |

Because both Pis share the same LAN, they can communicate **directly by IP or hostname** without any internet dependency. The operator's browser (on any device on the same network) also connects to `192.168.137.200` — the cabin Pi — to see the web dashboard.

> **Important:** The gate Pi (`pi4`) is never directly exposed to the browser. The browser only ever talks to `piANPR`. This keeps the gate device lean and simple.

---

## 4. Final Architecture Decision

After testing multiple approaches (raw Python frame sockets, `ffplay` over UDP, VNC-based viewing), we landed on this architecture:

```
┌──────────────────────────────────┐         LAN (Wi-Fi)
│           Pi4 @ Gate             │ ───────────────────────────────────────────────┐
│                                  │         UDP / MPEG-TS stream                   │
│  Camera v2 → rpicam-vid          │ ──────────────────────────────────────────────►│
│  Hardware H.264 encode           │                                                 │
│  No display, no GUI              │                                                 │
└──────────────────────────────────┘                              ┌──────────────────┴──────────────┐
                                                                   │       piANPR @ Cabin            │
                                                                   │                                 │
                                                                   │  Receive stream → decode        │
                                                                   │  YOLO vehicle detection         │
                                                                   │  YOLO plate crop                │
                                                                   │  OCR → plate string             │
                                                                   │  Web server (Flask/FastAPI)      │
                                                                   │  WebRTC or MJPEG to browser     │
                                                                   │                                 │
                                                                   └─────────────────────────────────┘
                                                                                    │
                                                                          Browser on LAN
                                                                    http://192.168.137.200:PORT
                                                                   ┌─────────────────────────────────┐
                                                                   │  Live camera feed               │
                                                                   │  Detected plate overlay         │
                                                                   │  Plate text + timestamp log     │
                                                                   └─────────────────────────────────┘
```

---

## 5. Role Split Between the Two Pis

| Task | Pi4 (Gate) | piANPR (Cabin) |
|---|:---:|:---:|
| Camera capture | ✅ | ❌ |
| H.264 hardware encode | ✅ | ❌ |
| Stream sender (UDP/MPEG-TS) | ✅ | ❌ |
| Stream receiver/decoder | ❌ | ✅ |
| YOLO vehicle detection | ❌ | ✅ |
| Number plate crop | ❌ | ✅ |
| OCR server call | ❌ | ✅ |
| Web server (Flask/FastAPI) | ❌ | ✅ |
| Browser-facing live feed | ❌ | ✅ |
| Web dashboard UI | ❌ | ✅ |
| Detection log / history | ❌ | ✅ |

This clean split ensures Pi4 stays **lightweight** (only runs camera + encoder + UDP sender) and piANPR handles all the heavy compute (YOLO inference, OCR, web serving).

---

## 6. Internal Stream: Pi4 → piANPR

### Protocol
UDP / MPEG-TS using `rpicam-vid` with hardware H.264 encoding.

### Why UDP/MPEG-TS?
- Lower latency than RTSP on a controlled LAN.
- Native Raspberry Pi toolchain support via `rpicam-vid`.
- No extra server daemon needed on Pi4.
- Works well as an internal transport; the browser-facing path is handled separately on piANPR.

### Sender command (on Pi4)
```bash
rpicam-vid -t 0 \
  --nopreview \
  --inline \
  --width 1280 \
  --height 720 \
  --framerate 30 \
  --bitrate 8000000 \
  --codec libav \
  --libav-format mpegts \
  -o udp://192.168.137.200:5555
```

**Key flags explained:**
| Flag | Meaning |
|---|---|
| `-t 0` | Run forever (no timeout) |
| `--nopreview` | No HDMI display on Pi4, saves resources |
| `--inline` | Embed SPS/PPS headers in stream for receiver sync |
| `--width/height` | 720p resolution — fits Camera v2's 720p60 native mode |
| `--framerate 30` | 30 fps is stable; 60 fps tested and too heavy on Wi-Fi |
| `--bitrate 8000000` | 8 Mbps gives good image quality without overloading network |
| `--codec libav --libav-format mpegts` | Hardware H.264 encode, output as MPEG-TS container |
| `-o udp://...` | Send directly to piANPR's reserved IP on port 5555 |

### Receiver ingest (on piANPR, for ANPR pipeline)
OpenCV captures directly from the UDP stream:
```python
import cv2

cap = cv2.VideoCapture(
    'udp://@:5555',
    cv2.CAP_FFMPEG
)
# Always grab the freshest frame, don't process every queued frame
while True:
    cap.grab()          # flush buffer
    ret, frame = cap.retrieve()
    if ret:
        process_frame(frame)   # send to YOLO pipeline
```

> **Critical:** Always call `cap.grab()` in a tight loop and only read with `cap.retrieve()` when ready to process. This prevents the OpenCV buffer from building up stale frames, which is the number one cause of detection lag in live ANPR systems.

---

## 7. Web Dashboard: piANPR → Browser

### Why Web and Not VNC or Qt GUI?
- VNC adds a remote-desktop encoding layer on top of video, making latency look worse than it is.
- A browser-based UI is accessible from **any device on the LAN** — laptop, phone, tablet — without installing anything.
- The web stack lets us combine the live feed, detection overlays, plate text, and log history into one clean, responsive UI.

### Target Stack on piANPR

| Component | Technology |
|---|---|
| Web server | Flask or FastAPI (Python) |
| Live video delivery to browser | MJPEG stream (phase 1) → WebRTC (phase 2) |
| Frontend UI | HTML + JavaScript (served by Flask) |
| Real-time plate updates | WebSocket push from server to browser |
| Detection overlay | Canvas overlay on the video element |

### MJPEG streaming (Phase 1 — simple & works in any browser)
Flask serves MJPEG frames directly:
```python
from flask import Flask, Response
import cv2

app = Flask(__name__)

def generate_frames():
    cap = cv2.VideoCapture('udp://@:5555', cv2.CAP_FFMPEG)
    while True:
        cap.grab()
        ret, frame = cap.retrieve()
        if not ret:
            continue
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               buffer.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, threaded=True)
```

The browser then simply shows:
```html
<img src="http://192.168.137.200:8080/video_feed" />
```

### WebRTC (Phase 2 — lower latency, preferred for production)
WebRTC removes the MJPEG re-encoding overhead. The Pi2 web server uses a Python WebRTC library (e.g., `aiortc`) to negotiate a peer connection with the browser and push the H.264 stream natively. This is the long-term target for sub-500ms end-to-end latency.

---

## 8. ANPR Detection Pipeline (on piANPR)

The ANPR pipeline has been previously built and tested on a single Pi. It is now being adapted to ingest from the UDP stream and output to the web dashboard.

### Pipeline stages

```
UDP frame received
      │
      ▼
┌─────────────────────┐
│  Stage 1: Vehicle   │  YOLO Model 1
│  Detection          │  Detects cars/trucks in frame
│  (YOLO)             │  Outputs bounding box
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Stage 2: Plate     │  YOLO Model 2
│  Crop               │  Within detected vehicle ROI,
│  (YOLO)             │  locates and crops the plate region
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Stage 3: OCR       │  OCR server call (local or LAN)
│                     │  Returns plate string
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Stage 4: Output    │  WebSocket push to browser
│                     │  Plate text + timestamp logged
│                     │  Overlay drawn on live feed
└─────────────────────┘
```

### Performance target
| Metric | Target |
|---|---|
| End-to-end latency (camera → plate text on screen) | ~2 seconds |
| Gate throughput | 12–15 cars/minute |
| False positive rate | Minimised via vehicle detection stage first |

---

## 9. Why We Chose Web-Based Viewing

During development we tested multiple viewer approaches:

| Approach | Result | Decision |
|---|---|---|
| `ffplay` on piANPR (direct) | Low quality + frozen frames | ❌ Abandoned |
| VNC remote desktop | Added its own lag on top of stream lag | ❌ Abandoned |
| Qt/Tkinter GUI on piANPR | Requires display attached to piANPR | ❌ Not ideal |
| **Browser via piANPR web server** | Clean separation, LAN accessible, no client install | ✅ **Chosen** |

The web approach is also future-proof: the same dashboard can later be accessed from a tablet at the gate reception desk, a manager's laptop, or even secured externally if needed.

---

## 10. Performance Targets

| Metric | Target | Notes |
|---|---|---|
| Camera FPS | 30 fps @ 720p | Camera v2 supports this natively |
| Internal stream latency (Pi4 → piANPR) | < 100ms | UDP/MPEG-TS on LAN |
| Web feed latency (piANPR → Browser) | < 500ms MJPEG / < 200ms WebRTC | Phase 1 / Phase 2 |
| ANPR pipeline latency | ~1–1.5 sec | YOLO + OCR |
| Total end-to-end | ~2 seconds | Acceptable for gate use |
| Concurrent browser viewers | 1–2 (LAN cabin use) | Not a public-scale deployment |

---

## 11. What's Built Next (Phase Roadmap)

### Phase 1 — Stream + Web Viewer (Current)
- [ ] Pi4: confirm `rpicam-vid` UDP stream runs reliably on boot
- [ ] piANPR: build Flask server that ingests UDP stream and serves MJPEG to browser
- [ ] Test browser view directly (not VNC) and confirm quality + latency
- [ ] Validate frame freshness in OpenCV ingest loop

### Phase 2 — ANPR Integration
- [ ] Connect existing YOLO pipeline to live UDP ingest on piANPR
- [ ] Run detection on freshest frame only (no queued backlog)
- [ ] Push detected plate text to browser via WebSocket
- [ ] Draw detection bounding box overlay on the browser canvas

### Phase 3 — Web Dashboard UI
- [ ] Clean browser UI: live feed + plate overlay + detection log table
- [ ] Plate history with timestamp stored in SQLite on piANPR
- [ ] Status indicators: stream alive/dead, detection active, last plate seen
- [ ] Mobile-friendly layout so operator can also view on phone

### Phase 4 — Stability & Hardening
- [ ] Auto-restart services on Pi4 and piANPR using `systemd`
- [ ] Handle stream reconnect if Pi4 reboots or Wi-Fi drops
- [ ] Watchdog on piANPR web server
- [ ] Final latency measurement from real gate test

### Phase 5 (Optional) — WebRTC Upgrade
- [ ] Replace MJPEG browser delivery with WebRTC using `aiortc`
- [ ] Measure latency improvement vs MJPEG
- [ ] Keep MJPEG as fallback for older/lower-spec browsers

---

## 12. Project Structure (Planned)

```
twopisetup/
│
├── pi4/                          # Code that runs on the Gate Pi (Pi4)
│   ├── stream_sender.sh          # rpicam-vid UDP stream command (shell script)
│   ├── stream_sender.service     # systemd unit for auto-start on boot
│   └── README.md                 # Pi4-specific setup notes
│
├── pianpr/                       # Code that runs on the Cabin Pi (piANPR)
│   ├── app.py                    # Main Flask/FastAPI web server
│   ├── stream_ingest.py          # UDP stream → OpenCV frame loop
│   ├── anpr_pipeline.py          # YOLO Stage 1 + Stage 2 + OCR call
│   ├── websocket_server.py       # WebSocket push for plate results
│   ├── templates/
│   │   └── index.html            # Browser dashboard UI
│   ├── static/
│   │   ├── style.css
│   │   └── dashboard.js          # Live feed + WebSocket client
│   ├── models/
│   │   ├── vehicle_detect.pt     # YOLO Model 1 weights
│   │   └── plate_crop.pt         # YOLO Model 2 weights
│   ├── requirements.txt
│   └── README.md                 # piANPR-specific setup notes
│
├── docs/
│   ├── architecture-diagram.md
│   └── latency-test-results.md
│
└── README.md                     # This file — top-level project overview
```

---

## 13. Key Technical Decisions Log

| Decision | Options Considered | Chosen | Reason |
|---|---|---|---|
| Internal transport | Raw Python sockets, RTSP, UDP/MPEG-TS | **UDP/MPEG-TS** | Lowest latency, native `rpicam-vid` support |
| Browser delivery | RTSP direct (not supported), HLS, MJPEG, WebRTC | **MJPEG (Phase 1), WebRTC (Phase 2)** | MJPEG is simplest and works in all browsers; WebRTC for production latency |
| Operator UI | VNC, Qt GUI, Web browser | **Web browser** | No client install, LAN accessible from any device, cleanest UX |
| Frame ingest for ANPR | `cv2.read()` every frame, grab+retrieve pattern | **grab+retrieve** | Prevents buffer backlog of stale frames |
| Resolution/FPS | 1080p30, 720p60, 720p30 | **720p30** | 720p60 unstable over Wi-Fi; 720p30 stable with 8Mbps bitrate |
| Detection architecture | Single Pi (all tasks), Two Pi split | **Two Pi split** | Keeps gate Pi lightweight, cabin Pi handles all compute |

---

## Contributing

This is a private/team project. If you are collaborating, always work in a feature branch and open a PR for review before merging to `main`.

---

## License

Private project — VGS IT Solution, Surat. Not for public distribution.

---

*Last updated: May 2026 — Initial architecture commit*
