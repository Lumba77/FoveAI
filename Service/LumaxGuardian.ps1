# FoveAI Guardian — Autonomous Watchdog & Healer
# Runs from Task Scheduler every 5 minutes, and at boot.
# Survives Windows Updates by re-registering NSSM if missing.
# If the service is dead, it heals. If NSSM is gone, it reinstalls.
#
# Logs: .logs\foveai_guardian.log
# State: .logs\foveai_guardian_state.json

param(
    [switch]$InstallOnly,
    [switch]$ForceHeal
)

Add-Type -AssemblyName System.Windows.Forms

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LOG_DIR = Join-Path $FoveAI_ROOT ".logs"
$STATE_FILE = Join-Path $LOG_DIR "foveai_guardian_state.json"
$GUARDIAN_LOG = Join-Path $LOG_DIR "foveai_guardian.log"
$SVC_NAME = "LumaxService"
$SVC_SCRIPT = Join-Path $FoveAI_ROOT "Service\LumaxService.ps1"
$INSTALLER = Join-Path $FoveAI_ROOT "Service\Install_Lumax_Service.ps1"
$NSSM_DIR = Join-Path $FoveAI_ROOT "Service\nssm"
$NSSM_EXE = Join-Path $NSSM_DIR "nssm.exe"
$TRAY_SCRIPT = Join-Path $FoveAI_ROOT "Service\LumaxTray.ps1"

# --- Backup Configuration ---
$BACKUP_ROOT = Join-Path $env:USERPROFILE "FoveAI-Backups"
$BACKUP_INCR_DIR = Join-Path $BACKUP_ROOT "incremental"
$BACKUP_FULL_DIR = Join-Path $BACKUP_ROOT "full"
$BACKUP_STATE_FILE = Join-Path $LOG_DIR "foveai_backup_state.json"
$BACKUP_LOG = Join-Path $LOG_DIR "foveai_backup.log"

$BACKUP_PATTERNS = @("*.ps1", "*.py", "*.json", "*.md", "*.html", "*.env", "*.yml", "*.txt", "*.cmd", "*.gd", "*.css", "*.js")
$BACKUP_EXCLUDE_DIRS = @(".logs", ".venv", "__pycache__", "node_modules", ".git", "Backups", "backup", "tmp", "temp", ".cache", "*.gguf", "*.zip", "*.wav", "*.mp3", "*.png", "*.jpg", "*.vrm", "*.db")

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Write-GuardianLog {
    param($Level, $Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    try { Add-Content -Path $GUARDIAN_LOG -Value $line -ErrorAction SilentlyContinue } catch {}
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-GuardianState {
    if (Test-Path $STATE_FILE) {
        try { return Get-Content $STATE_FILE -Raw | ConvertFrom-Json } catch {}
    }
    return @{ last_run = 0; heal_count = 0; install_attempts = 0; boot_checks = 0 }
}

function Set-GuardianState {
    param($State)
    try { $State | ConvertTo-Json -Depth 3 | Set-Content $STATE_FILE -Force } catch {}
}

function Test-ServiceExists {
    return $null -ne (Get-Service -Name $SVC_NAME -ErrorAction SilentlyContinue)
}

function Test-ServiceRunning {
    $svc = Get-Service -Name $SVC_NAME -ErrorAction SilentlyContinue
    return ($svc -and $svc.Status -eq "Running")
}

function Test-NssmPresent {
    return (Test-Path $NSSM_EXE)
}

function Test-PortsAlive {
    $ports = @(8000, 8080, 8110, 8103, 8109, 8004, 5176)
    $alive = @()
    foreach ($p in $ports) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $ar = $tcp.BeginConnect("127.0.0.1", $p, $null, $null)
            if ($ar.AsyncWaitHandle.WaitOne(500) -and $tcp.Connected) {
                $alive += $p
            }
            $tcp.Close()
        }
        catch {}
    }
    return $alive
}

