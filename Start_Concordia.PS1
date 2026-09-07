<#
.SYNOPSIS
  Sleipnir Engine Matrix — Diamond Concordia Launcher
.DESCRIPTION
  Activates the local python virtual environment, binds background database engines,
  and fires up the multi-agent execution cockpit.
#>

$FoveAI_ROOT = $PSScriptRoot
Set-Location $FoveAI_ROOT

Write-Host "🛸 [SLEIPNIR MATRIX] Igniting Diamond Concordia Core Daemon..." -ForegroundColor Green
Write-Host "💎 Local: RTX 4060 8GB | 4096 ctx | TokenSlayer 10x: 35k real → 3500 delivered" -ForegroundColor Cyan
Write-Host "🌱 Manifesting code at 1.0 temperature via self-healing compiler gates." -ForegroundColor DarkGreen
Write-Host "----------------------------------------------------------------------------------" -ForegroundColor Gray

# 1. Enforce native execution bypass for this terminal track
if ((Get-ExecutionPolicy) -ne 'Bypass') {
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
}

# 2. Pre-flight: kill zombie processes on critical ports
# This ensures avatar gets :8080 (mic requires same-origin) and no double-starts
Write-Host "🧹 [PRE-FLIGHT] Clearing stale port occupants..." -ForegroundColor DarkCyan
$criticalPorts = @(8000, 8001, 8004, 8080, 8101, 8103, 8104, 8106, 8109, 8110, 8112, 8113, 8888, 5000)
foreach ($port in $criticalPorts) {
    $netstat = netstat -ano 2>$null | Select-String ":$port\s" | Select-String "LISTENING|TIME_WAIT"
    foreach ($line in $netstat) {
        $foundPid = ($line -split '\s+')[-1]
        if ($foundPid -match '^\d+$' -and $foundPid -ne '0') {
            try {
                Stop-Process -Id $foundPid -Force -ErrorAction SilentlyContinue
                Write-Host "   💀 Cleared PID $foundPid on port $port" -ForegroundColor DarkYellow
            } catch {}
        }
    }
    # After killing, wait for TIME_WAIT to clear (up to 3 seconds)
    # TIME_WAIT on Windows can block rebinding for ~4 minutes if we don't wait
    $deadline = (Get-Date).AddSeconds(3)
    while ((Get-Date) -lt $deadline) {
        $remaining = netstat -ano 2>$null | Select-String ":$port\s" | Select-String "TIME_WAIT"
        if (-not $remaining) { break }
        Start-Sleep -Milliseconds 200
    }
}
Write-Host "   ✅ Pre-flight complete." -ForegroundColor DarkGreen

# 3. Check for local python runtime environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "🐍 Activating localized Python Cognition Environment (.venv)..." -ForegroundColor Gray
    . .venv\Scripts\Activate.ps1
} else {
    Write-Host "⚠️ Warning: Local .venv script path not verified. Utilizing global python mapping." -ForegroundColor Yellow
}

# 4. Fire the concurrent orchestration hub script
Write-Host ""
Write-Host "🌐 Avatar UI (WebXR) will be at: https://foveai.1um6a.se/" -ForegroundColor Cyan
Write-Host "🔊 WebXR Pass-Through & Mic requires HTTPS secure context!" -ForegroundColor DarkCyan
Write-Host ""

if (Test-Path "sleipnir_launcher.js") {
    node sleipnir_launcher.js
} else {
    Write-Host "❌ Critical Failure: sleipnir_launcher.js not found in project root." -ForegroundColor Red
    Write-Host "👉 Dropping down execution fallback via native verification loop..." -ForegroundColor Yellow
    node Tools\foveai-solver\system_verification.js
}