#!/bin/bash
# =============================================================================
# FarmLens RPi Node — One-Shot Installer
# =============================================================================
# Run this ONCE on any new Raspberry Pi to set up everything.
# Usage:
#   chmod +x install.sh
#   ./install.sh
# =============================================================================
set -e

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="$(whoami)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         FarmLens RPi Node — Installer               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  Project directory : $PROJ_DIR"
echo "  Running as user   : $SERVICE_USER"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/5] Installing system packages..."
sudo apt update -qq
sudo apt install -y -qq \
    python3-pip python3-venv sqlite3 \
    python3-picamera2 libcamera-dev libcamera-tools \
    python3-opencv python3-numpy

# ── 2. Python virtual environment ────────────────────────────────────────────
echo "[2/5] Creating Python virtual environment..."
python3 -m venv "$PROJ_DIR/venv" --system-site-packages
source "$PROJ_DIR/venv/bin/activate"

echo "[2/5] Installing Python packages..."
pip install --quiet fastapi "uvicorn[standard]"

# ── 3. Create required directories ───────────────────────────────────────────
echo "[3/5] Creating project directories..."
mkdir -p "$PROJ_DIR/logs/images"
mkdir -p "$PROJ_DIR/models"

# ── 4. Verify camera ─────────────────────────────────────────────────────────
echo "[4/5] Testing camera..."
python3 -c "
from picamera2 import Picamera2
import time
try:
    cam = Picamera2()
    cam.configure(cam.create_still_configuration(main={'size':(640,480),'format':'RGB888'}))
    cam.start()
    time.sleep(1)
    arr = cam.capture_array()
    cam.stop()
    print('  Camera: OK ✓  shape =', arr.shape)
except Exception as e:
    print('  Camera: WARNING -', e)
    print('  (Will use placeholder frames — connect RPi Camera or set CAMERA_BACKEND=opencv in .env)')
"

echo "[4/5] Testing Python packages..."
python3 -c "import fastapi, uvicorn, cv2; print('  FastAPI:', fastapi.__version__, '  OpenCV:', cv2.__version__)"

# ── 5. Install systemd service ────────────────────────────────────────────────
echo "[5/5] Installing systemd service..."

# Create start script
cat > "$PROJ_DIR/start.sh" << STARTEOF
#!/bin/bash
cd "$PROJ_DIR"
source "$PROJ_DIR/venv/bin/activate"
exec python3 "$PROJ_DIR/main.py"
STARTEOF
chmod +x "$PROJ_DIR/start.sh"

# Create systemd service
sudo tee /etc/systemd/system/farmlens.service > /dev/null << SVCEOF
[Unit]
Description=FarmLens RPi Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJ_DIR
ExecStart=$PROJ_DIR/start.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable farmlens
sudo systemctl start farmlens

sleep 3
sudo systemctl status farmlens --no-pager

# ── Done ──────────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              Installation Complete ✓                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  Dashboard : http://$IP:8000"
echo "  API status: http://$IP:8000/api/status"
echo ""
echo "  Service commands:"
echo "    sudo systemctl status  farmlens"
echo "    sudo systemctl restart farmlens"
echo "    sudo systemctl stop    farmlens"
echo "    journalctl -u farmlens -f     (live logs)"
echo ""
echo "  To change settings, edit .env then restart:"
echo "    nano $PROJ_DIR/.env"
echo "    sudo systemctl restart farmlens"
echo ""