function Install-NssmIfMissing {
    if (Test-Path $NSSM_EXE) { return $true }
    Write-GuardianLog "WARN" "NSSM missing — attempting download..."
    if (-not (Test-Path $NSSM_DIR)) { New-Item -ItemType Directory -Path $NSSM_DIR -Force | Out-Null }
    $zipPath = Join-Path $NSSM_DIR "nssm.zip"
    try {
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zipPath -UseBasicParsing -TimeoutSec 30
        Expand-Archive -Path $zipPath -DestinationPath $NSSM_DIR -Force
        $found = Get-ChildItem -Path $NSSM_DIR -Recurse -Filter "nssm.exe" | Select-Object -First 1
        if ($found) {
            Move-Item $found.FullName $NSSM_EXE -Force
            Get-ChildItem -Path $NSSM_DIR -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            Write-GuardianLog "INFO" "NSSM downloaded and installed"
            return $true
        }
    }
    catch {
        Write-GuardianLog "ERROR" "NSSM download failed: $($_.Exception.Message)"
    }
    return $false
}

function Register-LumaxService {
    if (-not (Test-NssmPresent)) {
        if (-not (Install-NssmIfMissing)) { return $false }
    }
    if (Test-ServiceExists) {
        Write-GuardianLog "INFO" "Service already registered — ensuring startup=auto"
        try {
            & $NSSM_EXE set $SVC_NAME Start SERVICE_AUTO_START | Out-Null
            return $true
        }
        catch { return $false }
    }

    Write-GuardianLog "INFO" "Registering LumaxService via NSSM..."
    $psPath = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
    if (-not $psPath) { $psPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" }
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$SVC_SCRIPT`""

    try {
        & $NSSM_EXE install $SVC_NAME $psPath | Out-Null
        & $NSSM_EXE set $SVC_NAME AppParameters $arguments | Out-Null
        & $NSSM_EXE set $SVC_NAME AppDirectory $FoveAI_ROOT | Out-Null
        & $NSSM_EXE set $SVC_NAME DisplayName "FoveAI Background Service" | Out-Null
        & $NSSM_EXE set $SVC_NAME Description "Keeps FoveAI services running from boot. Handles SLEEP/AWAKE lifecycle." | Out-Null
        & $NSSM_EXE set $SVC_NAME Start SERVICE_AUTO_START | Out-Null
        & $NSSM_EXE set $SVC_NAME ObjectName "LocalSystem" | Out-Null
        & $NSSM_EXE set $SVC_NAME Type SERVICE_WIN32_OWN_PROCESS | Out-Null
        & $NSSM_EXE set $SVC_NAME AppStdout (Join-Path $LOG_DIR "foveai_service_nssm.log") | Out-Null
        & $NSSM_EXE set $SVC_NAME AppStderr (Join-Path $LOG_DIR "foveai_service_nssm_err.log") | Out-Null
        & $NSSM_EXE set $SVC_NAME AppRotateFiles 1 | Out-Null
        & $NSSM_EXE set $SVC_NAME AppRotateOnline 0 | Out-Null
        & $NSSM_EXE set $SVC_NAME AppRotateSeconds 86400 | Out-Null

        Write-GuardianLog "INFO" "Service registered successfully"
        return $true
    }
    catch {
        Write-GuardianLog "ERROR" "Service registration failed: $($_.Exception.Message)"
        return $false
    }
}

function Start-LumaxService {
    if (Test-ServiceRunning) {
        Write-GuardianLog "INFO" "Service already running"
        return $true
    }
    if (-not (Test-ServiceExists)) {
        if (-not (Register-LumaxService)) { return $false }
    }
    try {
        Start-Service -Name $SVC_NAME -ErrorAction Stop
        Start-Sleep -Seconds 3
        if (Test-ServiceRunning) {
            Write-GuardianLog "INFO" "Service started successfully"
            return $true
        }
    }
    catch {
        Write-GuardianLog "ERROR" "Failed to start service: $($_.Exception.Message)"
    }
    return $false
}

function Start-LumaxTrayIfMissing {
    $trayWmi = Get-WmiObject Win32_Process -Filter "CommandLine LIKE '%LumaxTray.ps1%'" -ErrorAction SilentlyContinue
    if ($trayWmi) { return }
    Write-GuardianLog "INFO" "Tray not detected — respawning..."
    $psPath = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
    if (-not $psPath) { $psPath = "powershell.exe" }
    try {
        Start-Process -FilePath $psPath -ArgumentList "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$TRAY_SCRIPT`"" -WorkingDirectory $FoveAI_ROOT -ErrorAction SilentlyContinue
        Write-GuardianLog "INFO" "Tray respawned"
    }
    catch {
        Write-GuardianLog "WARN" "Tray respawn failed: $($_.Exception.Message)"
    }
}

