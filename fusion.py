"""
FarmLens Sensor Fusion
=======================
- Receives ESP32 sensor data via POST /api/sensor
- Combines visual AI confidence (Cv) with soil stress score (Cs)
- Computes Ccombined = w1*Cv + w2*Cs
- Fires alert when Ccombined > theta

All state is thread-safe (Lock-protected).
Weights are editable live via POST /api/settings — no restart needed.
"""
import threading
import time
import logging

from config import (
    DEFAULT_W1, DEFAULT_W2, DEFAULT_THETA, DEFAULT_CROP,
    MOISTURE_STRESS_THRESHOLD, WATER_STRESS_THRESHOLD,
    NODE_ID,
)

log = logging.getLogger("farmlens.fusion")

_lock = threading.Lock()

# ── Sensor store — updated by POST /api/sensor ───────────────────────────────
_sensor: dict = {
    "node_id":         NODE_ID,
    "moisture_raw":    2048,
    "moisture_pct":    50.0,
    "water_raw":       2048,
    "water_pct":       50.0,
    "moisture_stress": 0,
    "water_stress":    0,
    "ts":              0,
    "fault":           1,        # 1 = no ESP32 data yet
    "last_esp32_ts":   0.0,
}

# ── Fusion settings — editable via POST /api/settings ────────────────────────
_settings: dict = {
    "w1":        DEFAULT_W1,
    "w2":        DEFAULT_W2,
    "theta":     DEFAULT_THETA,
    "crop_type": DEFAULT_CROP,
}


def update_sensor(data: dict):
    """Called when ESP32 POSTs new sensor data."""
    with _lock:
        _sensor.update({
            "node_id":         str(data.get("node_id", NODE_ID)),
            "moisture_raw":    int(data.get("moisture_raw", 2048)),
            "moisture_pct":    float(data.get("moisture_pct", 50.0)),
            "water_raw":       int(data.get("water_raw", 2048)),
            "water_pct":       float(data.get("water_pct", 50.0)),
            "moisture_stress": int(data.get("moisture_stress", 0)),
            "water_stress":    int(data.get("water_stress", 0)),
            "ts":              int(data.get("ts", 0)),
            "fault":           int(data.get("fault", 0)),
            "last_esp32_ts":   time.time(),
        })


def get_sensor() -> dict:
    with _lock:
        return dict(_sensor)


def get_settings() -> dict:
    with _lock:
        return dict(_settings)


def update_settings(data: dict):
    with _lock:
        if "w1"        in data: _settings["w1"]        = float(data["w1"])
        if "w2"        in data: _settings["w2"]        = float(data["w2"])
        if "theta"     in data: _settings["theta"]     = float(data["theta"])
        if "crop_type" in data: _settings["crop_type"] = str(data["crop_type"])
    log.info("Settings updated: %s", _settings)


def compute(detection_class: str, confidence: float) -> dict:
    """
    Run one fusion cycle.
    Returns full result dict — becomes /api/live and is saved to SQLite.

    To swap in real AI: just change how (detection_class, confidence) are
    produced upstream in main.py. This function never needs to change.
    """
    with _lock:
        s   = dict(_sensor)
        cfg = dict(_settings)

    # Sensor stress from ESP32 values
    m_stress = 1 if s["moisture_pct"] < MOISTURE_STRESS_THRESHOLD else 0
    w_stress = 1 if s["water_pct"]    < WATER_STRESS_THRESHOLD    else 0
    cs = round(0.6 * m_stress + 0.4 * w_stress, 3)

    # Ccombined
    cc    = round(min(1.0, cfg["w1"] * confidence + cfg["w2"] * cs), 3)
    alert = cc > cfg["theta"]

    cycle_id = f"{NODE_ID}-{time.strftime('%Y%m%d-%H%M%S')}"

    return {
        "ts":              int(time.time()),
        "node_id":         s["node_id"],
        "moisture_raw":    s["moisture_raw"],
        "moisture_pct":    round(s["moisture_pct"], 1),
        "water_raw":       s["water_raw"],
        "water_pct":       round(s["water_pct"], 1),
        "moisture_stress": m_stress,
        "water_stress":    w_stress,
        "cs":              cs,
        "cv":              round(confidence, 3),
        "ccombined":       cc,
        "alert":           alert,
        "detection_class": detection_class,
        "detection_conf":  round(confidence, 3),
        "cycle_id":        cycle_id,
        "has_image":       False,
        "fault":           s["fault"],
    }


def esp32_connected() -> bool:
    """True if an ESP32 packet arrived in the last 30 seconds."""
    with _lock:
        return (time.time() - _sensor["last_esp32_ts"]) < 30


_cycle_count = 0

def increment_cycle() -> int:
    global _cycle_count
    _cycle_count += 1
    return _cycle_count

def get_cycle_count() -> int:
    return _cycle_count
