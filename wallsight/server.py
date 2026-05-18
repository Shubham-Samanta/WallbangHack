# server.py
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from camera_registry import registry
from config import (
    JPEG_QUALITY,
    MAC_B_CAM_INDEX,
    MAC_B_IP,
    PORT,
    PROCESS_EVERY_N,
    SSL_CERT,
    SSL_KEY,
    TARGET_H,
    TARGET_W,
    USE_HTTPS,
)
from pipeline import fuse_frames

_STATIC = Path(__file__).parent / "static"

app = FastAPI()

_latest_frame: bytes = b""
_frame_lock = threading.Lock()


def _set_frame(frame: np.ndarray):
    global _latest_frame
    _, buf = cv2.imencode(
        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    )
    with _frame_lock:
        _latest_frame = buf.tobytes()


def _get_frame() -> bytes:
    with _frame_lock:
        return _latest_frame


@app.websocket("/ws/camera")
async def camera_ws(ws: WebSocket):
    cam_id = ws.query_params.get("id", f"ws_{id(ws)}")
    await ws.accept()
    print(f"[CAM +] {cam_id} connected")
    try:
        while True:
            data = await ws.receive_bytes()
            arr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                registry.update(cam_id, frame)
    except WebSocketDisconnect:
        print(f"[CAM -] {cam_id} disconnected")


def _webcam_thread():
    cap = cv2.VideoCapture(MAC_B_CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_H)
    if not cap.isOpened():
        print("[WARN] Mac B webcam not available — skipping builtin cam")
        return
    print("[CAM] Mac B builtin webcam started")
    while True:
        ok, frame = cap.read()
        if ok:
            registry.update("mac_b_builtin", frame)
        else:
            time.sleep(0.1)


def _processing_loop():
    tick = 0
    print("[PIPELINE] Processing loop started")
    while True:
        tick += 1
        if tick % PROCESS_EVERY_N != 0:
            time.sleep(0.008)
            continue

        frames = registry.get_all_active()
        if not frames:
            time.sleep(0.05)
            continue

        try:
            output = fuse_frames(frames)
            _set_frame(output)
        except Exception as e:
            print(f"[PIPELINE ERR] {e}")

        time.sleep(0.001)


def _mjpeg_generator():
    while True:
        frame = _get_frame()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(0.033)


@app.get("/feed")
def feed():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/")
def hud():
    return HTMLResponse((_STATIC / "hud.html").read_text())


@app.get("/camera")
def camera_page():
    return HTMLResponse((_STATIC / "camera.html").read_text())


@app.get("/status")
def status():
    cams = registry.list_cameras()
    return JSONResponse({"cameras": cams, "count": len(cams)})


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.on_event("startup")
def startup():
    threading.Thread(target=_webcam_thread, daemon=True).start()
    threading.Thread(target=_processing_loop, daemon=True).start()
    scheme = "https" if USE_HTTPS and SSL_CERT.exists() else "http"
    base = f"{scheme}://{MAC_B_IP}:{PORT}"
    print(f"[WALLSIGHT] Server live → {base}")
    print(f"[WALLSIGHT] Camera page → {base}/camera  (use HTTPS on Mac A)")
    print(f"[WALLSIGHT] Status      → {base}/status")
    if USE_HTTPS and not SSL_CERT.exists():
        print("[WALLSIGHT] Run: ./generate_certs.sh  then restart server")


if __name__ == "__main__":
    ssl_kwargs = {}
    if USE_HTTPS:
        if SSL_CERT.exists() and SSL_KEY.exists():
            ssl_kwargs = {
                "ssl_certfile": str(SSL_CERT),
                "ssl_keyfile": str(SSL_KEY),
            }
        else:
            print("[WARN] HTTPS enabled but certs missing — falling back to HTTP")
            print("[WARN] Mac A camera will NOT work until you run ./generate_certs.sh")

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="warning",
        ws_max_size=10 * 1024 * 1024,
        **ssl_kwargs,
    )