function Clear-ZombiePorts {
    param([int[]]$Ports)
    $killed = 0
    foreach ($port in $Ports) {
        try {
            $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" -or $_.State -eq "Established" }
            if (-not $conn) { continue }
            foreach ($c in $conn) {
                $ownerPid = $c.OwningProcess
                if ($ownerPid -eq 0 -or $ownerPid -eq 4) { continue }
                $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
                if (-not $proc) { continue }
                $cmd = $proc.CommandLine
                if ($proc.ProcessName -eq "python" -and ($cmd -like "*FoveAI*" -or $cmd -like "*compagent*" -or $cmd -like "*uvicorn*" -or $cmd -like "*xr_app*" -or $cmd -like "*motor_daemon*" -or $cmd -like "*smart_context*" -or $cmd -like "*stardust_encoder*" -or $cmd -like "*foveai_mcp_server*" -or $cmd -like "*foveai_mouth*")) {
                    Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
                    Write-GuardianLog "WARN" "Killed zombie PID $ownerPid holding port $port"
                    $killed++
                    Start-Sleep -Seconds 1
                }
            }
        }
        catch {}
    }
    return $killed
}

function Clear-OrphanedPython {
    # Kill any Python process that references FoveAI but has no parent service
    $svcPids = @()
    $svc = Get-Service -Name $SVC_NAME -ErrorAction SilentlyContinue
    if ($svc) {
        try {
            $svcWmi = Get-WmiObject Win32_Process -Filter "Name LIKE '%nssm%'" -ErrorAction SilentlyContinue
            if ($svcWmi) { $svcPids += $svcWmi.ProcessId }
        }
        catch {}
    }
    $orphans = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $cmd = $_.CommandLine
        ($cmd -like "*FoveAI*" -or $cmd -like "*compagent*" -or $cmd -like "*uvicorn*" -or $cmd -like "*web_app*") -and
        ($svcPids -notcontains $_.Parent.Id)
    }
    foreach ($o in $orphans) {
        Stop-Process -Id $o.Id -Force -ErrorAction SilentlyContinue
        Write-GuardianLog "WARN" "Killed orphaned Python PID $($o.Id)"
    }
    return ($orphans | Measure-Object).Count
}

function Heal-Ports {
    $expected = @(8000, 8080, 8110, 8103, 8109, 8004, 5176)
    # Pre-clear: kill zombies holding any expected port
    $zombiesKilled = Clear-ZombiePorts $expected
    if ($zombiesKilled -gt 0) { Start-Sleep -Seconds 3 }

    $alive = Test-PortsAlive
    $missing = $expected | Where-Object { $alive -notcontains $_ }
    if ($missing.Count -eq 0) {
        Write-GuardianLog "INFO" "All core ports alive: $($alive -join ', ')"
        return $true
    }
    Write-GuardianLog "WARN" "Missing ports: $($missing -join ', ') — service may need restart"
    # If service is running but ports dead, the Python processes crashed
    if (Test-ServiceRunning) {
        Write-GuardianLog "WARN" "Service running but ports dead — restarting service..."
        try {
            Stop-Service -Name $SVC_NAME -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Start-Service -Name $SVC_NAME -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 5
            $aliveAfter = Test-PortsAlive
            $stillMissing = $expected | Where-Object { $aliveAfter -notcontains $_ }
            if ($stillMissing.Count -eq 0) {
                Write-GuardianLog "INFO" "Service restart healed all ports"
                return $true
            }
            else {
                Write-GuardianLog "WARN" "Still missing after restart: $($stillMissing -join ', ')"
            }
        }
        catch {
            Write-GuardianLog "ERROR" "Restart failed: $($_.Exception.Message)"
        }
    }
    return $false
}

