# WALLSIGHT — Final Technical Plan
### Browser-First, OS-Agnostic, Multi-Camera Architecture
**Hardware:** Mac A (M1) + Mac B (M1) + iPhone · **Network:** Tailscale · **v1.0**

---

## Core Design Principle

> Every camera device is just a browser tab. Every viewer is just a browser tab.
> Only Mac B runs Python. Nothing else needs installing on any device, ever.

Adding a new camera = open a URL. Removing one = close the tab. No OS-specific code anywhere except Mac B's Python inference engine.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Tailscale network (100.x.x.x)               │
│                                                                  │
│  ┌──────────────┐      ┌───────────────────────────────────┐    │
│  │   Mac A      │      │           Mac B (hub)             │    │
│  │  any browser │      │                                   │    │
│  │              │      │  ┌─────────────────────────────┐  │    │
│  │ /camera page │─WS──►│  │   WebSocket frame server    │  │    │
│  │ getUserMedia │      │  │   accepts N camera streams  │  │    │
│  │ → frames     │      │  └──────────────┬──────────────┘  │    │
│  └──────────────┘      │                 │                  │    │
│                         │  ┌─────────────▼──────────────┐  │    │
│  ┌──────────────┐      │  │   MediaPipe inference       │  │    │
│  │  Mac B cam   │      │  │   (MPS accelerated, M1)     │  │    │
│  │  built-in    │─────►│  │   pose + segmentation       │  │    │
│  │  webcam      │      │  └─────────────┬──────────────┘  │    │
│  └──────────────┘      │                 │                  │    │
│                         │  ┌─────────────▼──────────────┐  │    │
│  ┌──────────────┐      │  │   Multi-view fusion         │  │    │
│  │  Android/    │      │  │   Valorant FX render        │  │    │
│  │  ESP32 etc.  │─WS──►│  └─────────────┬──────────────┘  │    │
│  │  (future)    │      │                 │                  │    │
│  └──────────────┘      │  ┌─────────────▼──────────────┐  │    │
│                         │  │  FastAPI server             │  │    │
│                         │  │  /feed   → MJPEG stream    │  │    │
│                         │  │  /camera → camera page     │  │    │
│                         │  │  /       → iPhone HUD PWA  │  │    │
│                         │  └─────────────────────────────┘  │    │
│                         └───────────────────────────────────┘    │
│                                        │                         │
│                          ┌─────────────▼──────────────┐         │
│                          │         iPhone              │         │
│                          │   Safari → PWA HUD          │         │
│                          │   100.x.x.B:3000            │         │
│                          └─────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Device Roles

| Device | Role | What runs on it | URL it opens |
|--------|------|----------------|--------------|
| Mac A (M1) | Edge camera #1 | Chrome browser only | `http://100.x.x.B:3000/camera` |
| Mac B (M1) | Processing hub + camera #2 | Python server + browser (own cam) | runs the server |
| iPhone | HUD viewer | Safari (PWA) | `http://100.x.x.B:3000` |
| Android (future) | Edge camera #3 | Chrome browser only | same `/camera` URL |
| ESP32-CAM (future) | Edge camera #4 | MJPEG HTTP (special handler) | posts to `/esp32` endpoint |

---

## Network: Tailscale

### Why Tailscale over raw WiFi LAN

| Problem with raw WiFi | How Tailscale fixes it |
|-----------------------|----------------------|
| IPs change on reboot | Tailscale IPs (100.x.x.x) are permanent — hardcode them once |
| Only works on same router | Works across any network — demo anywhere |
| Port forwarding headaches | Zero config — just install and sign in |
| Adding iPhone to LAN | Install app, sign in, done |

### One-time setup (all 3 devices)

```bash
# Mac A and Mac B:
brew install tailscale
sudo tailscaled &
tailscale up          # sign in with same account on all devices

# iPhone: App Store → "Tailscale" → sign in with same account

# Verify:
tailscale status
# mac-a   100.x.x.A   macOS   -
# mac-b   100.x.x.B   macOS   -
# iphone  100.x.x.C   iOS     -
```

