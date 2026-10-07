#!/usr/bin/env bash
# HealthVision AI — one-time setup on macOS / Linux. Requires Python 3.11+ and Node.js 18+.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e "./backend[dev]"
.venv/bin/python tools/fetch_models.py
(cd frontend && npm install && npm run build)
echo
echo "Setup complete. Start the app with:  ./scripts/run.sh"
