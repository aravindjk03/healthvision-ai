#!/usr/bin/env bash
# Start HealthVision AI, then open http://127.0.0.1:8600
cd "$(dirname "$0")/.."
exec .venv/bin/python -m healthvision.main
