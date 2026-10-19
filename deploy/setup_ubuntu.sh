#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu 22.04/24.04 VM (Oracle Cloud Always Free works). Run as the default user:
#   bash deploy/setup_ubuntu.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl xz-utils

# Node 22 LTS from nodejs.org (only needed to build the dashboard once)
if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
  ARCH=$(uname -m); [ "$ARCH" = "aarch64" ] && NARCH=arm64 || NARCH=x64
  NODE_VER=v22.11.0
  curl -fsSLO "https://nodejs.org/dist/${NODE_VER}/node-${NODE_VER}-linux-${NARCH}.tar.xz"
  curl -fsSL "https://nodejs.org/dist/${NODE_VER}/SHASUMS256.txt" | grep "node-${NODE_VER}-linux-${NARCH}.tar.xz" | sha256sum -c -
  sudo tar -xJf "node-${NODE_VER}-linux-${NARCH}.tar.xz" -C /usr/local --strip-components=1
  rm "node-${NODE_VER}-linux-${NARCH}.tar.xz"
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt
npm ci && npm run build

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  chmod 600 backend/.env
  echo ">>> Edit backend/.env now (Telegram token/chat id; Angel keys optional). LIVE_TRADING stays false."
fi

# systemd service: starts on boot, restarts if it crashes, listens on localhost only
sudo tee /etc/systemd/system/c0mr4des.service >/dev/null <<UNIT
[Unit]
Description=C0MR4DE Terminal (paper autopilot)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
Restart=always
RestartSec=10
Environment=TZ=Asia/Kolkata

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now c0mr4des
sleep 5
systemctl --no-pager status c0mr4des | head -5
echo ">>> Done. Logs: journalctl -u c0mr4des -f   |   Test alert: curl -X POST http://127.0.0.1:8100/api/notify/test"
