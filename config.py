"""
FarmLens RPi Node — Configuration
==================================
ALL settings are read from environment variables first, then fall back
to sensible defaults. To change any setting, either:
  1. Edit the .env file (recommended)
  2. Export env vars before starting: export API_PORT=9000
  3. Edit the DEFAULT values below

Paths are always relative to this file's location — never hardcoded.
This means the project works regardless of where you clone/copy it.
"""
import os
import time

# ── Resolve base directory dynamically ───────────────────────────────────────
# Works no matter where the project is placed on any Raspberry Pi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _env(key: str, default: str) -> str:
    """Read from environment, then .env file, then use default."""
    return os.environ.get(key, default)

def _env_int(key: str, default: int) -> int:
    return int(_env(key, str(default)))

def _env_float(key: str, default: float) -> float:
    return float(_env(key, str(default)))

def _env_bool(key: str, default: bool) -> bool:
    return _env(key, str(default)).lower() in ("1", "true", "yes")

# Load .env file if present (simple key=value parser, no extra dependencies)
_env_file = os.path.join(BASE_DIR, ".env")
if os.path.isfile(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ═══════════════════════════════════════════════════════════════════════════════
# NODE IDENTITY
# ═══════════════════════════════════════════════════════════════════════════════
NODE_ID   = _env("NODE_ID",   "FL-001")
NODE_NAME = _env("NODE_NAME", "FarmLens Node")

# ═══════════════════════════════════════════════════════════════════════════════
# PATHS — all relative to BASE_DIR, portable across any RPi
# ═══════════════════════════════════════════════════════════════════════════════
DB_PATH       = os.path.join(BASE_DIR, _env("DB_FILE",       "farmlens.db"))
LOG_IMAGE_DIR = os.path.join(BASE_DIR, _env("LOG_IMAGE_DIR", "logs/images"))
MODEL_DIR     = os.path.join(BASE_DIR, _env("MODEL_DIR",     "models"))
MODEL_FILE    = _env("MODEL_FILE", "plant_disease.tflite")
MODEL_PATH    = os.path.join(MODEL_DIR, MODEL_FILE)
LOG_FILE      = os.path.join(BASE_DIR, _env("LOG_FILE",      "farmlens.log"))

# Create directories on import
os.makedirs(LOG_IMAGE_DIR, exist_ok=True)
os.makedirs(MODEL_DIR,     exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# API SERVER
# ═══════════════════════════════════════════════════════════════════════════════
API_HOST = _env("API_HOST", "0.0.0.0")
API_PORT = _env_int("API_PORT", 8000)

# ═══════════════════════════════════════════════════════════════════════════════
# CAMERA
# ═══════════════════════════════════════════════════════════════════════════════
# CAMERA_BACKEND: "picamera2" (RPi Camera v1/v2/HQ) or "opencv" (USB webcam)
CAMERA_BACKEND = _env("CAMERA_BACKEND", "picamera2")
CAMERA_INDEX   = _env_int("CAMERA_INDEX", 0)   # USB webcam index (opencv only)
CAMERA_WIDTH   = _env_int("CAMERA_WIDTH",  640)
CAMERA_HEIGHT  = _env_int("CAMERA_HEIGHT", 480)

# ═══════════════════════════════════════════════════════════════════════════════
# SENSOR FUSION DEFAULTS (editable live via POST /api/settings)
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_W1    = _env_float("DEFAULT_W1",    0.6)
DEFAULT_W2    = _env_float("DEFAULT_W2",    0.4)
DEFAULT_THETA = _env_float("DEFAULT_THETA", 0.5)
DEFAULT_CROP  = _env("DEFAULT_CROP", "tomato")

# ═══════════════════════════════════════════════════════════════════════════════
# SENSOR CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════════
MOISTURE_DRY              = _env_int("MOISTURE_DRY",   2800)
MOISTURE_WET              = _env_int("MOISTURE_WET",   1200)
MOISTURE_STRESS_THRESHOLD = _env_float("MOISTURE_STRESS_THRESHOLD", 30.0)
WATER_DRY                 = _env_int("WATER_DRY",      3000)
WATER_WET                 = _env_int("WATER_WET",       500)
WATER_STRESS_THRESHOLD    = _env_float("WATER_STRESS_THRESHOLD",    20.0)

# ═══════════════════════════════════════════════════════════════════════════════
# AI MODEL
# ═══════════════════════════════════════════════════════════════════════════════
# AI_MODE: "mock" (random walk, no model) or "tflite" (real inference)
AI_MODE              = _env("AI_MODE", "mock")
CONFIDENCE_THRESHOLD = _env_float("CONFIDENCE_THRESHOLD", 0.25)
NMS_IOU_THRESHOLD    = _env_float("NMS_IOU_THRESHOLD",    0.45)

# Disease classes — must match Flutter app's formatDetectionClass()
DISEASE_CLASSES = [
    "Tomato_Late_blight",
    "Tomato_Early_blight",
    "Strawberry_Leaf_scorch",
    "Pepper_Bacterial_spot",
    "Tomato_Bacterial_spot",
    "Tomato_Leaf_Mold",
    "Tomato_Septoria_leaf_spot",
    "Tomato_Spider_mites",
    "Tomato_Target_Spot",
    "Tomato_YellowLeaf_Curl_Virus",
    "Tomato_mosaic_virus",
    "Tomato_healthy",
    "Strawberry_healthy",
    "Pepper_healthy",
    "Grape_Black_rot",
    "Grape_Esca",
    "Grape_Leaf_blight",
    "Grape_healthy",
]
HEALTHY_CLASS = "Tomato_healthy"

# ═══════════════════════════════════════════════════════════════════════════════
# TIMING
# ═══════════════════════════════════════════════════════════════════════════════
CYCLE_INTERVAL_S = _env_int("CYCLE_INTERVAL_S", 30)

# ═══════════════════════════════════════════════════════════════════════════════
# RUNTIME CONSTANT
# ═══════════════════════════════════════════════════════════════════════════════
START_TIME = time.time()