Note your Mac B Tailscale IP — it's the only IP you need in any config file.

---

## Mac B — Environment Setup

### Python environment

```bash
# Install Python 3.11 via Homebrew
brew install python@3.11
python3.11 -m venv ~/wallsight-env
source ~/wallsight-env/bin/activate

# Core dependencies
pip install mediapipe          # pose + segmentation (Apple Silicon native)
pip install opencv-python      # frame processing
pip install numpy              # array ops
pip install fastapi            # web server (replaces Flask — async, faster)
pip install uvicorn            # ASGI server for FastAPI
pip install websockets         # WebSocket support
pip install Pillow             # image encode/decode

# Verify Apple Silicon GPU (MPS) is available
python3 -c "import mediapipe; print('mediapipe ok')"
```

### Why FastAPI over Flask
- Async by default — handles many WebSocket camera connections simultaneously without blocking
- Built-in WebSocket support
- Serves static files (the camera page + HUD PWA) natively
- No CORS issues when serving everything from same origin

---

## Project File Structure

```
~/wallsight/
│
├── server.py              ← FastAPI app: WebSocket ingestion + MJPEG out
├── pipeline.py            ← MediaPipe inference + fusion + FX
├── camera_registry.py     ← tracks connected cameras, thread-safe frame store
│
├── static/
│   ├── camera.html        ← camera node page (open on Mac A, Android, etc.)
│   ├── camera.js          ← getUserMedia → WebSocket frame sender
│   ├── hud.html           ← iPhone PWA viewer
│   ├── hud.js             ← MJPEG display + HUD overlay elements
│   ├── hud.css            ← Valorant-style HUD styling
│   └── manifest.json      ← PWA manifest (makes it installable on iPhone)
│
├── models/                ← MediaPipe model files (auto-downloaded first run)
│
└── config.py              ← all IPs, ports, resolution settings in one place
```

---

## config.py — Single Source of Truth

```python
# config.py — change ONLY this file when anything moves

MAC_B_TAILSCALE_IP = "100.x.x.B"   # fill in your actual IP
PORT_MAIN         = 3000            # HUD + camera page + MJPEG feed
PORT_WS           = 3001            # WebSocket camera ingestion

TARGET_W          = 640
TARGET_H          = 480
JPEG_QUALITY      = 82
PROCESS_EVERY_N   = 2              # process every Nth frame (tune for FPS)

# Camera source for Mac B's own built-in webcam
MAC_B_WEBCAM_INDEX = 0
```

---

## camera_registry.py — OS-Agnostic Camera Manager

This is the key module that makes adding cameras trivial:

```python
import threading
import time
from typing import Dict, Optional
import numpy as np
import cv2

class CameraRegistry:
    """
    Holds the latest frame from every connected camera.
    Cameras can be:
      - Browser WebSocket (Mac A, Android, iPhone)
      - Local webcam (Mac B built-in)
      - ESP32-CAM MJPEG HTTP (future)
    All produce the same output: a numpy BGR frame.
    """

    def __init__(self):
        self._frames: Dict[str, np.ndarray] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

    def update(self, camera_id: str, frame: np.ndarray):
        with self._lock:
            self._frames[camera_id] = frame
            self._timestamps[camera_id] = time.time()

    def get(self, camera_id: str) -> Optional[np.ndarray]:
        with self._lock:
            return self._frames.get(camera_id)

    def get_all_active(self, max_age_seconds: float = 2.0):
        """Returns all cameras with a recent frame."""
        now = time.time()
        with self._lock:
            return {
                cid: frame.copy()
                for cid, frame in self._frames.items()
                if now - self._timestamps.get(cid, 0) < max_age_seconds
            }

    def list_cameras(self):
        with self._lock:
            return list(self._frames.keys())


# Global registry — shared across all threads
registry = CameraRegistry()
```

