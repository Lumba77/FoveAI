<#
.SYNOPSIS
  Sleipnir Speculative Swarm — Nursery Launcher
.DESCRIPTION
  Activates the localized python virtual environment and deploys the Forge Nursery
  API along with speculative Swarm Ring nodes.
#>

$LUMAX_ROOT = $PSScriptRoot
Set-Location $LUMAX_ROOT

Write-Host "🛸 [SLEIPNIR NURSERY] Igniting Speculative Swarm Ring Daemon..." -ForegroundColor Green
Write-Host "💎 Local Footprint: Speculative Swarm Nodes & Forge Nursery" -ForegroundColor Cyan
Write-Host "----------------------------------------------------------------------------------" -ForegroundColor Gray

# 1. Enforce native execution bypass for this terminal track
if ((Get-ExecutionPolicy) -ne 'Bypass') {
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
}

# 2. Check for local python runtime environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "🐍 Activating localized Python Cognition Environment (.venv)..." -ForegroundColor Gray
    . .venv\Scripts\Activate.ps1
} else {
    Write-Host "⚠️ Warning: Local .venv script path not verified. Utilizing global python mapping." -ForegroundColor Yellow
}

# 3. Fire the nursery orchestration hub script
if (Test-Path "sleipnir_nursery_launcher.js") {
    node sleipnir_nursery_launcher.js
} else {
    Write-Host "❌ Critical Failure: sleipnir_nursery_launcher.js not found in project root." -ForegroundColor Red
}
