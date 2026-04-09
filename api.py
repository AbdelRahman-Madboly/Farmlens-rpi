"""
FarmLens FastAPI Server
========================
Endpoints:
  GET  /              → Web dashboard (HTML)
  GET  /api/status    → Node health
  POST /api/sensor    → ESP32 posts sensor data here
  GET  /api/live      → App polls this every 5s
  GET  /api/logs      → Cycle history
  GET  /api/image/{id}→ JPEG for a specific cycle
  GET  /api/snapshot  → Fresh live camera frame
  GET  /api/settings  → Fusion weights
  POST /api/settings  → Update fusion weights (live, no restart)
"""
import time
import threading
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse

import fusion
import logger
from config import NODE_ID, START_TIME, API_PORT

log = logging.getLogger("farmlens.api")

app = FastAPI(title="FarmLens RPi Node", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared state (injected by main.py) ────────────────────────────────────────
_camera   = None
_ai_mode  = "mock"

def set_camera(cam):
    global _camera
    _camera = cam

def set_ai_mode(mode: str):
    global _ai_mode
    _ai_mode = mode

_latest: dict = {}
_latest_lock  = threading.Lock()

def update_latest(data: dict):
    with _latest_lock:
        _latest.update(data)

def get_latest() -> dict:
    with _latest_lock:
        return dict(_latest)


# ═══════════════════════════════════════════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/status")
def status():
    return {
        "node_id":         NODE_ID,
        "mode":            _ai_mode.upper(),
        "uptime_s":        int(time.time() - START_TIME),
        "free_heap":       0,
        "wifi_clients":    1,
        "cycle_count":     fusion.get_cycle_count(),
        "esp32_connected": fusion.esp32_connected(),
        "camera_ready":    _camera.is_ready() if _camera else False,
        "camera_backend":  _camera.backend()  if _camera else "none",
    }


@app.post("/api/sensor")
async def receive_sensor(body: dict):
    """ESP32 calls this every 5 seconds with mock sensor JSON."""
    fusion.update_sensor(body)
    return {"ok": True}


@app.get("/api/live")
def live():
    data = get_latest()
    if not data:
        return {
            "ts": int(time.time()), "node_id": NODE_ID,
            "moisture_raw": 2048,  "moisture_pct": 50.0,
            "water_raw":    2048,  "water_pct":    50.0,
            "moisture_stress": 0,  "water_stress": 0,
            "cs": 0.0, "cv": 0.3,  "ccombined": 0.18,
            "alert": False,
            "detection_class": "Tomato_healthy",
            "detection_conf":  0.3,
            "cycle_id": "", "has_image": False,
        }
    return data


@app.get("/api/logs")
def logs(limit: int = 50):
    limit = max(1, min(limit, 200))
    rows  = logger.get_logs(limit)
    return {"count": len(rows), "logs": rows}


@app.get("/api/image/{cycle_id}")
def get_image(cycle_id: str):
    if not logger.image_exists(cycle_id):
        raise HTTPException(404, "Image not found")
    with open(logger.image_path(cycle_id), "rb") as f:
        data = f.read()
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/snapshot")
def snapshot():
    """Live camera frame — app Camera tab refreshes this every 5s."""
    from camera import encode_jpeg
    if _camera is None:
        raise HTTPException(503, "Camera not initialised")
    frame_rgb = _camera.snapshot()

    # Convert RGB → BGR for encode_jpeg
    import cv2
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    jpeg = encode_jpeg(frame_bgr)
    if jpeg is None:
        raise HTTPException(503, "JPEG encode failed")
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/api/settings")
def get_settings():
    return fusion.get_settings()


@app.post("/api/settings")
async def post_settings(body: dict):
    fusion.update_settings(body)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# WEB DASHBOARD  (served at /)
# ═══════════════════════════════════════════════════════════════════════════════

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FarmLens Dashboard</title>
<style>
  :root {
    --green:  #1D9E75;
    --red:    #E24B4A;
    --amber:  #BA7517;
    --bg:     #F5F5F0;
    --card:   #FFFFFF;
    --border: #E8E8E4;
    --text:   #1A1A1A;
    --muted:  #6B7280;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; background: var(--bg);
         color: var(--text); padding: 16px; }
  h1 { color: var(--green); font-size: 1.4rem; margin-bottom: 4px; }
  .subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: 12px; margin-bottom: 16px; }
  .card { background: var(--card); border: 1px solid var(--border);
          border-radius: 12px; padding: 14px; }
  .card-label { font-size: .7rem; color: var(--muted); text-transform: uppercase;
                letter-spacing: .05em; margin-bottom: 6px; }
  .card-value { font-size: 1.6rem; font-weight: 700; }
  .card-unit  { font-size: .8rem; color: var(--muted); margin-left: 3px; }
  .green { color: var(--green); }
  .red   { color: var(--red);   }
  .amber { color: var(--amber); }
  .alert-banner { background: #fef2f2; border: 1px solid #fca5a5;
                  border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
                  color: var(--red); font-weight: 600; display: none; }
  .camera-wrap { background: #111; border-radius: 14px; overflow: hidden;
                 margin-bottom: 14px; aspect-ratio: 4/3; position: relative; }
  .camera-wrap img { width: 100%; height: 100%; object-fit: cover; }
  .cam-overlay { position: absolute; top: 8px; left: 8px;
                 background: rgba(0,0,0,.5); color: #fff;
                 font-size: .7rem; padding: 3px 8px; border-radius: 20px; }
  .status-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
  .badge { font-size: .7rem; padding: 3px 10px; border-radius: 20px;
           font-weight: 600; }
  .badge-green { background: #d1fae5; color: #065f46; }
  .badge-red   { background: #fee2e2; color: #991b1b; }
  .badge-grey  { background: #e5e7eb; color: #374151; }
  .log-table { width: 100%; border-collapse: collapse; font-size: .78rem; }
  .log-table th { background: var(--bg); padding: 6px 10px;
                  text-align: left; color: var(--muted); font-weight: 600;
                  border-bottom: 1px solid var(--border); }
  .log-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
  .log-table tr:last-child td { border: none; }
  footer { margin-top: 20px; font-size: .7rem; color: var(--muted); text-align: center; }
</style>
</head>
<body>
<h1>🌿 FarmLens Node Dashboard</h1>
<p class="subtitle" id="subtitle">Loading…</p>

<div id="alert-banner" class="alert-banner">⚠ Disease Alert: <span id="alert-class"></span></div>

<div class="status-row">
  <span class="badge badge-grey" id="badge-mode">MODE: —</span>
  <span class="badge badge-grey" id="badge-esp32">ESP32: —</span>
  <span class="badge badge-grey" id="badge-cam">CAM: —</span>
  <span class="badge badge-grey" id="badge-uptime">UPTIME: —</span>
</div>

<div class="camera-wrap">
  <img id="cam-img" src="/api/snapshot?t=0" alt="camera">
  <div class="cam-overlay" id="cam-label">Live</div>
</div>

<div class="grid">
  <div class="card">
    <div class="card-label">Soil Moisture</div>
    <div class="card-value" id="moisture">—<span class="card-unit">%</span></div>
  </div>
  <div class="card">
    <div class="card-label">Water Level</div>
    <div class="card-value" id="water">—<span class="card-unit">%</span></div>
  </div>
  <div class="card">
    <div class="card-label">AI Confidence (Cv)</div>
    <div class="card-value" id="cv">—</div>
  </div>
  <div class="card">
    <div class="card-label">Stress Score (Cs)</div>
    <div class="card-value" id="cs">—</div>
  </div>
  <div class="card">
    <div class="card-label">Ccombined</div>
    <div class="card-value" id="cc">—</div>
  </div>
  <div class="card">
    <div class="card-label">Detection</div>
    <div class="card-value" style="font-size:1rem;" id="detection">—</div>
  </div>
</div>

<div class="card">
  <div class="card-label" style="margin-bottom:10px">Recent Cycles</div>
  <table class="log-table">
    <thead><tr>
      <th>Cycle ID</th><th>Moisture</th><th>Water</th>
      <th>Cv</th><th>Cc</th><th>Alert</th><th>Class</th>
    </tr></thead>
    <tbody id="log-body"></tbody>
  </table>
</div>

<footer>FarmLens RPi Node · Auto-refreshes every 5s</footer>

<script>
let camTs = Date.now();

async function fetchLive() {
  try {
    const r = await fetch('/api/live');
    const d = await r.json();
    document.getElementById('moisture').innerHTML =
      d.moisture_pct.toFixed(1) + '<span class="card-unit">%</span>';
    document.getElementById('water').innerHTML =
      d.water_pct.toFixed(1) + '<span class="card-unit">%</span>';
    document.getElementById('cv').textContent = d.cv.toFixed(3);
    document.getElementById('cs').textContent = d.cs.toFixed(3);
    const ccEl = document.getElementById('cc');
    ccEl.textContent = d.ccombined.toFixed(3);
    ccEl.className = 'card-value ' + (d.ccombined > 0.65 ? 'red' : d.ccombined > 0.4 ? 'amber' : 'green');
    const det = d.detection_class.replace(/_/g,' ');
    const detEl = document.getElementById('detection');
    detEl.textContent = det;
    detEl.className = 'card-value ' + (det.includes('healthy') ? 'green' : 'red');
    const banner = document.getElementById('alert-banner');
    banner.style.display = d.alert ? 'block' : 'none';
    document.getElementById('alert-class').textContent = det;
    document.getElementById('subtitle').textContent =
      'Node: ' + d.node_id + '  ·  Cycle: ' + d.cycle_id;
  } catch(e) { console.warn('live fetch failed', e); }
}

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const fmt = s => { const h=Math.floor(s/3600),m=Math.floor((s%3600)/60);
      return h>0 ? h+'h '+m+'m' : m+'m'; };
    document.getElementById('badge-mode').textContent  = 'MODE: ' + d.mode;
    document.getElementById('badge-esp32').textContent = 'ESP32: ' + (d.esp32_connected ? '✓' : '✗');
    document.getElementById('badge-esp32').className   = 'badge ' + (d.esp32_connected ? 'badge-green' : 'badge-red');
    document.getElementById('badge-cam').textContent   = 'CAM: ' + (d.camera_ready ? d.camera_backend : 'off');
    document.getElementById('badge-cam').className     = 'badge ' + (d.camera_ready ? 'badge-green' : 'badge-red');
    document.getElementById('badge-uptime').textContent = 'UP: ' + fmt(d.uptime_s);
  } catch(e) {}
}

async function fetchLogs() {
  try {
    const r  = await fetch('/api/logs?limit=8');
    const d  = await r.json();
    const tb = document.getElementById('log-body');
    tb.innerHTML = d.logs.map(row =>
      '<tr>' +
      '<td>' + row.cycle_id.split('-').slice(-2).join('-') + '</td>' +
      '<td>' + row.moisture_pct.toFixed(1) + '%</td>' +
      '<td>' + row.water_pct.toFixed(1) + '%</td>' +
      '<td>' + row.cv.toFixed(2) + '</td>' +
      '<td>' + row.ccombined.toFixed(2) + '</td>' +
      '<td>' + (row.alert ? '<span style="color:red">YES</span>' : 'no') + '</td>' +
      '<td>' + row.detection_class.replace(/_/g,' ') + '</td>' +
      '</tr>'
    ).join('');
  } catch(e) {}
}

function refreshCamera() {
  camTs = Date.now();
  const img = document.getElementById('cam-img');
  img.src = '/api/snapshot?t=' + camTs;
  document.getElementById('cam-label').textContent = 'Live · ' + new Date().toLocaleTimeString();
}

async function tick() {
  await Promise.all([fetchLive(), fetchStatus(), fetchLogs()]);
  refreshCamera();
}

tick();
setInterval(tick, 5000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Web dashboard — open http://<RPi-IP>:8000 in any browser."""
    return HTMLResponse(content=_DASHBOARD_HTML)
