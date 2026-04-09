# FarmLens RPi Node

> **Phase 2** of the FarmLens system — Raspberry Pi server that captures camera frames, runs AI inference, receives ESP32 sensor data, fuses everything into a single health score, and serves the FarmLens Flutter app via REST API.

**Suez Canal University · Faculty of Engineering · IC EISIS 2026**
Abdel Rahman M. El-Saied · Mohamed Elsayed

---

## System Overview

FarmLens has three components. This repo is the RPi Node.

```
[ESP32 Sensor Bridge] ──POST /api/sensor──► [RPi Node ◄── this repo]
                                                    │
                                          REST API (port 8000)
                                                    │
                                         [Flutter App]  [Web Dashboard]
```

| Component | Repo | Role |
|-----------|------|------|
| **RPi Node** | ← this repo | Camera · AI inference · Fusion · API server |
| Firmware | farmlens-firmware | ESP32 sensor bridge (UART → WiFi POST) |
| App | farmlens-app | Flutter companion app |

---

## Quick Start

### 1. Flash Raspberry Pi OS

Use **Raspberry Pi Imager** with Raspberry Pi OS **Bookworm 64-bit**. Enable SSH and set WiFi credentials in the Imager settings (⚙ gear icon).

### 2. Copy the project to the RPi

```bash
# From your PC
scp -r farmlens-rpi/ pi@<RPI_IP>:/home/pi/
```

### 3. Run the installer

SSH into the RPi, then run the one-shot installer:

```bash
cd ~/farmlens-rpi
chmod +x install.sh
./install.sh
```

This installs all system packages, creates a Python virtual environment, sets up the `farmlens` systemd service, and starts it automatically.

### 4. Open the dashboard

```
http://<RPI_IP>:8000
```

The FarmLens Flutter app connects to the same address on port `8000`.

---

## Configuration

All settings live in the `.env` file — edit it and restart the service. No code changes needed.

```bash
nano ~/farmlens-rpi/.env
sudo systemctl restart farmlens
```

### Key settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | `FL-001` | Node identifier — must match ESP32 `NODE_ID` |
| `API_PORT` | `8000` | HTTP port the server listens on |
| `CAMERA_BACKEND` | `picamera2` | `picamera2` (CSI ribbon) or `opencv` (USB webcam) |
| `CAMERA_INDEX` | `0` | USB webcam index (opencv only) |
| `AI_MODE` | `mock` | `mock` (random walk) or `tflite` (real model) |
| `MODEL_FILE` | `plant_disease.tflite` | TFLite model filename inside `models/` |
| `CYCLE_INTERVAL_S` | `30` | Seconds between capture-infer-fuse cycles |
| `DEFAULT_W1` | `0.6` | AI confidence weight in fusion formula |
| `DEFAULT_W2` | `0.4` | Sensor stress weight in fusion formula |
| `DEFAULT_THETA` | `0.5` | Alert threshold (`Ccombined > theta` → alert) |
| `DEFAULT_CROP` | `tomato` | Default crop type |

---

## API Reference

All endpoints return JSON with `Access-Control-Allow-Origin: *`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web dashboard (HTML) |
| `GET` | `/api/status` | Node health — uptime, ESP32 status, camera |
| `POST` | `/api/sensor` | ESP32 posts sensor data here every 5 s |
| `GET` | `/api/live` | Current sensor + AI data (app polls every 5 s) |
| `GET` | `/api/logs?limit=50` | Cycle history (newest first, max 200) |
| `GET` | `/api/image/{cycle_id}` | JPEG image for a specific cycle |
| `GET` | `/api/snapshot` | Fresh live camera frame |
| `GET` | `/api/settings` | Current fusion weights |
| `POST` | `/api/settings` | Update fusion weights live (no restart) |

### Sample `/api/live` response

```json
{
  "ts": 1712345678,
  "node_id": "FL-001",
  "moisture_raw": 2341,
  "moisture_pct": 42.3,
  "water_raw": 1820,
  "water_pct": 44.5,
  "moisture_stress": 0,
  "water_stress": 0,
  "cs": 0.0,
  "cv": 0.72,
  "ccombined": 0.43,
  "alert": false,
  "detection_class": "Tomato_healthy",
  "detection_conf": 0.72,
  "cycle_id": "FL-001-20240405-143218",
  "has_image": true,
  "fault": 0
}
```

---

## Fusion Formula

Each 30-second cycle produces:

