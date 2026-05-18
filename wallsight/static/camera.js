// camera.js — universal camera node, works on any OS/browser
const CAM_ID = "cam_" + Math.random().toString(36).slice(2, 7);
const WS_PROTO = location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = `${WS_PROTO}//${location.host}/ws/camera?id=${CAM_ID}`;
const FPS = 15;
const QUALITY = 0.65;
const WIDTH = 640;
const HEIGHT = 480;

const video = document.getElementById("preview");
const dot = document.getElementById("dot");
const label = document.getElementById("label");
const camIdEl = document.getElementById("cam-id");

camIdEl.textContent = `node id: ${CAM_ID}`;

let ws, canvas, ctx, sendInterval;

function setStatus(state, text) {
  dot.className = state;
  label.textContent = text;
}

async function initCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus(
      "error",
      "camera blocked: use HTTPS (not http). Try https://" + location.hostname + ":3000/camera"
    );
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: WIDTH, height: HEIGHT, facingMode: "environment" },
      audio: false,
    });
    video.srcObject = stream;
    canvas = document.createElement("canvas");
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    ctx = canvas.getContext("2d");
    setStatus("retry", "connecting to server...");
    connectWS();
  } catch (err) {
    setStatus("error", `camera error: ${err.message}`);
  }
}

function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    setStatus("live", "live — streaming");
    startSending();
  };

  ws.onclose = () => {
    setStatus("retry", "reconnecting...");
    clearInterval(sendInterval);
    setTimeout(connectWS, 2000);
  };

  ws.onerror = () => ws.close();
}

function startSending() {
  clearInterval(sendInterval);
  sendInterval = setInterval(() => {
    if (ws.readyState !== WebSocket.OPEN) return;
    ctx.drawImage(video, 0, 0, WIDTH, HEIGHT);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        blob.arrayBuffer().then((buf) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(buf);
        });
      },
      "image/jpeg",
      QUALITY
    );
  }, 1000 / FPS);
}

initCamera();