function Show-GuardianBalloon {
    param([string]$Text, [string]$Title = "FoveAI Guardian")
    try {
        $icon = New-Object System.Windows.Forms.NotifyIcon
        $icon.Icon = [System.Drawing.SystemIcons]::Information
        $icon.Visible = $true
        $icon.BalloonTipTitle = $Title
        $icon.BalloonTipText = $Text
        $icon.ShowBalloonTip(5000)
        Start-Sleep -Seconds 1
        $icon.Dispose()
    }
    catch {}
}

# --- Backup Functions ---

function Write-BackupLog {
    param($Level, $Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    try { Add-Content -Path $BACKUP_LOG -Value $line -ErrorAction SilentlyContinue } catch {}
}

function Get-CloudBackupPaths {
    $cloudPaths = @()
    # OneDrive
    foreach ($key in @("OneDrive", "OneDriveConsumer", "OneDriveCommercial")) {
        $p = [Environment]::GetEnvironmentVariable($key)
        if ($p -and (Test-Path $p)) {
            $cloudPaths += (Join-Path $p "FoveAI-Backups")
        }
    }
    # Google Drive
    $gd = Join-Path $env:USERPROFILE "Google Drive"
    $gd2 = Join-Path $env:USERPROFILE "My Drive"
    if ((Test-Path $gd)) { $cloudPaths += (Join-Path $gd "FoveAI-Backups") }
    if ((Test-Path $gd2)) { $cloudPaths += (Join-Path $gd2 "FoveAI-Backups") }
    return $cloudPaths | Select-Object -Unique
}

function Get-TrackedFiles {
    $tracked = @()
    foreach ($pat in $BACKUP_PATTERNS) {
        $tracked += Get-ChildItem -Path $FoveAI_ROOT -Recurse -Filter $pat -File -ErrorAction SilentlyContinue | Where-Object {
            $f = $_
            $excluded = $false
            foreach ($ex in $BACKUP_EXCLUDE_DIRS) {
                if ($f.FullName -like "*\$ex\*" -or $f.FullName -like "*\$ex") { $excluded = $true; break }
                if ($ex -like "*.*" -and $f.Name -like $ex) { $excluded = $true; break }
            }
            -not $excluded
        }
    }
    return $tracked | Select-Object -Property FullName, Length, LastWriteTime -Unique
}

function Get-BackupState {
    if (Test-Path $BACKUP_STATE_FILE) {
        try { return Get-Content $BACKUP_STATE_FILE -Raw | ConvertFrom-Json } catch {}
    }
    return @{
        file_hashes      = @{}
        last_full_backup = 0
        last_incr_backup = 0
        total_backups    = 0
        bytes_saved      = 0
    }
}

function Set-BackupState {
    param($State)
    try { $State | ConvertTo-Json -Depth 5 | Set-Content $BACKUP_STATE_FILE -Force } catch {}
}

function Get-FileHashQuick {
    param([string]$Path)
    try {
        return (Get-FileHash -Path $Path -Algorithm SHA256 -ErrorAction Stop).Hash
    }
    catch { return $null }
}

function Test-BackupNeeded {
    param([hashtable]$State)
    $files = Get-TrackedFiles
    $changed = 0
    $total = 0
    foreach ($f in $files) {
        $total++
        $h = Get-FileHashQuick $f.FullName
        if (-not $h) { continue }
        $rel = $f.FullName.Substring($FoveAI_ROOT.Length + 1)
        $old = $State.file_hashes."$rel"
        if (-not $old -or $old -ne $h) {
            $changed++
        }
    }
    Write-BackupLog "INFO" "Backup scan: $changed/$total files changed"
    return ($changed -gt 0)
}

function Backup-ScriptsIncremental {
    param([hashtable]$State)
    if (-not (Test-Path $BACKUP_INCR_DIR)) { New-Item -ItemType Directory -Path $BACKUP_INCR_DIR -Force | Out-Null }
    $stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $destDir = Join-Path $BACKUP_INCR_DIR $stamp
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null

    $files = Get-TrackedFiles
    $copied = 0
    $bytes = 0
    foreach ($f in $files) {
        $h = Get-FileHashQuick $f.FullName
        if (-not $h) { continue }
        $rel = $f.FullName.Substring($FoveAI_ROOT.Length + 1)
        $old = $State.file_hashes."$rel"
        if (-not $old -or $old -ne $h) {
            $destFile = Join-Path $destDir $rel
            $destParent = Split-Path $destFile -Parent
            if (-not (Test-Path $destParent)) { New-Item -ItemType Directory -Path $destParent -Force | Out-Null }
            Copy-Item $f.FullName $destFile -Force
            $State.file_hashes."$rel" = $h
            $copied++
            $bytes += $f.Length
        }
    }

    # Write manifest
    $manifest = @{
        timestamp     = $stamp
        type          = "incremental"
        source_root   = $FoveAI_ROOT
        files_copied  = $copied
        bytes_copied  = $bytes
        total_tracked = ($files | Measure-Object).Count
    }
    $manifest | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $destDir "_manifest.json") -Force

    $State.last_incr_backup = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $State.total_backups += 1
    $State.bytes_saved += $bytes
    Set-BackupState $State

    Write-BackupLog "INFO" "Incremental backup complete: $copied files, $bytes bytes → $destDir"
    return $copied
}

