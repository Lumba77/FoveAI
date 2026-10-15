<#
.SYNOPSIS
    FoveAI Unified Startup — launches proxy (8414) + multigate (8414) + dashboard (8414)
.DESCRIPTION
    Starts all FoveAI services in a single window:
      1. Foveated Memory Proxy  →  http://127.0.0.1:8400
      2. Monitor Dashboard      →  http://127.0.0.1:8414
      3. Multigate (FoveAI Copilot) →  http://127.0.0.1:5177
    Prerequisite: LM Studio must already be running on port 7272.
.EXAMPLE
    .\start-foveai.ps1          # Start all services
    .\start-foveai.ps1 -Check   # Only verify services are reachable
#>
param(
    [switch]$Check
)

$ErrorActionPreference = 'Continue'

# ── Paths ─────────────────────────────────────────────────────────────
$LumaxRoot     = Resolve-Path (Join-Path $PSScriptRoot '..')
$ProxyDir      = Join-Path $LumaxRoot 'Tools' 'foveated-memory'
$MultigateDir  = Join-Path $LumaxRoot 'Frontend' 'multigate'

# ── Ports ────────────────────────────────────────────────────────────
$ProxyPort      = 8400
$DashboardPort  = 8414
$MultigatePort  = 5177
$LMStudioPort   = 7272

# ── Helper: test if a port is responding ─────────────────────────────
function Test-Port {
    param([int]$Port, [string]$Label, [string]$Path = '')
    try {
        $uri = "http://127.0.0.1:$Port/$Path"
        $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        Write-Host "  ✓ $Label (:$Port) — $($r.StatusCode)" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  ✗ $Label (:$Port) — not reachable" -ForegroundColor Red
        return $false
    }
}

# ── Check-only mode ──────────────────────────────────────────────────
if ($Check) {
    Write-Host ''
    Write-Host '=== FoveAI Service Health Check ===' -ForegroundColor Cyan
    Write-Host ''
    Test-Port -Port $LMStudioPort  -Label 'LM Studio'
    Test-Port -Port $ProxyPort      -Label 'XRLF Proxy'       -Path 'health'
    Test-Port -Port $DashboardPort  -Label 'Dashboard'        -Path 'settings.html'
    Test-Port -Port $MultigatePort  -Label 'Multigate (Copilot)'
    Write-Host ''
    return
}

# ── Verify LM Studio is up before starting proxy ─────────────────────
Write-Host ''
Write-Host '=== FoveAI Unified Startup ===' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Checking LM Studio on :7272 ...' -NoNewline
if (-not (Test-Port -Port $LMStudioPort -Label 'LM Studio')) {
    Write-Host ''
    Write-Host '⚠  LM Studio is not running on port 7272.' -ForegroundColor Yellow
    Write-Host '   Start LM Studio first, then re-run this script.' -ForegroundColor Yellow
    Write-Host ''
    return
}

# ── Start Foveated Memory Proxy (8400) ────────────────────────────────
Write-Host ''
Write-Host 'Starting XRLF Foveated Proxy on :8400 ...' -ForegroundColor Cyan
$proxyProc = Start-Process -FilePath 'node' `
    -ArgumentList 'server.js' `
    -WorkingDirectory $ProxyDir `
    -PassThru `
    -NoNewWindow

# Give the proxy a moment to bind
Start-Sleep -Seconds 2
if (-not (Test-Port -Port $ProxyPort -Label 'XRLF Proxy' -Path 'health')) {
    Write-Host 'Proxy failed to start. Check logs in:' -ForegroundColor Red
    Write-Host "  $ProxyDir\proxy.log" -ForegroundColor Gray
    if (-not $proxyProc.HasExited) { $proxyProc.Kill() }
    return
}

# ── Start Multigate Dev Server (5177) ────────────────────────────────
Write-Host ''
Write-Host 'Starting Multigate (FoveAI Copilot) on :5177 ...' -ForegroundColor Cyan
$multigateProc = Start-Process -FilePath 'npm' `
    -ArgumentList 'run','dev' `
    -WorkingDirectory $MultigateDir `
    -PassThru `
    -NoNewWindow

# Give Vite a moment to start
Start-Sleep -Seconds 3
Test-Port -Port $MultigatePort -Label 'Multigate (Copilot)'

# ── Summary ──────────────────────────────────────────────────────────
Write-Host ''
Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host '  FoveAI services running:' -ForegroundColor Cyan
Write-Host "    • LM Studio          →  http://127.0.0.1:$LMStudioPort" -ForegroundColor White
Write-Host "    • XRLF Proxy          →  http://127.0.0.1:$ProxyPort" -ForegroundColor White
Write-Host "    • Dashboard           →  http://127.0.0.1:$DashboardPort" -ForegroundColor White
Write-Host "    • FoveAI Copilot      →  http://127.0.0.1:$MultigatePort" -ForegroundColor White
Write-Host ''
Write-Host '  Chain: Copilot(5177) → /api/foveated → Proxy(8400) → LM Studio(7272)' -ForegroundColor Gray
Write-Host '═══════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Press Ctrl+C to stop all services.' -ForegroundColor Yellow
Write-Host ''

# ── Wait for user to stop ────────────────────────────────────────────
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Write-Host ''
    Write-Host 'Shutting down ...' -ForegroundColor Yellow
    if (-not $proxyProc.HasExited)      { $proxyProc.Kill() }
    if (-not $multigateProc.HasExited)   { $multigateProc.Kill() }
    Write-Host 'All services stopped.' -ForegroundColor Green
}