# ═══════════════════════════════════════════════════════
# FOVEAI ONE-COMMAND LAUNCHER
# ═══════════════════════════════════════════════════════
# Starts the full FoveAI companion stack:
#   1. XRLF Runtime (Gemma 4 12B + CUDA + Kokoro TTS) → :8402
#   2. Foveated Memory Proxy + Dashboard              → :8400/:8401
#
# Usage:
#   .\start_foveai.ps1              # Start everything
#   .\start_foveai.ps1 -Stop        # Stop everything
#   .\start_foveai.ps1 -Status      # Check status
#
# Prerequisites:
#   - CUDA toolkit installed
#   - llama-cpp-python 0.3.34 built with CUDA (see build_cuda_wheel.bat)
#   - Kokoro package installed (pip install kokoro)
#   - Node.js installed (for the proxy)
# ═══════════════════════════════════════════════════════

param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

# ── Paths ──────────────────────────────────────────────
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython  = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$ProxyDir    = Join-Path $ScriptDir "foveated-memory"
$RuntimeLog  = Join-Path $ScriptDir "runtime_log.txt"
$RuntimeErr  = Join-Path $ScriptDir "runtime_err.txt"

# ── Status check ───────────────────────────────────────
function Get-StackStatus {
    $services = @(
        @{ Name = "XRLF Runtime";    Port = 8402; Type = "python" },
        @{ Name = "WebSocket IPC";   Port = 8403; Type = "python" },
        @{ Name = "Proxy/Dashboard"; Port = 8400; Type = "node" }
    )
    $allRunning = $true
    foreach ($svc in $services) {
        $conn = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $svc.Port }
        if ($conn) {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            Write-Host "  $($svc.Name) (:$($svc.Port))  RUNNING  PID=$($conn.OwningProcess)" -ForegroundColor Green
        } else {
            Write-Host "  $($svc.Name) (:$($svc.Port))  STOPPED" -ForegroundColor Red
            $allRunning = $false
        }
    }
    return $allRunning
}

# ── Stop mode ──────────────────────────────────────────
if ($Stop) {
    Write-Host "`n  Stopping FoveAI stack..." -ForegroundColor Yellow
    foreach ($port in @(8400, 8401, 8402, 8403)) {

        $conn = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $port }
        if ($conn) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped port $port (PID $($conn.OwningProcess))" -ForegroundColor Gray
        }
    }
    Write-Host "  Done.`n" -ForegroundColor Green
    return
}

# ── Status mode ────────────────────────────────────────
if ($Status) {
    Write-Host "`n  FoveAI Stack Status:" -ForegroundColor Cyan
    Get-StackStatus | Out-Null
    Write-Host ""
    return
}

# ── Start mode ─────────────────────────────────────────
Write-Host "`n  ═══ FoveAI Companion Stack ═══" -ForegroundColor Cyan
Write-Host "  Gemma 4 12B (CUDA) + Kokoro TTS + Foveated Memory`n" -ForegroundColor Cyan

# Check if already running
$runtimeRunning = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 8402 }
$proxyRunning   = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 8400 }

if ($runtimeRunning -and $proxyRunning) {
    Write-Host "  Stack is already running." -ForegroundColor Yellow
    Get-StackStatus | Out-Null
    Write-Host "`n  Companion:  http://127.0.0.1:8401/companion.html" -ForegroundColor Cyan
    Write-Host "  Dashboard:   http://127.0.0.1:8401`n" -ForegroundColor Cyan
    return
}

