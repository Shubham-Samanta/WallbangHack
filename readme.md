# WallSight

Multi-camera pose + segmentation hub (Mac B) with browser camera nodes (Mac A) and iPhone HUD viewer. See [WALLSIGHT_FINAL_TECH_PLAN.md](WALLSIGHT_FINAL_TECH_PLAN.md) for full architecture.

## Prerequisites

- **Mac B** — Python 3.11+ venv, Tailscale, camera permission for Terminal/Cursor
- **Mac A** — Chrome only (no Python)
- **iPhone** — Safari + Tailscale (HUD, after `server.py` is built)
- All devices on the same Tailscale account

IPs are in `wallsight/config.py` (update if yours differ).

| Device | Tailscale IP (example) | Role |
|--------|------------------------|------|
| Mac B | `100.84.88.110` | Server (`shubham-sankalps-macbook-air`) |
| Mac A | `100.124.162.83` | Browser camera (`shubhams-macbook-air`) |
| iPhone | `100.104.191.98` | HUD viewer |

---

## One-time setup (Mac B)

```bash
cd wallsight
python3.11 -m venv venv
source venv/bin/activate
pip install mediapipe opencv-python numpy fastapi uvicorn websockets Pillow
```

**macOS camera:** System Settings → Privacy & Security → Camera → enable for Terminal (or Cursor). Quit and reopen the app after changing.

First run of the pipeline may download models into `wallsight/models/`.

---

## Test pipeline only (Mac B)

Verifies MediaPipe + webcam + Valorant FX in a local window.

```bash
cd wallsight
source venv/bin/activate
python test_pipeline.py
```

Press **Q** to quit.

Quick webcam check:

```bash
python -c "import cv2; c=cv2.VideoCapture(0); print('opened:', c.isOpened()); c.release()"
```

---

## HTTPS certs (Mac B — required for Mac A camera)

Chrome blocks webcam on `http://100.x.x.x`. Generate a self-signed cert **once** on Mac B:

```bash
cd wallsight
chmod +x generate_certs.sh
./generate_certs.sh 100.84.88.110
```

## Run the full system (Mac B)

```bash
cd wallsight
source venv/bin/activate
python server.py
```

Use **`https://`** URLs (not `http://`). On first visit, click **Advanced → Proceed** to trust the self-signed cert.

Server listens on `0.0.0.0:3000` (HTTP) and `3001` (WebSocket cameras).

| URL | Device | Purpose |
|-----|--------|---------|
| `http://<MAC_B_IP>:3000/` | iPhone | HUD / MJPEG viewer |
| `http://<MAC_B_IP>:3000/camera` | Mac A | Browser camera feed |
| `http://<MAC_B_IP>:3000/status` | Any | Connected cameras JSON |
| `http://<MAC_B_IP>:3000/feed` | Any | Raw MJPEG stream |

Example (replace with your Mac B IP from `config.py`):

- Mac A camera: `https://100.84.88.110:3000/camera`
- iPhone HUD: `https://100.84.88.110:3000`

---

## Mac A (camera only)

1. Open Chrome.
2. Go to `https://<MAC_B_IP>:3000/camera` (must be HTTPS)
3. Allow camera access and leave the tab open.

No install or terminal commands on Mac A.

---

## iPhone (HUD)

1. Safari → `http://<MAC_B_IP>:3000`
2. Share → **Add to Home Screen** for fullscreen PWA.

---

## Project layout

```
wallsight/
  config.py           # IPs, ports, resolution
  camera_registry.py  # Thread-safe frame store
  pipeline.py         # MediaPipe + fusion + FX
  test_pipeline.py    # Local webcam test
  server.py           # FastAPI hub (WIP)
  static/             # camera + HUD pages (WIP)
  models/             # Downloaded .task / .tflite weights
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `not authorized to capture video` | Grant Camera to Terminal/Cursor in System Settings, restart app |
| `Cannot open webcam` | Try `MAC_B_CAM_INDEX = 1` in `config.py` |
| Flickering body/skeleton | Tune `MASK_SMOOTH` in `pipeline.py` (default `0.72`) |
| Mac A can’t connect | Confirm Tailscale on both Macs; use **Mac B** IP in the URL, not Mac A’s |
| `getUserMedia` undefined on Mac A | Use **https://** not http://; run `./generate_certs.sh` on Mac B and restart server |