function Backup-Full {
    param([hashtable]$State)
    if (-not (Test-Path $BACKUP_FULL_DIR)) { New-Item -ItemType Directory -Path $BACKUP_FULL_DIR -Force | Out-Null }
    $stamp = Get-Date -Format "yyyy-MM-dd"
    $zipPath = Join-Path $BACKUP_FULL_DIR "foveai_full_$stamp.zip"

    $tempList = Join-Path $env:TEMP "foveai_backup_files.txt"
    $files = Get-TrackedFiles
    $files.FullName | Set-Content $tempList -Force

    try {
        $compressParams = @{
            Path             = (Get-Content $tempList)
            DestinationPath  = $zipPath
            Force            = $true
            CompressionLevel = "Optimal"
        }
        Compress-Archive @compressParams -ErrorAction Stop
        $zipSize = (Get-Item $zipPath).Length
        $State.last_full_backup = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        Set-BackupState $State
        Write-BackupLog "INFO" "Full backup complete: $zipPath ($zipSize bytes) from $($files.Count) files"
        Remove-Item $tempList -Force -ErrorAction SilentlyContinue
        return $zipPath
    }
    catch {
        Write-BackupLog "ERROR" "Full backup failed: $($_.Exception.Message)"
        Remove-Item $tempList -Force -ErrorAction SilentlyContinue
        return $null
    }
}

function Sync-ToCloud {
    param([string]$LocalPath)
    $cloudPaths = Get-CloudBackupPaths
    if ($cloudPaths.Count -eq 0) {
        Write-BackupLog "INFO" "No cloud sync target detected (OneDrive/Google Drive not found)"
        return $false
    }
    $synced = 0
    foreach ($cp in $cloudPaths) {
        if (-not (Test-Path $cp)) {
            try { New-Item -ItemType Directory -Path $cp -Force | Out-Null } catch { continue }
        }
        $dest = Join-Path $cp (Split-Path $LocalPath -Leaf)
        try {
            Copy-Item $LocalPath $dest -Force -ErrorAction Stop
            Write-BackupLog "INFO" "Cloud sync OK → $cp"
            $synced++
        }
        catch {
            Write-BackupLog "WARN" "Cloud sync failed for $cp`: $($_.Exception.Message)"
        }
    }
    return ($synced -gt 0)
}