# ── 1. Start XRLF Runtime ──────────────────────────────
if (-not $runtimeRunning) {
    Write-Host "  [1/2] Starting XRLF Runtime (Gemma 4 12B + CUDA + WebSocket IPC)..." -ForegroundColor Yellow

    # Clear Python cache to ensure code changes are picked up
    Get-ChildItem $ScriptDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

    Remove-Item $RuntimeLog -Force -ErrorAction SilentlyContinue
    Remove-Item $RuntimeErr -Force -ErrorAction SilentlyContinue

    # Build the command with env vars for Kokoro/HuggingFace offline mode
    # --ws-port 8403 enables the WebSocket IPC server for Quest/multigate clients
    $envVars = "set HF_HUB_OFFLINE=1 && set TRANSFORMERS_OFFLINE=1 && set REQUESTS_CA_BUNDLE=C:/Users/danie/program/LUMAX/cloudflare-gateway-ca.pem && set SSL_CERT_FILE=C:/Users/danie/program/LUMAX/cloudflare-gateway-ca.pem && set CURL_CA_BUNDLE=C:/Users/danie/program/LUMAX/cloudflare-gateway-ca.pem"
    $cmd = "$envVars && `"$VenvPython`" -u run_xrlf.py --ws-port 8403"

    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd `
        -WorkingDirectory $ScriptDir `
        -RedirectStandardOutput $RuntimeLog `
        -RedirectStandardError $RuntimeErr `
        -WindowStyle Hidden

    # Wait for runtime to be ready
    Write-Host "        Loading model (this takes ~30-60s)..." -ForegroundColor Gray
    $maxWait = 120
    $waited = 0
    do {
        Start-Sleep -Seconds 5
        $waited += 5
        try {
            $h = Invoke-WebRequest -Uri "http://127.0.0.1:8402/health" -TimeoutSec 3 -UseBasicParsing
            if ($h.StatusCode -eq 200) { break }
        } catch {}
        if ($waited -ge $maxWait) {
            Write-Host "  Runtime failed to start within ${maxWait}s. Check $RuntimeErr" -ForegroundColor Red
            return
        }
        Write-Host "        ...waiting (${waited}s)" -ForegroundColor DarkGray
    } while ($true)

    Write-Host "        Runtime ready on :8402" -ForegroundColor Green

    # Show TTS engine
    $ttsLine = Get-Content $RuntimeLog -ErrorAction SilentlyContinue | Select-String "TTS engine" | Select-Object -First 1
    if ($ttsLine) { Write-Host "        $($ttsLine.Line.Trim())" -ForegroundColor Gray }
} else {
    Write-Host "  [1/2] XRLF Runtime already running on :8402" -ForegroundColor Green
}

# ── 2. Start Foveated Memory Proxy ─────────────────────
if (-not $proxyRunning) {
    Write-Host "  [2/2] Starting Foveated Memory Proxy + Dashboard..." -ForegroundColor Yellow

    Start-Process -FilePath "node" -ArgumentList "server.js" `
        -WorkingDirectory $ProxyDir `
        -WindowStyle Hidden

    Start-Sleep -Seconds 3

    $proxyConn = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 8400 }
    if ($proxyConn) {
        Write-Host "        Proxy ready on :8400, Dashboard on :8401" -ForegroundColor Green
    } else {
        Write-Host "        Proxy failed to start. Check node server.js manually." -ForegroundColor Red
        return
    }
} else {
    Write-Host "  [2/2] Proxy already running on :8400" -ForegroundColor Green
}

# ── Done ───────────────────────────────────────────────
Write-Host "`n  ═══ Stack Ready ═══" -ForegroundColor Green
Write-Host ""
Get-StackStatus | Out-Null
Write-Host ""
Write-Host "  Companion:  http://127.0.0.1:8401/companion.html" -ForegroundColor Cyan
Write-Host "  Dashboard:   http://127.0.0.1:8401" -ForegroundColor Cyan
Write-Host "  API:         http://127.0.0.1:8400/v1/chat/completions" -ForegroundColor Cyan
Write-Host "  Runtime:     http://127.0.0.1:8402/health" -ForegroundColor Cyan
Write-Host "  WebSocket:   ws://<your-pc-ip>:8403/ws  (Quest/multigate)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Stop with:   .\start_foveai.ps1 -Stop" -ForegroundColor Gray
Write-Host "  Status:      .\start_foveai.ps1 -Status`n" -ForegroundColor Gray
