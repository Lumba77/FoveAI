<#
.SYNOPSIS
    DeadSure Watchdog Supervisor — Windows-Native Auto-Restart Guardian

.DESCRIPTION
    Keeps deadsure_watchdog.py alive. If the process exits for any reason,
    it logs the crash and restarts after a configurable delay.
    
    Run with -Install to register as a Windows Scheduled Task (auto-starts at login).
    Run with -Uninstall to remove the scheduled task.

.PARAMETER Install
    Register this script as a Windows Scheduled Task that runs at user logon.

.PARAMETER Uninstall
    Remove the registered scheduled task.

.PARAMETER Port
    Port for the watchdog HTTP service. Default: 8112

.EXAMPLE
    .\start-solver-service.ps1               # Run supervisor interactively
    .\start-solver-service.ps1 -Install      # Install as startup task
    .\start-solver-service.ps1 -Uninstall    # Remove startup task

#>
param(
    [switch]$Install,
    [switch]$Uninstall,
    [int]$Port = 8112
)

# ─── Config ───────────────────────────────────────────────────────────────────
$TASK_NAME     = "FoveAI-DeadSure-Watchdog"
$SCRIPT_ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$FoveAI_ROOT    = Split-Path -Parent $SCRIPT_ROOT
$WATCHDOG_PY   = Join-Path $SCRIPT_ROOT "deadsure_watchdog.py"
$SAFE_SAVES    = Join-Path $FoveAI_ROOT ".SafeSaves"
$HEARTBEAT_LOG = Join-Path $SAFE_SAVES "watchdog_heartbeat.log"
$CRASH_LOG     = Join-Path $SAFE_SAVES "supervisor_crash.log"

# Try root venv first, then Tools-local venv
$PYTHON = @(
    (Join-Path $FoveAI_ROOT ".venv\Scripts\python.exe"),
    (Join-Path $SCRIPT_ROOT ".venv\Scripts\python.exe"),
    "python"
) | Where-Object { Test-Path $_ -ErrorAction SilentlyContinue } | Select-Object -First 1

if (-not $PYTHON) { $PYTHON = "python" }

$RESTART_DELAY = 5   # seconds between crash → restart
$MAX_RESTARTS  = 0   # 0 = unlimited

# ─── Ensure .SafeSaves exists ─────────────────────────────────────────────────
if (-not (Test-Path $SAFE_SAVES)) {
    New-Item -ItemType Directory -Path $SAFE_SAVES -Force | Out-Null
}

# ─── Install as Scheduled Task ────────────────────────────────────────────────
if ($Install) {
    Write-Host "📌 Installing '$TASK_NAME' as a Windows Scheduled Task..." -ForegroundColor Cyan

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -File `"$($MyInvocation.MyCommand.Path)`" -Port $Port" `
        -WorkingDirectory $SCRIPT_ROOT

    $trigger  = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
        -RestartCount 99 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable

    Register-ScheduledTask `
        -TaskName $TASK_NAME `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -RunLevel Highest `
        -Force | Out-Null

    Write-Host "✅ Task registered. The watchdog will auto-start at next login." -ForegroundColor Green
    Write-Host "   To start it now: Start-ScheduledTask -TaskName '$TASK_NAME'" -ForegroundColor Gray
    exit 0
}

# ─── Uninstall Scheduled Task ─────────────────────────────────────────────────
if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "🗑️  Task '$TASK_NAME' removed." -ForegroundColor Yellow
    exit 0
}

# ─── Supervisor Loop ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "🛡️  DeadSure Supervisor v2 — Keeping the watchdog alive, whatever happens." -ForegroundColor Cyan
Write-Host "    Watchdog : $WATCHDOG_PY"
Write-Host "    Python   : $PYTHON"
Write-Host "    Port     : $Port"
Write-Host "    Heartbeat: $HEARTBEAT_LOG"
Write-Host "    Crash log: $CRASH_LOG"
Write-Host ""

$restartCount = 0

while ($true) {
    $startTime = Get-Date
    Write-Host "$(Get-Date -Format 'HH:mm:ss') 🚀 Starting watchdog (attempt #$($restartCount + 1))..." -ForegroundColor Green

    # Write heartbeat: starting
    $hb = @{ ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); status = "starting"; restarts = $restartCount } | ConvertTo-Json -Compress
    Add-Content -Path $HEARTBEAT_LOG -Value $hb

    try {
        $proc = Start-Process `
            -FilePath $PYTHON `
            -ArgumentList "`"$WATCHDOG_PY`" --port $Port" `
            -WorkingDirectory $FoveAI_ROOT `
            -PassThru `
            -NoNewWindow

        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
    } catch {
        $exitCode = -1
    }

    $uptime = ((Get-Date) - $startTime).TotalSeconds
    $restartCount++

    $crashMsg = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') | Exit=$exitCode | Uptime=${uptime}s | Restart #$restartCount"
    Add-Content -Path $CRASH_LOG -Value $crashMsg

    $hb = @{ ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(); status = "crashed"; exit = $exitCode; uptime = [math]::Round($uptime,1); restarts = $restartCount } | ConvertTo-Json -Compress
    Add-Content -Path $HEARTBEAT_LOG -Value $hb

    if ($exitCode -eq 0) {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') 🛑 Watchdog exited cleanly (code 0). Supervisor stopping." -ForegroundColor Yellow
        break
    }

    Write-Host "$(Get-Date -Format 'HH:mm:ss') 💥 Watchdog crashed (code $exitCode, up ${uptime}s). Restarting in ${RESTART_DELAY}s..." -ForegroundColor Red

    Start-Sleep -Seconds $RESTART_DELAY
}