function Clean-OldBackups {
    param([int]$KeepDays = 7)
    # Remove incremental folders older than KeepDays
    if (Test-Path $BACKUP_INCR_DIR) {
        $cutoff = (Get-Date).AddDays(-$KeepDays)
        Get-ChildItem -Path $BACKUP_INCR_DIR -Directory | Where-Object {
            $_.CreationTime -lt $cutoff
        } | ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force
            Write-BackupLog "INFO" "Pruned old incremental: $($_.Name)"
        }
    }
    # Remove full zips older than 30 days
    if (Test-Path $BACKUP_FULL_DIR) {
        $cutoffFull = (Get-Date).AddDays(-30)
        Get-ChildItem -Path $BACKUP_FULL_DIR -Filter "*.zip" | Where-Object {
            $_.CreationTime -lt $cutoffFull
        } | ForEach-Object {
            Remove-Item $_.FullName -Force
            Write-BackupLog "INFO" "Pruned old full backup: $($_.Name)"
        }
    }
}

function Run-BackupCycle {
    Write-BackupLog "INFO" "=== Backup cycle start ==="
    $bstate = Get-BackupState
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $needBackup = Test-BackupNeeded $bstate

    if (-not $needBackup) {
        Write-BackupLog "INFO" "No changes detected — skipping backup"
        return
    }

    # Incremental (every 5 min when changed)
    $incrAgeMin = [math]::Floor(($now - $bstate.last_incr_backup) / 60)
    if ($incrAgeMin -ge 4) {
        $copied = Backup-ScriptsIncremental $bstate
        $bstate = Get-BackupState
        if ($copied -gt 0) {
            $lastIncr = Get-ChildItem -Path $BACKUP_INCR_DIR -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1
            if ($lastIncr) { Sync-ToCloud $lastIncr.FullName }
        }
    }

    # Full (once daily if changed)
    $fullAgeHours = [math]::Floor(($now - $bstate.last_full_backup) / 3600)
    if ($fullAgeHours -ge 23) {
        $zipPath = Backup-Full $bstate
        if ($zipPath) {
            Sync-ToCloud $zipPath
            Clean-OldBackups
        }
    }

    Write-BackupLog "INFO" "=== Backup cycle complete ==="
}

# --- Main Guardian Logic ---
Write-GuardianLog "INFO" "Guardian starting — FoveAI_ROOT=$FoveAI_ROOT"

$state = Get-GuardianState
$state.last_run = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$state.boot_checks += 1

# --- Layer 1: Ensure Service Registration ---
$svcOk = $false
if (Test-ServiceExists) {
    $svcOk = $true
    Write-GuardianLog "INFO" "Service exists"
}
else {
    Write-GuardianLog "WARN" "Service does NOT exist — Windows Update may have removed it"
    if (-not (Test-Admin)) {
        Write-GuardianLog "ERROR" "Guardian not running as Admin — cannot reinstall service"
        Set-GuardianState $state
        exit 1
    }
    if (Register-LumaxService) {
        $state.install_attempts += 1
        $svcOk = $true
    }
}

# --- Layer 2: Ensure Service Running ---
if ($svcOk) {
    if (-not (Test-ServiceRunning)) {
        Write-GuardianLog "WARN" "Service registered but not running — starting..."
        if (Start-LumaxService) {
            $state.heal_count += 1
            Show-GuardianBalloon "FoveAI service was offline. Guardian restarted it." "FoveAI Healed"
        }
    }
    else {
        Write-GuardianLog "INFO" "Service is running"
    }
}

# --- Layer 3: Port Health Check (deep validation) ---
if ($svcOk -and (Test-ServiceRunning)) {
    $portsOk = Heal-Ports
    if (-not $portsOk) {
        $state.heal_count += 1
        Show-GuardianBalloon "Some FoveAI services are not responding. Guardian attempted restart." "FoveAI Warning"
    }
}

# --- Layer 4: Tray Widget ---
Start-LumaxTrayIfMissing

# --- Layer 5: Backup System ---
Run-BackupCycle

Set-GuardianState $state

Write-GuardianLog "INFO" "Guardian cycle complete. heal_count=$($state.heal_count) install_attempts=$($state.install_attempts)"

if ($InstallOnly) {
    Write-Host "Guardian installed as scheduled task. It will run every 5 minutes." -ForegroundColor Green
}
