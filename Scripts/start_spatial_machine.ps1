param(
    [switch]$Help
)

if ($Help) {
    Write-Host "Usage: .\start_spatial_machine.ps1"
    Write-Host "Starts the core backend services for the FoveAI."
    Write-Host "  - Foveated Memory Proxy (Port 8400) from FoveAI"
    Write-Host "  - Soul Core / Cognitive Engine (Port 8000)"
    Write-Host "  - Web UI (Port 8080)"
    exit
}

$LUMAX_ROOT = $PSScriptRoot | Split-Path -Parent
$SPATIAL_DIR = Join-Path $LUMAX_ROOT "FoveAI"
$PythonExe = Join-Path $LUMAX_ROOT ".venv\Scripts\python.exe"

# Load .env into the process environment so web_app, soul_core etc. see the settings
$EnvPath = Join-Path $LUMAX_ROOT ".env"
if (Test-Path $EnvPath) {
    Get-Content $EnvPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $k, $v = $line.Split('=', 2)
            [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
        }
    }
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   🚀 BOOTING FoveAI (LUMAX)   " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 0. Start Foveated Memory Proxy (Port 8400) — run from FoveAI
Write-Host "[+] Starting Foveated Memory Proxy (Port 8400) from FoveAI..." -ForegroundColor Magenta
$FovServerPath = Join-Path $LUMAX_ROOT "FoveAI\foveated-memory\server.js"
if (Test-Path $FovServerPath) {
    Start-Process -FilePath "node" -ArgumentList $FovServerPath -WorkingDirectory $LUMAX_ROOT -WindowStyle Hidden
    Write-Host "    → Proxy started from $SPATIAL_DIR" -ForegroundColor Green
} else {
    Write-Host "[-] Could not find foveated-memory server.js at $FovServerPath" -ForegroundColor Red
}

# 1. Start Soul Core (Port 8000)
$SoulCorePath = Join-Path $LUMAX_ROOT "Backend\Cognition\soul_core.py"

if (Test-Path $SoulCorePath) {
    Write-Host "[+] Starting Soul Core (Cognition) -> Port 8000" -ForegroundColor Green
    Start-Process -FilePath $PythonExe -ArgumentList $SoulCorePath -WorkingDirectory (Join-Path $LUMAX_ROOT "Backend\Cognition")
} else {
    Write-Host "[-] Could not find Soul Core at $SoulCorePath" -ForegroundColor Red
}

# 2. Start Web UI (Port 8080)
$WebUIPath = Join-Path $LUMAX_ROOT "Frontend\Webui\web_app.py"
if (Test-Path $WebUIPath) {
    Write-Host "[+] Starting Web Vessel / UI -> Port 8080" -ForegroundColor Green
    Start-Process -FilePath $PythonExe -ArgumentList $WebUIPath -WorkingDirectory (Join-Path $LUMAX_ROOT "Frontend\Webui")
} else {
    Write-Host "[-] Could not find Web UI at $WebUIPath" -ForegroundColor Red
}

Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "All systems initiated. Foveated Memory Proxy on :8400." -ForegroundColor Yellow
Write-Host "Open Unity (FoveAI\client_quest) to build the XR client." -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Cyan
