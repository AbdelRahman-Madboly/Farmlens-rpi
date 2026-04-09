"""
FarmLens RPi Node — Main Orchestrator
=======================================
Start:  python3 main.py
Stop:   Ctrl+C  or  sudo systemctl stop farmlens

Cycle every 30 seconds (configurable via CYCLE_INTERVAL_S in .env):
  1. Capture camera frame
  2. Run inference (mock or TFLite)
  3. Compute sensor fusion (uses latest ESP32 data)
  4. Draw overlay on frame and save JPEG
  5. Save cycle to SQLite
  6. Update /api/live cache
"""
import sys
import time
import signal
import logging
import threading

import uvicorn

from config import (
    NODE_ID, API_HOST, API_PORT,
    CYCLE_INTERVAL_S, LOG_FILE, AI_MODE,
)
from camera import CameraCapture, draw_overlay, save_jpeg
from inference import InferenceEngine
from fusion import compute, increment_cycle
from logger import init_db, save_cycle, image_path
from api import app, set_camera, set_ai_mode, update_latest

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("farmlens.main")

_running = True

def _handle_signal(sig, frame):
    global _running
    log.info("Shutdown signal received — stopping after current cycle")
    _running = False

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Cycle loop ────────────────────────────────────────────────────────────────

def cycle_loop(camera: CameraCapture, engine: InferenceEngine):
    log.info("Cycle loop started — every %ds", CYCLE_INTERVAL_S)

    while _running:
        cycle_start = time.time()
        n = increment_cycle()

        try:
            # 1. Capture
            frame_rgb = camera.capture()

            # 2. Inference (mock or TFLite — same interface)
            det_class, confidence, latency_ms = engine.run(frame_rgb)

            # 3. Fusion
            data = compute(det_class, confidence)

            # 4. Draw overlay + save JPEG
            frame_bgr = draw_overlay(
                frame_rgb, det_class, confidence,
                data["ccombined"], data["cycle_id"],
                ai_mode=engine.mode(),
            )
            saved           = save_jpeg(frame_bgr, image_path(data["cycle_id"]))
            data["has_image"] = saved

            # 5. Persist
            save_cycle(data)

            # 6. Update API cache
            update_latest(data)

            log.info(
                "#%-4d %-30s m=%5.1f%% w=%5.1f%% "
                "cv=%.2f cc=%.2f alert=%-3s %s%s",
                n, data["cycle_id"],
                data["moisture_pct"], data["water_pct"],
                data["cv"], data["ccombined"],
                "YES" if data["alert"] else "no",
                "[img✓]" if saved else "[no-img]",
                f" [{latency_ms:.0f}ms]" if latency_ms > 0 else "",
            )

        except Exception as e:
            log.error("Cycle #%d error: %s", n, e, exc_info=True)

        # Sleep for remainder of interval
        elapsed = time.time() - cycle_start
        sleep   = max(0.0, CYCLE_INTERVAL_S - elapsed)
        if sleep > 0:
            time.sleep(sleep)

    log.info("Cycle loop stopped after %d cycles", n)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import socket
    log.info("=" * 56)
    log.info("  FarmLens RPi Node  |  Node: %s  |  Mode: %s",
             NODE_ID, AI_MODE.upper())
    log.info("=" * 56)

    # Init database
    init_db()

    # Init camera
    camera = CameraCapture()
    set_camera(camera)

    # Init inference engine
    engine = InferenceEngine()
    set_ai_mode(engine.mode())

    # Start cycle loop in background thread
    t = threading.Thread(
        target=cycle_loop, args=(camera, engine), daemon=True
    )
    t.start()

    # Resolve actual IP for display
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "unknown"

    log.info("┌─────────────────────────────────────────────────────┐")
    log.info("│  Dashboard  : http://%-30s│", f"{ip}:{API_PORT}/")
    log.info("│  API status : http://%-30s│", f"{ip}:{API_PORT}/api/status")
    log.info("│  Live data  : http://%-30s│", f"{ip}:{API_PORT}/api/live")
    log.info("│  Snapshot   : http://%-30s│", f"{ip}:{API_PORT}/api/snapshot")
    log.info("└─────────────────────────────────────────────────────┘")
    log.info("  App connect: IP=%s  Port=%d", ip, API_PORT)

    # Run FastAPI (blocking)
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")

    # Cleanup on exit
    camera.release()
    log.info("FarmLens stopped.")


if __name__ == "__main__":
    main()
