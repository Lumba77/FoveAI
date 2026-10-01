# Start FoveAI Windows NPU Bridge
# This script runs on the Windows host to expose NPU/GPU capabilities to WSL.

Write-Host "=== FoveAI Windows NPU Bridge ===" -ForegroundColor Cyan
Write-Host "Setting up host environment..." -ForegroundColor Gray

# Check for Python
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found on Windows host. Please install Python." -ForegroundColor Red
    exit
}

# Install dependencies if missing
Write-Host "Verifying host dependencies (FastAPI, Uvicorn, ONNX Runtime)..." -ForegroundColor Gray
python -m pip install fastapi uvicorn onnxruntime-directml --quiet

# Identify Host IP for WSL reference
$HostIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet").IPAddress
if (!$HostIP) {
    $HostIP = "localhost"
}

Write-Host "Bridge will be reachable from: http://$($HostIP):11436" -ForegroundColor Green
Write-Host "Starting server..." -ForegroundColor Gray

# Start the bridge
python Tools/npu_bridge.py
