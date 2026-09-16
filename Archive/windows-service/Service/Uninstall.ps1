# FoveAI Unified Uninstaller
# Reverses everything Install.ps1 sets up. Run as Administrator.
#
# Usage:
#   .\Uninstall.ps1                  # Clean uninstall (removes .venv, config, tokens, logs)
#   .\Uninstall.ps1 -KeepData        # Preserve .venv, .env, config, OAuth tokens, memories, logs
#   .\Uninstall.ps1 -Auto            # Skip confirmations

param(
    [switch]$Auto,     # Skip non-critical confirmations
    [switch]$KeepData  # Preserve user data: .venv, .env, config, OAuth tokens, memories, logs
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $PSScriptRoot).Path
$ServiceRoot = Join-Path $RepoRoot "Service"
$NssmExe = Join-Path $ServiceRoot "nssm\nssm.exe"
$ServiceName = "LumaxService"
$StartupFolder = [Environment]::GetFolderPath("Startup")
$TrayShortcut = Join-Path $StartupFolder "LumaxTray.lnk"

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Write-Host-Cyan { param($txt) Write-Host "⚓️ $txt" -ForegroundColor Cyan }
function Write-Host-Yellow { param($txt) Write-Host "🚠 $txt" -ForegroundColor Yellow }
function Write-Host-Green { param($txt) Write-Host "✅ $txt" -ForegroundColor Green }
function Write-Host-Red { param($txt) Write-Host "❌ $txt" -ForegroundColor Red }
function Write-Host-Section { param($txt) Write-Host "`n=== $txt ===" -ForegroundColor DarkGray }

if (-not (Test-Admin)) {
    Write-Host-Red "ERROR: Must run as Administrator for service and PATH removal."
    Write-Host-Yellow "Right-click PowerShell → 'Run as administrator', then retry."
    exit 1
}

Clear-Host
Write-Host "====================================================" -ForegroundColor DarkGray
Write-Host "   FoveAI Unified Uninstaller" -ForegroundColor Cyan -Bold
Write-Host "====================================================" -ForegroundColor DarkGray

if ($KeepData) {
    Write-Host-Yellow "MODE: Keep Data — .venv, config, OAuth tokens, memories, and logs will be PRESERVED."
} else {
    Write-Host-Yellow "MODE: Clean Uninstall — all artifacts will be REMOVED (reversible by reinstalling)."
}

Write-Host ""

if (-not $Auto) {
    $confirm = Read-Host "Continue? [Y/n]"
    if ($confirm -and $confirm -notmatch "^[Yy]") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
}

$removedItems = @()
$keptItems = @()

# =====================================================================
# 1. Stop and Remove Windows Service
# =====================================================================
Write-Host-Section "Phase A: Service Removal"

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host-Yellow "Stopping service: $ServiceName..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if (Test-Path $NssmExe) {
        & $NssmExe remove $ServiceName confirm 2>$null
    } else {
        Write-Host-Yellow "NSSM not found, trying sc.exe..."
        sc.exe delete $ServiceName | Out-Null
    }
    Start-Sleep -Seconds 2
    Write-Host-Green "Service removed."
    $removedItems += "Windows Service ($ServiceName)"
} else {
    Write-Host-Green "Service not found (already removed)."
}

# =====================================================================
# 2. Remove Tray from Startup + Kill Process
# =====================================================================
Write-Host-Section "Phase B: Tray Widget Removal"

if (Test-Path $TrayShortcut) {
    Remove-Item $TrayShortcut -Force
    Write-Host-Green "Tray startup shortcut removed."
    $removedItems += "Tray startup shortcut"
}

$trayProcs = Get-Process -Name "powershell" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*LumaxTray.ps1*"
}
if ($trayProcs) {
    foreach ($p in $trayProcs) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        Write-Host-Yellow "Stopped tray process (PID $($p.Id))."
    }
    $removedItems += "Tray process(es)"
} else {
    Write-Host-Green "Tray process not running."
}

# =====================================================================
# 3. Kill Remaining FoveAI Processes
# =====================================================================
Write-Host-Section "Phase C: Process Cleanup"

$procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and (
        $_.Path -like "*$RepoRoot*\.venv*" -or
        $_.Path -like "*$RepoRoot*foveai*" -or
        $_.Path -like "*$RepoRoot*vad*" -or
        $_.CommandLine -like "*LumaxService.ps1*"
    )
}
if ($procs) {
    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            Write-Host-Yellow "Stopped process: $($p.Name) (PID $($p.Id))"
        } catch {}
    }
    $removedItems += "FoveAI Python processes"
} else {
    Write-Host-Green "No FoveAI processes running."
}

# =====================================================================
# 4. Unregister from PATH
# =====================================================================
Write-Host-Section "Phase D: PATH Cleanup"

$currentPath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$pathEntries = $currentPath -split ";" | Where-Object { $_ -ne "" }

if ($pathEntries -contains $RepoRoot) {
    $newPath = ($pathEntries | Where-Object { $_ -ne $RepoRoot }) -join ";"
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Host-Green "Removed from system PATH."
    $removedItems += "PATH entry"
} else {
    Write-Host-Green "Not registered in PATH."
}