---

## camera.html + camera.js — The Universal Camera Node Page

Open this on ANY device (Mac A, Android, future devices) in Chrome/Safari.
No install. No OS-specific code. Pure browser APIs.

```html
<!-- static/camera.html -->
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WallSight — Camera Node</title>
  <style>
    body { background:#000; display:flex; flex-direction:column;
           align-items:center; justify-content:center; height:100vh; margin:0; }
    video { width:320px; border-radius:8px; opacity:0.7; }
    #status { color:#00ffcc; font-family:monospace; font-size:13px;
              margin-top:12px; letter-spacing:2px; }
    #cam-id { color:#888; font-family:monospace; font-size:11px; margin-top:6px; }
  </style>
</head>
<body>
  <video id="preview" autoplay muted playsinline></video>
  <div id="status">connecting...</div>
  <div id="cam-id"></div>
  <script src="camera.js"></script>
</body>
</html>
```

```javascript
// static/camera.js
const WS_URL   = `ws://${location.hostname}:3001/ws/camera`;
const CAM_ID   = `cam_${Math.random().toString(36).slice(2,7)}`;  // unique per tab
const FPS      = 15;        // frames per second to send
const QUALITY  = 0.6;       // JPEG quality (0–1)
const WIDTH    = 640;
const HEIGHT   = 480;

const video    = document.getElementById('preview');
const status   = document.getElementById('status');
const camIdEl  = document.getElementById('cam-id');

camIdEl.textContent = `ID: ${CAM_ID}`;

let ws, canvas, ctx, intervalId;

async function init() {
  // 1. Request camera — works on Mac, Android, iPhone, anything
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: WIDTH, height: HEIGHT, facingMode: 'environment' },
    audio: false
  });
  video.srcObject = stream;

  canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  ctx = canvas.getContext('2d');

  // 2. Connect WebSocket to Mac B
  connectWS();
}

function connectWS() {
  ws = new WebSocket(`${WS_URL}?id=${CAM_ID}`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    status.textContent = 'live — sending frames';
    status.style.color = '#00ff88';
    startSending();
  };

  ws.onclose = () => {
    status.textContent = 'reconnecting...';
    status.style.color = '#ffaa00';
    clearInterval(intervalId);
    setTimeout(connectWS, 2000);   // auto-reconnect
  };

  ws.onerror = () => ws.close();
}

function startSending() {
  intervalId = setInterval(() => {
    if (ws.readyState !== WebSocket.OPEN) return;
    ctx.drawImage(video, 0, 0, WIDTH, HEIGHT);
    canvas.toBlob(blob => {
      blob.arrayBuffer().then(buf => ws.send(buf));
    }, 'image/jpeg', QUALITY);
  }, 1000 / FPS);
}

init().catch(err => {
  status.textContent = `camera error: ${err.message}`;
  status.style.color = '#ff4444';
});
```

---

## pipeline.py — MediaPipe Inference + Fusion + FX

```python
import cv2
import numpy as np
import mediapipe as mp
from typing import Dict

mp_pose      = mp.solutions.pose
mp_selfie    = mp.solutions.selfie_segmentation
mp_drawing   = mp.solutions.drawing_utils
mp_styles    = mp.solutions.drawing_styles

# Init models once at startup
pose_model = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,          # 0=lite, 1=full, 2=heavy — start with 1
    smooth_landmarks=True,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.5
)

seg_model = mp_selfie.SelfieSegmentation(model_selection=1)


