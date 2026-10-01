# FoveAI Windows Service Installer
# Registers LumaxService as an auto-start Windows Service using NSSM.
# Also installs the tray widget to the user's Startup folder.
#
# Requires: NSSM (Non-Sucking Service Manager) — will auto-download if missing.
# Run as Administrator.

param(
    [switch]$SkipNssmDownload,
    [string]$NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
)

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ServiceRoot = Join-Path $FoveAI_ROOT "Service"
$NssmDir = Join-Path $ServiceRoot "nssm"
$NssmExe = Join-Path $NssmDir "nssm.exe"
$ServiceName = "LumaxService"
$ServiceScript = Join-Path $ServiceRoot "LumaxService.ps1"
$TrayScript = Join-Path $ServiceRoot "LumaxTray.ps1"
$StartupFolder = [Environment]::GetFolderPath("Startup")

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "ERROR: Must run as Administrator." -ForegroundColor Red
    Write-Host "Right-click PowerShell → 'Run as administrator', then retry." -ForegroundColor Yellow
    exit 1
}

Write-Host "=== FoveAI Service Installer ===" -ForegroundColor Cyan
Write-Host "Root: $FoveAI_ROOT" -ForegroundColor Gray

# --- Download NSSM if missing ---
if (-not (Test-Path $NssmExe)) {
    if ($SkipNssmDownload) {
        Write-Host "NSSM not found and -SkipNssmDownload specified. Please place nssm.exe at: $NssmExe" -ForegroundColor Red
        exit 1
    }
    Write-Host "Downloading NSSM..." -ForegroundColor Yellow
    if (-not (Test-Path $NssmDir)) { New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null }
    $zipPath = Join-Path $ServiceRoot "nssm.zip"
    try {
        Invoke-WebRequest -Uri $NssmUrl -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $NssmDir -Force
        # Find nssm.exe inside extracted folder
        $found = Get-ChildItem -Path $NssmDir -Recurse -Filter "nssm.exe" | Select-Object -First 1
        if ($found) {
            Move-Item $found.FullName $NssmExe -Force
            Get-ChildItem -Path $NssmDir -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            Write-Host "NSSM installed: $NssmExe" -ForegroundColor Green
        } else {
            throw "nssm.exe not found in archive"
        }
    } catch {
        Write-Host "Failed to download NSSM: $_" -ForegroundColor Red
        Write-Host "Manually download from https://nssm.cc and place nssm.exe at: $NssmExe" -ForegroundColor Yellow
        exit 1
    }
}

# --- Remove existing service if present ---
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing service..." -ForegroundColor Yellow
    & $NssmExe remove $ServiceName confirm 2>$null
    Start-Sleep -Seconds 2
}

# --- Install service ---
Write-Host "Installing service: $ServiceName..." -ForegroundColor Cyan
$psPath = (Get-Command powershell.exe).Source
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ServiceScript`""

& $NssmExe install $ServiceName $psPath
& $NssmExe set $ServiceName AppParameters $arguments
& $NssmExe set $ServiceName AppDirectory $FoveAI_ROOT
& $NssmExe set $ServiceName DisplayName "FoveAI Background Service"
& $NssmExe set $ServiceName Description "Keeps FoveAI services (SOUL, EARS, MEMORY, MOUTH, WEBUI, VAD) running from boot. Handles SLEEP/AWAKE lifecycle."
& $NssmExe set $ServiceName Start SERVICE_AUTO_START
& $NssmExe set $ServiceName ObjectName "LocalSystem"
& $NssmExe set $ServiceName Type SERVICE_WIN32_OWN_PROCESS
& $NssmExe set $ServiceName AppStdout (Join-Path $FoveAI_ROOT ".logs\foveai_service_nssm.log")
& $NssmExe set $ServiceName AppStderr (Join-Path $FoveAI_ROOT ".logs\foveai_service_nssm_err.log")
& $NssmExe set $ServiceName AppRotateFiles 1
& $NssmExe set $ServiceName AppRotateOnline 0
& $NssmExe set $ServiceName AppRotateSeconds 86400

Write-Host "Service installed." -ForegroundColor Green

# --- Start service ---
Write-Host "Starting service..." -ForegroundColor Cyan
Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host "Service is RUNNING." -ForegroundColor Green
} else {
    Write-Host "Service may not have started yet. Check: .logs\foveai_service_nssm_err.log" -ForegroundColor Yellow
}

# --- Install tray widget to Startup ---
$trayShortcut = Join-Path $StartupFolder "LumaxTray.lnk"
$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($trayShortcut)
$shortcut.TargetPath = $psPath
$shortcut.Arguments = "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$TrayScript`""
$shortcut.WorkingDirectory = $FoveAI_ROOT
$shortcut.IconLocation = "powershell.exe,0"
$shortcut.Description = "FoveAI System Tray Widget"
$shortcut.Save()

Write-Host "Tray widget added to Startup: $trayShortcut" -ForegroundColor Green

# --- Install Guardian as Scheduled Task (every 5 min + boot) ---
$guardianScript = Join-Path $ServiceRoot "LumaxGuardian.ps1"
if (Test-Path $guardianScript) {
    Write-Host "Installing FoveAI Guardian watchdog..." -ForegroundColor Cyan
    $taskName = "LumaxGuardian"
    try {
        # Remove existing task if any
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1

        $action = New-ScheduledTaskAction -Execute $psPath -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$guardianScript`"" -WorkingDirectory $FoveAI_ROOT
        $bootTrigger = New-ScheduledTaskTrigger -AtStartup
        $idleTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden -RunOnlyIfNetworkAvailable:$false
        $task = New-ScheduledTask -Action $action -Principal $principal -Trigger $bootTrigger, $idleTrigger -Settings $settings
        Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
        Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Write-Host "Guardian installed: runs every 5 minutes + at boot." -ForegroundColor Green
    } catch {
        Write-Host "Guardian install warning: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# --- Optionally start tray now ---
$trayRunning = Get-Process -Name "powershell" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*LumaxTray.ps1*"
}
if (-not $trayRunning) {
    Write-Host "Starting tray widget..." -ForegroundColor Cyan
    Start-Process $psPath -ArgumentList "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$TrayScript`"" -WindowStyle Hidden
}

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host "Service:    sc.exe query $ServiceName" -ForegroundColor Gray
Write-Host "Guardian:   Get-ScheduledTask LumaxGuardian" -ForegroundColor Gray
Write-Host "Tray:       System tray dot (green=on, red=off, amber=sleep)" -ForegroundColor Gray
Write-Host "Logs:       $FoveAI_ROOT\.logs\" -ForegroundColor Gray
Write-Host "Config:     $ServiceRoot\foveai_service_config.json" -ForegroundColor Gray
Write-Host ""
Write-Host "To uninstall:   Service\Uninstall_Lumax_Service.ps1" -ForegroundColor Gray
Write-Host "To open console: Start_FoveAI.ps1" -ForegroundColor Gray