# =====================================================================
# 5. Data Removal (Optional)
# =====================================================================
Write-Host-Section "Phase E: Data Cleanup"

if ($KeepData) {
    Write-Host-Green "Skipping data removal (-KeepData specified)."
    $keptItems += ".venv (Python environment)"
    $keptItems += ".env (configuration)"
    $keptItems += "Service config (avatar, timeouts)"
    $keptItems += "OAuth tokens (.cache/)"
    $keptItems += "Consent data backups (Data/Consent/)"
    $keptItems += "Memory databases (ChromaDB, Kuzu)"
    $keptItems += "Logs (.logs/)"
} else {
    # .venv
    $venvPath = Join-Path $RepoRoot ".venv"
    if (Test-Path $venvPath) {
        Remove-Item $venvPath -Recurse -Force
        Write-Host-Green "Removed .venv"
        $removedItems += "Python .venv"
    }

    # .env
    if (Test-Path (Join-Path $RepoRoot ".env")) {
        Remove-Item (Join-Path $RepoRoot ".env") -Force
        Write-Host-Green "Removed .env"
        $removedItems += ".env config"
    }

    # Service config
    $svcConfig = Join-Path $ServiceRoot "foveai_service_config.json"
    if (Test-Path $svcConfig) {
        Remove-Item $svcConfig -Force
        Write-Host-Green "Removed service config"
        $removedItems += "Service config"
    }

    # OAuth tokens
    $cacheDir = Join-Path $RepoRoot ".cache"
    if (Test-Path $cacheDir) {
        Remove-Item $cacheDir -Recurse -Force
        Write-Host-Green "Removed OAuth tokens (.cache/)"
        $removedItems += "OAuth tokens (.cache/)"
    }

    # Consent data backups
    $consentData = Join-Path $RepoRoot "Data\Consent"
    if (Test-Path $consentData) {
        Remove-Item $consentData -Recurse -Force
        Write-Host-Green "Removed consent data backups"
        $removedItems += "Consent data backups"
    }

    # Memory databases (ChromaDB, Kuzu)
    $memoryDir = Join-Path $RepoRoot "backend\Memory"
    if (Test-Path $memoryDir) {
        $dbFiles = Get-ChildItem -Path $memoryDir -File -ErrorAction SilentlyContinue | Where-Object {
            $_.Extension -in @(".db", ".sqlite3", ".kuzu", ".json")
        }
        foreach ($db in $dbFiles) {
            Remove-Item $db.FullName -Force
            Write-Host-Green "Removed memory database: $($db.Name)"
            $removedItems += "Memory DB: $($db.Name)"
        }
    }

    # Logs
    $logsDir = Join-Path $RepoRoot ".logs"
    if (Test-Path $logsDir) {
        Remove-Item $logsDir -Recurse -Force
        Write-Host-Green "Removed logs (.logs/)"
        $removedItems += "Logs (.logs/)"
    }
}

# =====================================================================
# 6. Optional: Remove NSSM
# =====================================================================
Write-Host-Section "Phase F: NSSM Cleanup"

$nssmDir = Join-Path $ServiceRoot "nssm"
if (Test-Path $nssmDir) {
    if (-not $Auto) {
        $removeNssm = Read-Host "Remove NSSM directory? (y/N)"
        if ($removeNssm -eq "y" -or $removeNssm -eq "Y") {
            Remove-Item $nssmDir -Recurse -Force
            Write-Host-Green "NSSM removed."
            $removedItems += "NSSM"
        } else {
            Write-Host-Green "NSSM kept."
            $keptItems += "NSSM"
        }
    } else {
        # Auto mode: keep NSSM (it's small, and reinstalling it requires download)
        Write-Host-Green "NSSM kept (auto mode preserves it)."
        $keptItems += "NSSM"
    }
} else {
    Write-Host-Green "NSSM not found."
}

# =====================================================================
# Summary
# =====================================================================
Write-Host "====================================================" -ForegroundColor DarkGray
Write-Host-Green "Uninstall Complete."

Write-Host ""
Write-Host-Cyan "Removed:"
if ($removedItems.Count -eq 0) {
    Write-Host "  (nothing)"
} else {
    foreach ($item in $removedItems) {
        Write-Host "  - $item"
    }
}

Write-Host ""
Write-Host-Cyan "Preserved:"
if ($keptItems.Count -eq 0) {
    Write-Host "  (nothing — clean slate)"
} else {
    foreach ($item in $keptItems) {
        Write-Host "  - $item"
    }
}

Write-Host ""
if (-not $KeepData) {
    Write-Host "FoveAI is fully removed. To reinstall:" -ForegroundColor Gray
    Write-Host "  .\Install.ps1 -Auto -InstallService -RegisterGlobal" -ForegroundColor Cyan
} else {
    Write-Host "FoveAI services removed. Data preserved. To reinstall quickly:" -ForegroundColor Gray
    Write-Host "  .\Install.ps1 -Auto -InstallService -RegisterGlobal" -ForegroundColor Cyan
    Write-Host "(.venv already exists — install will skip dependency download)" -ForegroundColor Gray
}
Write-Host "====================================================" -ForegroundColor DarkGray