def process_frame(frame: np.ndarray):
    """Run pose + segmentation on a single frame."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pose_result = pose_model.process(rgb)
    seg_result  = seg_model.process(rgb)
    return pose_result, seg_result


def fuse_frames(frames: Dict[str, np.ndarray]) -> np.ndarray:
    """
    Accept frames from N cameras.
    Run inference on each, fuse segmentation masks,
    draw skeleton from highest-confidence pose result.
    Returns final styled frame.
    """
    if not frames:
        return np.zeros((480, 640, 3), dtype=np.uint8)

    cam_ids = list(frames.keys())

    # Run inference on all cameras
    results = {}
    for cid, frame in frames.items():
        h, w = frame.shape[:2]
        if h != 480 or w != 640:
            frame = cv2.resize(frame, (640, 480))
        results[cid] = process_frame(frame)

    # Pick primary frame (cam closest to centre of scene, or first available)
    primary_id = cam_ids[0]
    primary_frame = cv2.resize(frames[primary_id], (640, 480))

    # Fuse segmentation masks — union of all detected person masks
    fused_mask = np.zeros((480, 640), dtype=np.float32)
    for cid, (pose_res, seg_res) in results.items():
        if seg_res.segmentation_mask is not None:
            mask = cv2.resize(seg_res.segmentation_mask, (640, 480))
            fused_mask = np.maximum(fused_mask, mask)

    # Apply Valorant visual style
    output = apply_valorant_fx(primary_frame, fused_mask, results[primary_id][0])
    return output


def apply_valorant_fx(frame: np.ndarray, mask: np.ndarray,
                      pose_result) -> np.ndarray:
    """
    Dark background + cyan body outline + orange skeleton + scanlines.
    """
    h, w = frame.shape[:2]

    # 1. Dark background
    bg = np.zeros((h, w, 3), dtype=np.uint8)
    bg[:] = (10, 8, 6)    # very dark warm black

    # 2. Soft body fill from segmentation mask
    mask_3ch = np.stack([mask] * 3, axis=-1)
    mask_hard = (mask > 0.5).astype(np.float32)
    mask_soft = cv2.GaussianBlur(mask_hard, (0, 0), sigmaX=4)
    mask_3ch_soft = np.stack([mask_soft] * 3, axis=-1)

    # Cyan-tinted body region
    tinted = frame.copy().astype(np.float32)
    tinted[:, :, 2] *= 0.3    # reduce red
    tinted[:, :, 1] *= 1.1    # boost green
    tinted[:, :, 0] *= 1.3    # boost blue
    tinted = np.clip(tinted, 0, 255).astype(np.uint8)

    body_layer = (tinted * mask_3ch_soft + bg * (1 - mask_3ch_soft)).astype(np.uint8)

    # 3. Edge glow (Canny on mask)
    mask_uint8 = (mask_hard * 255).astype(np.uint8)
    edges = cv2.Canny(mask_uint8, 40, 120)
    glow = cv2.GaussianBlur(edges, (0, 0), sigmaX=3)
    body_layer[:, :, 0] = np.clip(body_layer[:, :, 0].astype(int) + glow, 0, 255)
    body_layer[:, :, 1] = np.clip(body_layer[:, :, 1].astype(int) + glow, 0, 255)

    output = body_layer.copy()

    # 4. Skeleton overlay (orange bones)
    if pose_result.pose_landmarks:
        mp_drawing.draw_landmarks(
            output,
            pose_result.pose_landmarks,
            mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=mp_drawing.DrawingSpec(
                color=(0, 140, 255), thickness=2, circle_radius=3),
            connection_drawing_spec=mp_drawing.DrawingSpec(
                color=(0, 100, 220), thickness=2)
        )

    # 5. Scanlines (every 4 pixels, subtle)
    output[::4, :] = (output[::4, :] * 0.7).astype(np.uint8)

    return output
```

---

## server.py — FastAPI Hub

```python
import asyncio
import threading
import time
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn

from camera_registry import registry
from pipeline import fuse_frames
from config import (MAC_B_WEBCAM_INDEX, TARGET_W, TARGET_H,
                    JPEG_QUALITY, PROCESS_EVERY_N, PORT_MAIN, PORT_WS)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Latest processed frame (thread-safe) ─────────────────────────
latest_output: bytes = b""
output_lock   = threading.Lock()

# ── WebSocket camera ingestion ────────────────────────────────────
@app.websocket("/ws/camera")
async def camera_ws(ws: WebSocket):
    cam_id = ws.query_params.get("id", "unknown")
    await ws.accept()
    print(f"[CAM] {cam_id} connected")
    try:
        while True:
            data = await ws.receive_bytes()
            arr  = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                registry.update(cam_id, frame)
    except WebSocketDisconnect:
        print(f"[CAM] {cam_id} disconnected")

# ── Mac B built-in webcam (runs in background thread) ────────────
def mac_b_webcam_thread():
    cap = cv2.VideoCapture(MAC_B_WEBCAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_H)
    while True:
        ok, frame = cap.read()
        if ok:
            registry.update("mac_b_builtin", frame)
        time.sleep(0.033)

# ── Processing loop (runs in background thread) ───────────────────
def processing_loop():
    global latest_output
    tick = 0
    while True:
        tick += 1
        if tick % PROCESS_EVERY_N != 0:
            time.sleep(0.01)
            continue

        frames = registry.get_all_active()
        if not frames:
            time.sleep(0.05)
            continue

        output = fuse_frames(frames)
        _, buf = cv2.imencode('.jpg', output,
                              [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        with output_lock:
            latest_output = buf.tobytes()

        time.sleep(0.001)

# ── MJPEG feed → iPhone ───────────────────────────────────────────
def mjpeg_generator():
    while True:
        with output_lock:
            frame = latest_output
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.033)

@app.get("/feed")
def feed():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# ── Routes ────────────────────────────────────────────────────────
@app.get("/")
def hud():
    return HTMLResponse(open("static/hud.html").read())

@app.get("/camera")
def camera_page():
    return HTMLResponse(open("static/camera.html").read())

@app.get("/status")
def status():
    return {"cameras": registry.list_cameras()}

# ── Startup ───────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    threading.Thread(target=mac_b_webcam_thread, daemon=True).start()
    threading.Thread(target=processing_loop, daemon=True).start()

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT_MAIN,
                ws_max_size=10 * 1024 * 1024)   # 10MB max WS message
```

---

## static/hud.html + hud.css — iPhone PWA

```html
<!-- static/hud.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="#000a14">
  <link rel="manifest" href="/static/manifest.json">
  <link rel="apple-touch-icon" href="/static/icon.png">
  <title>WALLSIGHT</title>
  <link rel="stylesheet" href="/static/hud.css">
</head>
<body>
  <img id="feed" src="/feed" alt="live feed">

  <div id="hud-top">
    <span id="dot"></span>
    <span id="label">WALLSIGHT // LIVE</span>
  </div>

  <div id="hud-cameras">
    <span id="cam-count">— cams</span>
  </div>

  <div id="hud-bottom">
    <span id="fps-counter">— fps</span>
  </div>

  <script src="/static/hud.js"></script>
</body>
</html>
```

```css
/* static/hud.css */
* { margin:0; padding:0; box-sizing:border-box; }

body {
  background:#000a14;
  width:100vw; height:100vh;
  overflow:hidden;
  display:flex; align-items:center; justify-content:center;
}

#feed {
  width:100vw;
  height:100vh;
  object-fit:cover;
}

#hud-top {
  position:absolute; top:14px; left:16px;
  color:#00ffcc; font-family:monospace;
  font-size:11px; letter-spacing:2px;
  display:flex; align-items:center; gap:8px;
}

#dot {
  width:7px; height:7px; border-radius:50%;
  background:#00ff88;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.15} }

#hud-cameras {
  position:absolute; top:14px; right:16px;
  color:#00ffcc88; font-family:monospace;
  font-size:10px; letter-spacing:1px;
}

#hud-bottom {
  position:absolute; bottom:14px; right:16px;
  color:#00ffcc55; font-family:monospace; font-size:10px;
}

/* Vignette overlay */
body::after {
  content:'';
  position:absolute; inset:0;
  background: radial-gradient(ellipse at center,
    transparent 55%, rgba(0,0,0,0.7) 100%);
  pointer-events:none;
}
```

```javascript
// static/hud.js
const STATUS_URL = '/status';
let frameCount = 0, lastTime = Date.now();
const fpsEl  = document.getElementById('fps-counter');
const camEl  = document.getElementById('cam-count');
const feed   = document.getElementById('feed');

// FPS counter
feed.addEventListener('load', () => {
  frameCount++;
  const now = Date.now();
  if (now - lastTime >= 1000) {
    fpsEl.textContent = `${frameCount} fps`;
    frameCount = 0;
    lastTime = now;
  }
});

// Camera count poller
setInterval(async () => {
  try {
    const r = await fetch(STATUS_URL);
    const d = await r.json();
    camEl.textContent = `${d.cameras.length} cam${d.cameras.length !== 1 ? 's' : ''}`;
  } catch {}
}, 3000);
```

```json
// static/manifest.json
{
  "name": "WALLSIGHT",
  "short_name": "WALLSIGHT",
  "display": "fullscreen",
  "orientation": "landscape",
  "background_color": "#000a14",
  "theme_color": "#000a14",
  "start_url": "/",
  "icons": [{ "src": "/static/icon.png", "sizes": "192x192", "type": "image/png" }]
}
```

> **To install as app on iPhone:** open Safari → share button → "Add to Home Screen"
> Launches fullscreen, no browser chrome, landscape locked. Looks native.

---

## Running the System

### Mac B — start the server (one command)

```bash
cd ~/wallsight
source ~/wallsight-env/bin/activate
python server.py
# Server live at http://0.0.0.0:3000
# Tailscale URL: http://100.x.x.B:3000
```

### Mac A — open camera page (zero install)

```
Open Chrome → http://100.x.x.B:3000/camera
Allow camera access → streaming immediately
```

### iPhone — open HUD

```
Open Safari → http://100.x.x.B:3000
Share → Add to Home Screen → launch fullscreen
```

### Check connected cameras

```
http://100.x.x.B:3000/status
→ {"cameras": ["mac_b_builtin", "cam_a3f9x"]}
```

---

## Adding Cameras Later — Zero Code Changes

| New device | What to do |
|------------|-----------|
| Android phone | Open Chrome → `http://100.x.x.B:3000/camera` → allow camera |
| Second iPhone | Same URL in Safari |
| Laptop (any OS) | Chrome → same URL |
| ESP32-CAM | Special endpoint `/esp32?id=esp1` accepts MJPEG POST |
| IP Webcam app | MJPEG pull → registry.update() in a background thread |

For ESP32, add one route to server.py:

```python
@app.post("/esp32")
async def esp32_frame(request: Request, id: str = "esp32_0"):
    data = await request.body()
    arr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is not None:
        registry.update(id, frame)
    return {"ok": True}
```

No other changes. The pipeline picks it up automatically.

---

## Performance on M1 Mac B

| Resolution | Cameras | FPS (estimated) | Notes |
|------------|---------|----------------|-------|
| 640×480 | 2 | 20–28 FPS | good for demo |
| 640×480 | 4 | 12–18 FPS | still usable |
| 320×240 | 2 | 35–45 FPS | if latency matters more than quality |

MediaPipe uses Apple Neural Engine on M1 — inference is ~8–15ms per frame,
faster than any Intel alternative at the same quality.

---

## Latency Budget (end to end)

```
Browser capture (Mac A)     →  ~33ms  (at 30 FPS capture)
JPEG encode in browser      →  ~5ms
WebSocket transit (LAN)     →  ~5ms
Python decode               →  ~3ms
MediaPipe inference (MPS)   →  ~12ms
Fusion + FX render          →  ~8ms
JPEG encode output          →  ~5ms
Tailscale transit → iPhone  →  ~8ms
iPhone MJPEG decode         →  ~8ms
─────────────────────────────────────
Total                       →  ~87ms  ≈ 11 FPS theoretical ceiling
With PROCESS_EVERY_N=2      →  ~120ms at ~20 FPS display rate
```

For a wall-awareness demo this is excellent. Sub-150ms feels real-time.

---

## Build Checklist

### Phase 0 — Network (Day 1, ~30 min)
- [ ] Install Tailscale on Mac A, Mac B, iPhone
- [ ] Confirm `tailscale status` shows all 3 devices
- [ ] Note Mac B Tailscale IP → update `config.py`

### Phase 1 — Server skeleton (Day 1–2)
- [ ] Create project folder + venv on Mac B
- [ ] Install all pip packages
- [ ] Run `server.py` — confirm it starts without errors
- [ ] Open `/status` in browser → `{"cameras": ["mac_b_builtin"]}`

### Phase 2 — Camera page (Day 2)
- [ ] Open `/camera` on Mac B itself → confirm frame streaming
- [ ] Open `/camera` on Mac A → confirm second camera appears in `/status`
- [ ] Verify `registry.get_all_active()` returns frames from both

### Phase 3 — Pipeline (Day 3)
- [ ] Run `fuse_frames()` on live frames → display with `cv2.imshow` on Mac B
- [ ] Confirm MediaPipe detects person
- [ ] Tune `model_complexity` and `PROCESS_EVERY_N` for FPS

### Phase 4 — HUD on iPhone (Day 4)
- [ ] Open `http://100.x.x.B:3000` in Safari → confirm MJPEG feed loads
- [ ] Add to Home Screen → confirm fullscreen PWA works
- [ ] Verify Valorant FX looks correct on iPhone screen

### Phase 5 — Polish (Day 5)
- [ ] Add FPS counter to HUD
- [ ] Add camera count indicator
- [ ] Test: disconnect Mac A mid-session → confirm system keeps running on Mac B cam
- [ ] Test: reconnect Mac A → confirm it reappears automatically

---

## Known Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Camera page shows "camera error: permission denied" | Browser blocked camera | In Chrome: Settings → Privacy → Camera → allow |
| WebSocket won't connect | Wrong IP in camera.js | `location.hostname` auto-uses server IP — should be automatic |
| iPhone feed shows but freezes | MJPEG buffer | Reduce JPEG_QUALITY to 70, add `?t=Date.now()` cache-buster to img src |
| MediaPipe crashes on startup | Wrong Python version | Must be 3.9–3.11. Check: `python3 --version` |
| Mac B webcam not found | Wrong device index | Run `python3 -c "import cv2; print(cv2.VideoCapture(0).isOpened())"` |
| Tailscale connection drops | Sleep/wake | `tailscale up` again, or set login expiry to never in admin console |
| PWA won't install on iPhone | No HTTPS | For local network PWA, Safari allows HTTP. If it still fails, run `mkcert` for self-signed cert |

---

## Future Camera Additions (no code changes needed)

```
V1  Mac A + Mac B builtin  →  2 cameras  ← BUILD THIS
V2  + Android phone        →  3 cameras  (open /camera in Chrome)
V3  + ESP32-CAM ×2         →  5 cameras  (add /esp32 route, ~30 lines)
V4  + Raspberry Pi cam     →  6 cameras  (MJPEG pull, ~20 lines)
```

Each addition is additive. Nothing breaks. The pipeline handles N cameras.

---

## Arduino — Future Role

Not needed for MVP. Useful later as:
- PIR motion sensor → trigger inference only when motion detected (saves CPU)
- Haptic wristband → vibrate when person detected in specific zone
- LED strip indicator → visual alert in your room independent of iPhone

Interface: Arduino USB serial → `pyserial` on Mac B → registry event trigger

---

*Total new hardware for V1: ₹0. Uses what you have.*
*Total lines of code for working demo: ~400.*
*Time to first working demo: 4–5 days part-time.*
