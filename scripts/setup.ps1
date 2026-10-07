# HealthVision AI — one-time setup on Windows (PowerShell).
# Requires: Python 3.11+ and Node.js 18+ on PATH.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
Write-Host "Creating Python virtual environment (.venv)…"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
Write-Host "Downloading and verifying AI models…"
& .\.venv\Scripts\python.exe tools\fetch_models.py
Write-Host "Building the web interface…"
Push-Location frontend
npm install
npm run build
Pop-Location
Write-Host "`nSetup complete. Start the app with:  .\scripts\run.ps1"
