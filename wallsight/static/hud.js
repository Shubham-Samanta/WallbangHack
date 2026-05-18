// hud.js
const feed = document.getElementById("feed");
const fpsEl = document.getElementById("fps");
const camEl = document.getElementById("hud-tr");

feed.setAttribute("cache-control", "no-cache");
feed.src = "/feed?t=" + Date.now();

let frames = 0;
let lastTs = Date.now();

feed.addEventListener("load", () => {
  frames++;
  const now = Date.now();
  if (now - lastTs >= 1000) {
    fpsEl.textContent = `${frames} fps`;
    frames = 0;
    lastTs = now;
  }
});

async function pollStatus() {
  try {
    const r = await fetch("/status");
    const d = await r.json();
    camEl.textContent = `${d.count} cam${d.count !== 1 ? "s" : ""} live`;
  } catch {
    camEl.textContent = "— cams";
  }
}
pollStatus();
setInterval(pollStatus, 3000);

setInterval(() => {
  feed.src = "/feed?t=" + Date.now();
}, 8000);
