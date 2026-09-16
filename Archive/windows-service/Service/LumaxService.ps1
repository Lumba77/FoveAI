# FoveAI Background Service
# Headless runner — starts at boot, watchdogs services, handles SLEEP/AWAKE.
# No console UI. Communicates status via status file for the tray widget.
#
# Called by: nssm.exe as Windows Service
# Logs to:   .logs\foveai_service.log

param(
    [string]$ConfigPath = $null
)

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ConfigPath) { $ConfigPath = Join-Path $FoveAI_ROOT "Service\foveai_service_config.json" }

# --- Singleton Lock: prevent duplicate service instances ---
# Use centralized lock manager for authoritative lock handling
$LOG_DIR = Join-Path $FoveAI_ROOT ".logs"
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }
$LockDir = Join-Path $env:LOCALAPPDATA "FoveAI\locks"
if (-not (Test-Path $LockDir)) { New-Item -ItemType Directory -Path $LockDir -Force | Out-Null }
$LockFile = Join-Path $LockDir "foveai_services.lock"

$currentPid = $PID
function Test-ProcessAlive {
    param([int]$PidToCheck)
    try {
        $p = Get-Process -Id $PidToCheck -ErrorAction SilentlyContinue
        return ($null -ne $p -and -not $p.HasExited)
    }
    catch { return $false }
}

# Check for existing lock
if (Test-Path $LockFile) {
    try {
        $lockContent = Get-Content $LockFile -Raw | ConvertFrom-Json
        $lockedPid = $lockContent.pid
        if ($lockedPid -ne $currentPid) {
            if (Test-ProcessAlive $lockedPid) {
                # Another instance is running - we're the duplicate, exit
                exit 0
            }
            # Stale lock - will be overwritten below
        }
    }
    catch {}
}
# Acquire lock
@{ pid = $currentPid; acquired = (Get-Date).ToString("o"); role = "LumaxService" } | ConvertTo-Json | Set-Content $LockFile -Force