```
Cs        = 0.6 × moisture_stress + 0.4 × water_stress
Ccombined = w1 × Cv + w2 × Cs        (defaults: w1=0.6, w2=0.4)
Alert     = Ccombined > theta         (default theta=0.5)
```

Weights and threshold are editable live via `POST /api/settings` — no restart needed.

---

## Camera Setup

**RPi Camera v1.3 / v2 / HQ (CSI ribbon):**
```bash
# In .env
CAMERA_BACKEND=picamera2

# Test
python3 -c "from picamera2 import Picamera2; c=Picamera2(); print('OK')"
```

**USB Webcam:**
```bash
# In .env
CAMERA_BACKEND=opencv
CAMERA_INDEX=0

# Test
python3 -c "import cv2; c=cv2.VideoCapture(0); print('OK' if c.isOpened() else 'FAIL')"
```

---

## AI Model Upgrade

To switch from mock mode to a real TFLite plant disease model:

1. Copy your model to `models/plant_disease.tflite`
2. Set in `.env`:
   ```
   AI_MODE=tflite
   MODEL_FILE=plant_disease.tflite
   ```
3. Install TFLite runtime:
   ```bash
   source ~/farmlens-rpi/venv/bin/activate
   pip install tflite-runtime
   ```
4. Restart:
   ```bash
   sudo systemctl restart farmlens
   ```
5. Verify in logs:
   ```bash
   journalctl -u farmlens -n 20
   # Should say: TFLite model loaded ✓
   ```

The Flutter app, web dashboard, API, and fusion engine require **zero changes** when switching AI modes.

---

## Service Management

```bash
sudo systemctl status  farmlens        # Check if running
sudo systemctl restart farmlens        # Restart (e.g. after .env change)
sudo systemctl stop    farmlens        # Stop
sudo systemctl start   farmlens        # Start manually
journalctl -u farmlens -f              # Live logs
journalctl -u farmlens -n 50          # Last 50 lines
```

---

## File Structure

```
farmlens-rpi/
├── .env                ← All user settings (edit this)
├── install.sh          ← One-shot installer — run once on new RPi
├── requirements.txt    ← Python package list
│
├── main.py             ← Entry point / orchestrator (30 s cycle loop)
├── config.py           ← Reads .env, defines all constants
├── camera.py           ← Camera capture (picamera2 or OpenCV)
├── inference.py        ← AI inference (mock random walk or TFLite)
├── fusion.py           ← Sensor fusion + ESP32 data store (thread-safe)
├── logger.py           ← SQLite cycle history + JPEG path helpers
├── api.py              ← FastAPI server + web dashboard
│
├── models/             ← Place .tflite model here (auto-created)
├── logs/images/        ← One annotated JPEG per cycle (auto-created)
├── farmlens.db         ← SQLite database (auto-created)
└── farmlens.log        ← Log file (auto-created)
```

---

## Troubleshooting

**Service not starting:**
```bash
journalctl -u farmlens -n 30
# Look for Python import errors or permission issues
```

**Camera not working:**
```bash
python3 -c "from picamera2 import Picamera2; Picamera2()"
# If error: check ribbon cable, or run sudo raspi-config → Interface Options → Camera
```

**Port 8000 already in use:**
```bash
sudo ss -tlnp | grep 8000
# Change API_PORT in .env and restart
```

**ESP32 shows POST FAIL:**
1. Verify RPi IP hasn't changed: `hostname -I`
2. Update `RPI_IP` in ESP32 firmware and reflash, or assign the RPi a static IP via your router's DHCP settings.

**Dashboard shows stale data after restart:**
The SQLite database (`farmlens.db`) persists across restarts intentionally. To clear history:
```bash
rm ~/farmlens-rpi/farmlens.db
# Recreated automatically on next start
```

---

## Hardware Requirements

- Raspberry Pi 4 (any RAM variant)
- Raspberry Pi OS Bookworm 64-bit
- RPi Camera v1.3 / v2 / HQ **or** any USB webcam
- WiFi — same network as ESP32 and Flutter app

---

## Phase 2 vs Phase 1

| Phase 1 (ESP32 only) | Phase 2 (this repo — RPi) |
|---|---|
| Mock sensor data generated on ESP32 | Real ADC readings forwarded via UART |
| Mock AI (random walk Cv) | Real TFLite inference on RPi |
| RAM-only log buffer | SQLite persistent history |
| No camera | Camera frame per cycle + JPEG archive |
| Settings reset on reboot | Settings via `.env`, persist across restarts |
| Served directly from ESP32 | RPi serves the app; ESP32 is sensor bridge only |