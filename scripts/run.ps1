# Start HealthVision AI on Windows, then open http://127.0.0.1:8600
Set-Location (Join-Path $PSScriptRoot "..")
Start-Process "http://127.0.0.1:8600"
& .\.venv\Scripts\python.exe -m healthvision_server.main