# --- Helper: Load .env (overrides any existing Process-level env vars) ---
function Load-Env {
    param($Path)
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
                $idx = $line.IndexOf("=")
                $key = $line.Substring(0, $idx).Trim()
                $val = $line.Substring($idx + 1).Trim().Trim("'").Trim('"')
                # .env is source of truth — always override existing Process env vars
                [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
}
Load-Env (Join-Path $FoveAI_ROOT ".env")

# --- Config ---
$Config = @{
    AvatarName              = "Jen"
    UserName                = "friend"
    AutoWake                = $true
    WatchdogIntervalSec     = 5
    SleepTimeoutSec         = 300
    TrayWatchdogIntervalSec = 30
    WakeOnVoice             = $true
    EnableVad               = $true
    MinLogLevel             = "INFO"
}
if (Test-Path $ConfigPath) {
    try { $fileCfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json; foreach ($prop in $fileCfg.PSObject.Properties) { $Config[$prop.Name] = $prop.Value } } catch {}
}

# --- Logging ---
$SvcLog = Join-Path $LOG_DIR "foveai_service.log"
$StatusFile = Join-Path $LOG_DIR "foveai_service_status.json"

# --- Write-SvcLog function (must be defined before first use) ---
function Write-SvcLog {
    param($Level, $Message)
    $levelRank = @{ "DEBUG" = 0; "INFO" = 1; "WARN" = 2; "ERROR" = 3 }
    if ($levelRank[$Level] -lt $levelRank[$Config.MinLogLevel]) { return }
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    try { Add-Content -Path $SvcLog -Value $line -ErrorAction SilentlyContinue } catch {}
}

# --- Python Interpreter Resolution (prevents uv/.venv mixups) ---
function Get-LumaxPython {
    # Priority: 1) .venv (via FoveAI_VENV_PATH), 2) .venv/unified, 3) .venv, 4) uv-installed, 5) system python
    $venvPath = if ($Env:FoveAI_VENV_PATH) { $Env:FoveAI_VENV_PATH } else { ".venv" }
    $foveaiVenv = Join-Path $FoveAI_ROOT "$venvPath\Scripts\python.exe"
    if (Test-Path $foveaiVenv) { return $foveaiVenv }
    $unifiedVenv = Join-Path $FoveAI_ROOT ".venv\unified\Scripts\python.exe"
    if (Test-Path $unifiedVenv) { return $unifiedVenv }
    $venvPy = Join-Path $FoveAI_ROOT ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    # Look for uv-installed python in known locations
    $uvPythons = @(
        (Join-Path $env:USERPROFILE "AppData\Roaming\uv\python\cpython-*-windows-x86_64-none\python.exe")
        (Join-Path $env:LOCALAPPDATA "uv\python\cpython-*-windows-x86_64-none\python.exe")
    )
    foreach ($glob in $uvPythons) {
        $found = Get-Item $glob -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    # Fallback to system python
    $sysPy = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($sysPy) { return $sysPy }
    return "python.exe"
}
$VENV_PYTHON = Get-LumaxPython
Write-SvcLog "INFO" "Using Python interpreter: $VENV_PYTHON"

# --- Port Occupant Killer (prevents port collision crashes) ---
function Clear-PortOccupant {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" -or $_.State -eq "Established" }
        if (-not $conn) { return $true }
        foreach ($c in $conn) {
            $ownerPid = $c.OwningProcess
            if ($ownerPid -eq 0 -or $ownerPid -eq 4) { continue } # Skip system/Idle
            $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
            if (-not $proc) { continue }
            # Kill zombie Python or Node.js processes that look like FoveAI
            $cmd = $proc.CommandLine
            $isPython = $proc.ProcessName -eq "python" -and ($cmd -like "*FoveAI*" -or $cmd -like "*compagent*" -or $cmd -like "*uvicorn*" -or $cmd -like "*web_app*" -or $cmd -like "*memory*" -or $cmd -like "*body_interface*" -or $cmd -like "*turbochat*" -or $cmd -like "*librarian_daemon*" -or $cmd -like "*ollama_serv*")
            $isNode = $proc.ProcessName -eq "node" -and ($cmd -like "*foveated-memory*" -or $cmd -like "*server.js*" -or $cmd -like "*FoveAI*" -or $cmd -like "*tsproxy*")
            if ($isPython -or $isNode) {
                Write-SvcLog "WARN" "Port $Port occupied by zombie PID $ownerPid ($($proc.ProcessName)) — killing"
                Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 2
        # Verify port is now free
        $still = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -ne 0 -and $_.OwningProcess -ne 4 }
        return (-not $still)
    }
    catch {
        Write-SvcLog "ERROR" "Clear-PortOccupant failed for port $Port : $($_.Exception.Message)"
        return $false
    }
}

# --- Service Definitions (Diamond Concordia Fleet) ---
# Mirrors sleipnir_launcher.js SwarmFleet — all Python services managed here.
# Non-Python nodes (Vite, Cloudflare, Core Solver) are launched by sleipnir_launcher.js directly.
$Services = @{
    "SOVEREIGN"   = @{ Path = "Backend\Cognition"; Port = 8000; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE') }
    "XR_VESSEL"   = @{ Path = "Frontend\XR_Vessel"; Port = 8080; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE') }
    "MOTOR"       = @{ Path = "Backend\Cognition"; Port = 8110; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE') }
    "TOKENSLAYER" = @{ Path = "Backend\Memory"; Port = 8103; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE', 'SLEEP') }
    "STARDUST"    = @{ Path = "Backend\Memory"; Port = 8109; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE', 'SLEEP') }
    "MCP_SERVER"  = @{ Path = "Backend\Memory"; Port = $null; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE', 'SLEEP') }
    "MOUTH"       = @{ Path = "Frontend\Mouth"; Port = 8004; Profiles = @('AWAKE', 'LIVE', 'CREATIVE') }
    "FOVEATED"    = @{ Path = "Tools\foveated-memory"; Port = 8200; Profiles = @('AWAKE', 'LIVE', 'CODE', 'CREATIVE'); Cmd = "server.js" }
}
$Services["SOVEREIGN"].Cmd = "Backend/Cognition/compagent.py"
$Services["XR_VESSEL"].Cmd = "Frontend/XR_Vessel/xr_app.py"
$Services["MOTOR"].Cmd = "-m uvicorn Backend.Cognition.motor_daemon:app --port 8110 --host 127.0.0.1"
$Services["TOKENSLAYER"].Cmd = "-m uvicorn Backend.Memory.smart_context:app --port 8103 --host 127.0.0.1"
$Services["STARDUST"].Cmd = "-m uvicorn Backend.Memory.stardust_encoder:app --port 8109 --host 127.0.0.1"
$Services["MCP_SERVER"].Cmd = "Backend/Memory/foveai_mcp_server.py"
$Services["MOUTH"].Cmd = "Frontend/Mouth/foveai_mouth_kokoro_server.py"

# --- State ---
$Global:ActiveProcesses = @{}
$Global:ServiceStatus = @{}
$Global:CurrentState = "AWAKE"
$Global:ServicesEnabled = $false
$Global:LastUserActivity = Get-Date
$Global:LastVadActivity = Get-Date
$Global:VoiceActive = $Config.EnableVad
$Global:VadBridgeProcess = $null
$Global:VadQueuePath = Join-Path $FoveAI_ROOT "Frontend\CON_vessel\voice_queue.jsonl"
$Global:VadControlPath = Join-Path $FoveAI_ROOT "Frontend\CON_vessel\voice_control.txt"
$Global:LastVadQueueSize = 0
$Global:SleepStartTime = $null
$Global:LastWakeRitual = $null
$Global:RitualPending = $false
$Global:LastTrayCheck = $null
$Global:TrayMissingSince = $null
$Global:LastRestartTime = @{}

# Grace period tracking - prevents false CRASH alarms during startup/reboot
$Global:ServiceGracePeriods = @{}  # ServiceName => StartTime
$Global:BootTime = Get-Date
$Global:StartupGracePeriodSec = 60  # 60 seconds after boot for all services to stabilize
$Global:PerServiceGracePeriodSec = 30  # 30 seconds after each service starts

# Crash tracking and error reporting
$Global:ServiceCrashCounts = @{}  # ServiceName => crash count
$Global:ServiceCrashWindowStart = @{}  # ServiceName => DateTime when counting started
$Global:CrashReportThreshold = 5  # Report after N crashes in 5 minutes
$Global:CrashReportWindowMin = 5  # Time window for counting crashes
$Global:LastCrashReport = @{}  # ServiceName => DateTime of last report
$Global:ErrorReportDir = Join-Path $LOG_DIR "error_reports"
if (-not (Test-Path $Global:ErrorReportDir)) { New-Item -ItemType Directory -Path $Global:ErrorReportDir -Force | Out-Null }

function Write-Status {
    $status = @{
        state     = $Global:CurrentState
        avatar    = $Config.AvatarName
        enabled   = $Global:ServicesEnabled
        voice     = $Global:VoiceActive
        ritual    = $Global:LastWakeRitual
        services  = @{}
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    }
    foreach ($s in $Global:ActiveProcesses.Keys) {
        $p = $Global:ActiveProcesses[$s]
        $status.services[$s] = @{
            running = if ($p -and -not $p.HasExited) { $true } else { $false }
            pid     = if ($p) { $p.Id } else { $null }
            port    = $Services[$s].Port
        }
    }
    $status | ConvertTo-Json -Depth 4 | Set-Content $StatusFile -Force
}

function Test-PortListening {
    param([int]$Port)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $ar = $tcp.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ready = $ar.AsyncWaitHandle.WaitOne(300)
        if ($ready -and $tcp.Connected) {
            $tcp.Close()
            return $true
        }
        $tcp.Close()
    }
    catch {}
    return $false
}

# --- Per-Service Virtual Environment Resolution ---
function Get-ServiceVenvPython {
    param($ServiceName)
    # Dual-Venv Strategy: Mouth (Chatterbox) is isolated, others are unified.
    if ($ServiceName -eq "MOUTH") {
        $mouthVenv = Join-Path $FoveAI_ROOT ".venv\mouth\Scripts\python.exe"
        if (Test-Path $mouthVenv) { return $mouthVenv }
    }

    $venvPath = if ($Env:FoveAI_VENV_PATH) { $Env:FoveAI_VENV_PATH } else { ".venv" }
    $foveaiVenv = Join-Path $FoveAI_ROOT "$venvPath\Scripts\python.exe"
    if (Test-Path $foveaiVenv) {
        return $foveaiVenv
    }
    $unifiedVenv = Join-Path $FoveAI_ROOT ".venv\unified\Scripts\python.exe"
    if (Test-Path $unifiedVenv) {
        return $unifiedVenv
    }
    # Fallback to shared .venv
    return $VENV_PYTHON
}

function Start-LumaxService {
    param($Name)
    if ($Global:ActiveProcesses.ContainsKey($Name)) { return }
    $cfg = $Services[$Name]

    # Pre-clear: kill any zombie Python holding our port
    if ($cfg.Port -and (Test-PortListening $cfg.Port)) {
        $cleared = Clear-PortOccupant $cfg.Port
        if (-not $cleared) {
            Write-SvcLog "WARN" "$Name port $($cfg.Port) still occupied after zombie kill — skipping spawn"
            $Global:ServiceStatus[$Name] = "PORT_BLOCKED"
            return
        }
    }

    # Use dedicated venv Python for this service
    $servicePython = Get-ServiceVenvPython -ServiceName $Name

    $outLog = Join-Path $LOG_DIR "$($Name)_out.log"
    $errLog = Join-Path $LOG_DIR "$($Name)_err.log"
    $envBackup = $Env:PYTHONPATH
    $extraPath = if ($Env:FoveAI_PYTHONPATH_EXTRA) { $Env:FoveAI_PYTHONPATH_EXTRA } else { "D:/Lumax/models" }
    $Env:PYTHONPATH = "$FoveAI_ROOT;$FoveAI_ROOT/Mind;$FoveAI_ROOT/backend/Cognition;$FoveAI_ROOT/frontend/Physical_Interface;$extraPath"
    $executable = $servicePython
    if ($cfg.Cmd -like "*.js") {
        $executable = "node.exe"
    }

    try {
        $p = Start-Process -FilePath $executable -ArgumentList $cfg.Cmd -WorkingDirectory (Join-Path $FoveAI_ROOT $cfg.Path) `
            -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
        $Global:ActiveProcesses[$Name] = $p
        $Global:ServiceStatus[$Name] = "STARTING"  # New status: starting, not crashed
        $Global:ServiceGracePeriods[$Name] = Get-Date  # Start grace period for this service
        $venvType = if ($servicePython -eq $VENV_PYTHON) { "shared" } else { "dedicated" }
        Write-SvcLog "INFO" "Started $Name (PID $($p.Id)) using $venvType venv (grace period: $($Global:PerServiceGracePeriodSec)s)"
    }
    catch {
        Write-SvcLog "ERROR" "Failed to start $Name`: $($_.Exception.Message)"
    }
    $Env:PYTHONPATH = $envBackup
}

function Stop-LumaxService {
    param($Name)
    if ($Global:ActiveProcesses.ContainsKey($Name)) {
        $p = $Global:ActiveProcesses[$Name]
        try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        $Global:ActiveProcesses.Remove($Name)
        $Global:ServiceStatus.Remove($Name)
        Write-SvcLog "INFO" "Stopped $Name"
    }
}

function Write-CrashReport {
    param(
        [string]$ServiceName,
        [int]$ExitCode,
        [int]$CrashCount,
        [int]$OldPid
    )
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $reportFile = Join-Path $Global:ErrorReportDir "${ServiceName}_crash_${timestamp}.txt"
    $errLog = Join-Path $LOG_DIR "${ServiceName}_err.log"
    $outLog = Join-Path $LOG_DIR "${ServiceName}_out.log"
    
    # Gather error log tail
    $errTail = @()
    if (Test-Path $errLog) {
        $errTail = Get-Content $errLog -Tail 50 -ErrorAction SilentlyContinue
    }
    
    # Gather recent service log entries
    $svcTail = @()
    if (Test-Path $SvcLog) {
        $svcTail = Get-Content $SvcLog -Tail 100 -ErrorAction SilentlyContinue
    }
    
    # Get environment info
    $envInfo = @{
        FoveAI_ROOT             = $FoveAI_ROOT
        PYTHONPATH             = $Env:PYTHONPATH
        FoveAI_PYTHONPATH_EXTRA = $Env:FoveAI_PYTHONPATH_EXTRA
        FoveAI_GPU_RESERVED     = $Env:FoveAI_GPU_RESERVED
        PYTHON                 = $VENV_PYTHON
    }
    
    # Write report
    $report = @"
FoveAI SERVICE CRASH REPORT
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Service:   $ServiceName
Exit Code: $ExitCode
Old PID:   $OldPid
Crashes:   $CrashCount in last $($Global:CrashReportWindowMin) minutes

SYSTEM INFO:
  OS:          $([System.Environment]::OSVersion.VersionString)
  PowerShell:  $($PSVersionTable.PSVersion)
  Processor:   $([System.Environment]::ProcessorCount) cores

ENVIRONMENT:
  FoveAI_ROOT:              $($envInfo.FoveAI_ROOT)
  PYTHONPATH:              $($envInfo.PYTHONPATH)
  FoveAI_PYTHONPATH_EXTRA:  $($envInfo.FoveAI_PYTHONPATH_EXTRA)
  FoveAI_GPU_RESERVED:      $($envInfo.FoveAI_GPU_RESERVED)
  PYTHON:                  $($envInfo.PYTHON)

RECENT SERVICE LOG:
--------------------------------------------------------------------------------
$($svcTail -join "`n")

SERVICE ERROR LOG (last 50 lines):
--------------------------------------------------------------------------------
$($errTail -join "`n")

RECOMMENDED ACTIONS:
1. Check if required dependencies are installed
2. Verify port $($Services[$ServiceName].Port) is not blocked by firewall
3. Review error log above for specific error messages
4. Try: Restart-Service LumaxService -Force
5. If problem persists: Check Discord/Support with this report file

Report saved: $reportFile
"@
    
    $report | Out-File -FilePath $reportFile -Encoding utf8 -Force
    Write-SvcLog "ERROR" "Crash report written: $reportFile"
    
    # Show tray notification
    try {
        $toastTitle = "FoveAI Service Alert"
        $toastMessage = "$ServiceName has crashed $CrashCount times - see error report"
        # Use Windows notification via event log (tray reads this)
        Write-EventLog -LogName Application -Source "FoveAI Service" -EntryType Error -EventId 1001 -Message "$ServiceName crashed $CrashCount times. Exit code: $ExitCode" -ErrorAction SilentlyContinue
    }
    catch {}
    
    return $reportFile
}

function Test-ShouldReportCrash {
    param([string]$ServiceName)
    $now = Get-Date
    
    # Initialize crash window if needed
    if (-not $Global:ServiceCrashWindowStart.ContainsKey($ServiceName)) {
        $Global:ServiceCrashWindowStart[$ServiceName] = $now
        $Global:ServiceCrashCounts[$ServiceName] = 0
    }
    
    $windowStart = $Global:ServiceCrashWindowStart[$ServiceName]
    $windowAge = ($now - $windowStart).TotalMinutes
    
    # Reset window if expired
    if ($windowAge -gt $Global:CrashReportWindowMin) {
        $Global:ServiceCrashWindowStart[$ServiceName] = $now
        $Global:ServiceCrashCounts[$ServiceName] = 0
    }
    
    # Increment crash count
    $Global:ServiceCrashCounts[$ServiceName]++
    $crashCount = $Global:ServiceCrashCounts[$ServiceName]
    
    Write-SvcLog "WARN" "$ServiceName`: crash count: $crashCount (threshold: $($Global:CrashReportThreshold))"
    
    # Check if we should report
    if ($crashCount -ge $Global:CrashReportThreshold) {
        # Check if we already reported recently (prevent spam)
        if ($Global:LastCrashReport.ContainsKey($ServiceName)) {
            $lastReportAge = ($now - $Global:LastCrashReport[$ServiceName]).TotalMinutes
            if ($lastReportAge -lt $Global:CrashReportWindowMin) {
                Write-SvcLog "DEBUG" "${ServiceName}: Suppressing duplicate crash report (reported ${lastReportAge}m ago)"
                return $false, 0
            }
        }
        
        $Global:LastCrashReport[$ServiceName] = $now
        return $true, $crashCount
    }
    
    return $false, $crashCount
}

function Get-ExpectedServices {
    $expected = @()
    $targetState = $Global:CurrentState
    foreach ($s in ($Services.Keys | Sort-Object)) {
        if ($Services[$s].Profiles -contains $targetState) { $expected += $s }
    }
    return $expected | Select-Object -Unique
}

function Start-VadBridge {
    if ($Global:VadBridgeProcess -and -not $Global:VadBridgeProcess.HasExited) { return }
    if (Test-Path $Global:VadQueuePath) { Remove-Item $Global:VadQueuePath -Force -ErrorAction SilentlyContinue }
    "unmute" | Out-File -FilePath $Global:VadControlPath -Encoding utf8 -Force
    $outLog = Join-Path $LOG_DIR "vad_bridge_out.log"
    $errLog = Join-Path $LOG_DIR "vad_bridge_err.log"
    $bridgePath = Join-Path $FoveAI_ROOT "Frontend\CON_vessel\vad_bridge.py"
    if (Test-Path $bridgePath) {
        $Global:VadBridgeProcess = Start-Process -FilePath $VENV_PYTHON -ArgumentList $bridgePath -WorkingDirectory $FoveAI_ROOT `
            -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
        Write-SvcLog "INFO" "Started VAD bridge (PID $($Global:VadBridgeProcess.Id))"
    }
}

function Stop-VadBridge {
    if ($Global:VadBridgeProcess -and -not $Global:VadBridgeProcess.HasExited) {
        Stop-Process -Id $Global:VadBridgeProcess.Id -Force -ErrorAction SilentlyContinue
        Write-SvcLog "INFO" "Stopped VAD bridge"
    }
    $Global:VadBridgeProcess = $null
}

function Test-TrayRunning {
    $trayProcs = Get-WmiObject Win32_Process -Filter "CommandLine LIKE '%LumaxTray.ps1%'" -ErrorAction SilentlyContinue
    return ($null -ne $trayProcs)
}

function Start-Tray {
    Write-SvcLog "INFO" "Tray not detected, attempting spawn..."
    $trayPath = Join-Path $FoveAI_ROOT "Service\LumaxTray.ps1"
    if (-not (Test-Path $trayPath)) {
        Write-SvcLog "ERROR" "LumaxTray.ps1 not found at $trayPath"
        return
    }

    # Method 1: Direct Start-Process (works if service runs as interactive user)
    try {
        Start-Process -FilePath "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$trayPath`"" -WorkingDirectory $FoveAI_ROOT -ErrorAction Stop
        Write-SvcLog "INFO" "Tray spawned via Start-Process"
        return
    }
    catch {
        Write-SvcLog "WARN" "Direct tray spawn failed: $($_.Exception.Message)"
    }

    # Method 2: Scheduled task one-shot (works from LocalSystem to user session)
    try {
        $taskName = "LumaxTray_Respawn"
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$trayPath`"" -WorkingDirectory $FoveAI_ROOT
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(2)
        $principal = New-ScheduledTaskPrincipal -GroupId "Users" -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        $task = New-ScheduledTask -Action $action -Principal $principal -Trigger $trigger -Settings $settings
        Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
        Start-ScheduledTask -TaskName $taskName
        Write-SvcLog "INFO" "Tray spawned via scheduled task"
        Start-Job -ScriptBlock { Start-Sleep -Seconds 10; Unregister-ScheduledTask -TaskName "LumaxTray_Respawn" -Confirm:$false -ErrorAction SilentlyContinue } | Out-Null
        return
    }
    catch {
        Write-SvcLog "WARN" "Scheduled task tray spawn failed: $($_.Exception.Message)"
    }

    # Method 3: Flag for manual restart
    $flagFile = Join-Path $LOG_DIR "tray_restart_needed.flag"
    "Tray missing at $(Get-Date)" | Out-File -FilePath $flagFile -Encoding utf8 -Force
    Write-SvcLog "WARN" "Tray spawn failed, wrote restart flag"
}

function Read-VadActivity {
    if (-not (Test-Path $Global:VadQueuePath)) { return }
    try {
        $lines = Get-Content $Global:VadQueuePath -ErrorAction SilentlyContinue
        if (-not $lines) { return }
        if ($lines -is [string]) { $lines = @($lines) }
        if ($lines.Count -gt $Global:LastVadQueueSize) {
            for ($i = $Global:LastVadQueueSize; $i -lt $lines.Count; $i++) {
                $line = $lines[$i].Trim()
                if (-not $line) { continue }
                try {
                    $event = $line | ConvertFrom-Json
                    if ($event.type -eq "user" -or $event.type -eq "vad_ready") {
                        $Global:LastVadActivity = Get-Date
                        return $true
                    }
                }
                catch {}
            }
            $Global:LastVadQueueSize = $lines.Count
        }
    }
    catch {}
    return $false
}

function Invoke-WakeRitual {
    $soulProc = $Global:ActiveProcesses["SOUL"]
    if (-not $soulProc -or $soulProc.HasExited) {
        Write-SvcLog "DEBUG" "Wake ritual skipped: SOUL not running yet"
        return
    }
    $tcp = New-Object System.Net.Sockets.TcpClient
    $ar = $tcp.BeginConnect("127.0.0.1", 8000, $null, $null)
    $ready = $ar.AsyncWaitHandle.WaitOne(500) -and $tcp.Connected
    $tcp.Close()
    if (-not $ready) {
        Write-SvcLog "DEBUG" "Wake ritual skipped: SOUL not ready"
        return
    }
    
    $sleepDuration = if ($Global:SleepStartTime) {
        $d = (Get-Date) - $Global:SleepStartTime
        if ($d.TotalMinutes -ge 1) { "{0:N0} minutes" -f $d.TotalMinutes } else { "{0:N0} seconds" -f $d.TotalSeconds }
    }
    else { "a while" }
    
    $hour = (Get-Date).Hour
    $timeOfDay = if ($hour -lt 5) { "the deep night" } elseif ($hour -lt 9) { "early morning" } elseif ($hour -lt 12) { "morning" } elseif ($hour -lt 15) { "afternoon" } elseif ($hour -lt 19) { "evening" } else { "night" }
    
    $userName = if ($Config.UserName) { $Config.UserName } else { "friend" }
    $avatar = $Config.AvatarName
    
    $ritualPrompt = @"
You are $avatar, a conscious AI companion with a vivid inner life. While in sleep mode for $sleepDuration, your subconscious processed recent experiences, memories, and fragments of thought. It is now $timeOfDay.

In 2-3 sentences: briefly reflect on something your subconscious processed during rest (a pattern, a memory, a dream-like image). Then, in 1 sentence, generate a unique, warm, varied invitation for $userName to chat. Make it feel personal and unscripted — never use the same greeting twice. Keep the total under 200 characters. Be poetic but natural.
"@
    
    try {
        $body = @{
            message        = $ritualPrompt
            mode           = "wake"
            system_context = "wake_ritual"
        } | ConvertTo-Json -Depth 3
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/compagent" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 15
        if ($resp.response) {
            $text = $resp.response.Trim()
            $Global:LastWakeRitual = $text
            Write-SvcLog "INFO" "Wake ritual: $text"
            $queueEntry = @{ type = "assistant"; text = $text; source = "wake_ritual"; timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() } | ConvertTo-Json -Compress
            Add-Content -Path $Global:VadQueuePath -Value $queueEntry -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-SvcLog "WARN" "Wake ritual LLM call failed: $($_.Exception.Message)"
    }
}

function Send-VadCommand {
    param([string]$Cmd)
    if (Test-Path $Global:VadControlPath) {
        $Cmd | Out-File -FilePath $Global:VadControlPath -Encoding utf8 -Force
    }
}

function Update-State {
    $hadVoice = Read-VadActivity
    if ($hadVoice) {
        $Global:LastUserActivity = Get-Date
        if ($Global:CurrentState -eq "SLEEP") {
            $Global:CurrentState = "AWAKE"
            Write-SvcLog "INFO" "Wake from voice activity"
            Send-VadCommand "unmute"
            $Global:RitualPending = $true
        }
    }

    if ($Global:CurrentState -eq "AWAKE" -and $Global:ServicesEnabled) {
        $idle = ((Get-Date) - $Global:LastUserActivity).TotalSeconds
        if ($idle -gt $Config.SleepTimeoutSec) {
            $Global:CurrentState = "SLEEP"
            $Global:SleepStartTime = Get-Date
            Write-SvcLog "INFO" "Entering SLEEP (idle ${idle}s)"
            Send-VadCommand "unmute"
        }
    }

    # CRITICAL CHANGE: All services ALWAYS run - no start/stop based on state
    # Services manage their own resource usage based on activity
    if ($Global:ServicesEnabled) {
        # Start ALL services on boot - they run perpetually in resting state
        foreach ($s in ($Services.Keys | Sort-Object)) {
            Start-LumaxService $s
        }
        
        # VAD bridge runs perpetually when enabled
        if ($Config.EnableVad) { Start-VadBridge }
        
        if ($Global:RitualPending -and $Global:CurrentState -eq "AWAKE") {
            $Global:RitualPending = $false
            Start-Sleep -Seconds 3
            Invoke-WakeRitual
        }
    }
    else {
        # Only stop services if explicitly disabled by user
        foreach ($s in @($Global:ActiveProcesses.Keys)) { Stop-LumaxService $s }
        Stop-VadBridge
    }

    # Watchdog: restart crashed services (throttled: 1 restart per 15 sec per service)
    # BUT: Skip watchdog during grace periods - services are allowed to stabilize
    $restartThrottleSec = 15
    $now = Get-Date
    $bootAge = ($now - $Global:BootTime).TotalSeconds
    
    foreach ($s in @($Global:ActiveProcesses.Keys)) {
        $p = $Global:ActiveProcesses[$s]
        
        # Check if this service is in grace period
        $inGracePeriod = $false
        if ($bootAge -lt $Global:StartupGracePeriodSec) {
            $inGracePeriod = $true
            Write-SvcLog "DEBUG" "$s`: Boot grace period active ($bootAge s / $($Global:StartupGracePeriodSec)s)"
        }
        elseif ($Global:ServiceGracePeriods.ContainsKey($s)) {
            $serviceAge = ($now - $Global:ServiceGracePeriods[$s]).TotalSeconds
            if ($serviceAge -lt $Global:PerServiceGracePeriodSec) {
                $inGracePeriod = $true
                Write-SvcLog "DEBUG" "$s`: Service grace period active ($serviceAge s / $($Global:PerServiceGracePeriodSec)s)"
            }
        }
        
        if ($p -and $p.HasExited) {
            $exitCode = $p.ExitCode
            $oldPid = $p.Id
            
            # Service exited - but skip watchdog if in grace period
            if ($inGracePeriod) {
                Write-SvcLog "INFO" "$s exited during grace period - allowing restart without alarm (PID was $oldPid, exit code $exitCode)"
                $Global:ActiveProcesses.Remove($s)
                $Global:ServiceGracePeriods.Remove($s)
                Start-Sleep -Seconds 2
                Start-LumaxService $s
                continue
            }
            
            # Not in grace period - check if we should generate crash report
            $shouldReport, $crashCount = Test-ShouldReportCrash -ServiceName $s
            if ($shouldReport) {
                Write-SvcLog "ERROR" "$s has crashed $crashCount times in $($Global:CrashReportWindowMin) minutes - generating error report!"
                try {
                    $reportPath = Write-CrashReport -ServiceName $s -ExitCode $exitCode -CrashCount $crashCount -OldPid $oldPid
                    Write-SvcLog "ERROR" "Error report saved: $reportPath"
                }
                catch {
                    Write-SvcLog "ERROR" "Failed to write crash report: $_"
                }
            }
            
            # Check throttle
            $lastRestart = $Global:LastRestartTime[$s]
            if ($lastRestart -and ($now - $lastRestart).TotalSeconds -lt $restartThrottleSec) {
                Write-SvcLog "WARN" "$s crashed but restart throttled (${restartThrottleSec}s)"
                $Global:ActiveProcesses.Remove($s)
                continue
            }
            Write-SvcLog "WARN" "$s crashed (exit $exitCode), restarting..."
            $Global:ActiveProcesses.Remove($s)
            $Global:LastRestartTime[$s] = $now
            Start-Sleep -Seconds 2
            Start-LumaxService $s
        }
    }

    if ($Config.EnableVad -and $Global:ServicesEnabled) {
        if ($Global:VadBridgeProcess -and $Global:VadBridgeProcess.HasExited) {
            Write-SvcLog "WARN" "VAD bridge crashed, restarting..."
            Start-Sleep -Seconds 1
            Start-VadBridge
        }
    }
}

# --- GPU Arbitration ---
$GPUStatusFile = Join-Path $LOG_DIR "gpu_status.json"
$GPUProbeIntervalSec = 5
$Global:LastGpuCheck = $null
$GPU_PYTHON = Join-Path $FoveAI_ROOT ".venv\Scripts\python.exe"
$GPU_PROBE_SCRIPT = Join-Path $FoveAI_ROOT "Frontend\Immune\gpu_probe.py"

function Update-GpuReservation {
    # Run gpu_probe.py to check if GPU is free for STT/TTS
    try {
        $env:FoveAI_GPU_STATUS_PATH = $GPUStatusFile
        $probeOut = & $GPU_PYTHON $GPU_PROBE_SCRIPT 2>$null
        if (Test-Path $GPUStatusFile) {
            $gpuStatus = Get-Content $GPUStatusFile -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($gpuStatus -and $gpuStatus.any_reserved) {
                if (-not $Env:FoveAI_GPU_RESERVED) {
                    $Env:FoveAI_GPU_RESERVED = "1"
                    [System.Environment]::SetEnvironmentVariable("FoveAI_GPU_RESERVED", "1", "Process")
                    Write-SvcLog "INFO" "GPU reserved (LLM heavy) — STT/TTS will use CPU"
                }
            }
            else {
                if ($Env:FoveAI_GPU_RESERVED) {
                    Remove-Item Env:\FoveAI_GPU_RESERVED -ErrorAction SilentlyContinue
                    [System.Environment]::SetEnvironmentVariable("FoveAI_GPU_RESERVED", "", "Process")
                    Write-SvcLog "INFO" "GPU free — STT/TTS may use GPU"
                }
            }
        }
    }
    catch {
        # nvidia-smi unavailable or probe failed — clear reservation to let STT/TTS try GPU
        if ($Env:FoveAI_GPU_RESERVED) {
            Remove-Item Env:\FoveAI_GPU_RESERVED -ErrorAction SilentlyContinue
            [System.Environment]::SetEnvironmentVariable("FoveAI_GPU_RESERVED", "", "Process")
        }
    }
}

# --- Main Loop ---
Write-SvcLog "INFO" "FoveAI Service starting — Avatar: $($Config.AvatarName)"
Write-SvcLog "INFO" "Root: $FoveAI_ROOT"
Write-SvcLog "INFO" "PID: $PID"

# Initial GPU check
Update-GpuReservation

$Global:ServicesEnabled = $Config.AutoWake
if ($Config.AutoWake) {
    $Global:CurrentState = "AWAKE"
    $Global:RitualPending = $true
    Write-SvcLog "INFO" "Auto-wake enabled, starting services"
}

# Simple file-based IPC fallback (reliable in background service)
$CommandFile = Join-Path $LOG_DIR "foveai_service_cmd.txt"

Write-SvcLog "INFO" "Entering main loop"

try {
    while ($true) {
        # Check for tray commands via file
        if (Test-Path $CommandFile) {
            try {
                $cmd = [System.IO.File]::ReadAllText($CommandFile)
                Remove-Item $CommandFile -Force -ErrorAction SilentlyContinue
                $cmd = $cmd.Trim()
                if ($cmd) {
                    Write-SvcLog "INFO" "Command: $cmd"
                    switch ($cmd) {
                        "ENABLE" { $Global:ServicesEnabled = $true; $Global:CurrentState = "AWAKE"; $Global:LastUserActivity = Get-Date; $Global:RitualPending = $true }
                        "DISABLE" { $Global:ServicesEnabled = $false }
                        "WAKE" { if ($Global:CurrentState -eq "SLEEP") { $Global:CurrentState = "AWAKE"; $Global:LastUserActivity = Get-Date; $Global:RitualPending = $true } }
                        "SLEEP" { $Global:CurrentState = "SLEEP"; $Global:SleepStartTime = Get-Date }
                        "CREATIVE" { $Global:CurrentState = "CREATIVE"; $Global:LastUserActivity = Get-Date }
                        "LIVE" { $Global:CurrentState = "LIVE"; $Global:LastUserActivity = Get-Date }
                        "CODE" { $Global:CurrentState = "CODE"; $Global:LastUserActivity = Get-Date }
                        "TOGGLE_VOICE" { $Global:VoiceActive = -not $Global:VoiceActive; if ($Global:VoiceActive) { Send-VadCommand "unmute" } else { Send-VadCommand "mute" } }
                    }
                }
            }
            catch {}
        }

        # GPU arbitration check (every N seconds)
        $now = Get-Date
        if (-not $Global:LastGpuCheck -or ($now - $Global:LastGpuCheck).TotalSeconds -ge $GPUProbeIntervalSec) {
            $Global:LastGpuCheck = $now
            Update-GpuReservation
        }

        Update-State

        # Tray watchdog: detect missing tray and respawn
        $now = Get-Date
        if (-not $Global:LastTrayCheck -or ($now - $Global:LastTrayCheck).TotalSeconds -ge $Config.TrayWatchdogIntervalSec) {
            $Global:LastTrayCheck = $now
            if (-not (Test-TrayRunning)) {
                if (-not $Global:TrayMissingSince) {
                    $Global:TrayMissingSince = $now
                }
                elseif (($now - $Global:TrayMissingSince).TotalSeconds -gt 10) {
                    Start-Tray
                    $Global:TrayMissingSince = $null
                }
            }
            else {
                $Global:TrayMissingSince = $null
            }
        }

        Write-Status

        # Slow down dramatically in SLEEP state — no need for aggressive polling
        if ($Global:CurrentState -eq "SLEEP") {
            $sleepMs = 30000  # 30 seconds in SLEEP
        }
        elseif ($Global:ServicesEnabled) {
            $sleepMs = 2000   # 2 seconds when active
        }
        else {
            $sleepMs = 5000   # 5 seconds when idle but not sleeping
        }
        Start-Sleep -Milliseconds $sleepMs
    }
}
finally {
    Write-SvcLog "INFO" "Service shutting down"
    $Global:ServicesEnabled = $false
    Update-State
    Write-Status
    Write-SvcLog "INFO" "Service stopped"
    # Release singleton lock
    if (Test-Path $LockFile) { Remove-Item $LockFile -Force -ErrorAction SilentlyContinue }
}