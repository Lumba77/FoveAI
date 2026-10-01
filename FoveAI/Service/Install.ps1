# Version 2.0 (Unified Windows Install & Service Bootstrap)
# Root: FoveAI-lite/Install.ps1
#
# One-shot setup:
#   - Python .venv + requirements
#   - Windows Service + Tray (optional)
#   - Global `foveai` command (optional)
#   - Docker build (optional, if -Build)
#
# Run as Administrator for service/PATH registration.

Param(
    [switch]$Auto,           # Skip non-critical confirmations
    [switch]$Build,          # Trigger Docker Build for unified shards
    [switch]$SkipService,    # Skip Windows background service + tray install
    [switch]$RegisterGlobal, # Also add `foveai` to system PATH
    [switch]$ForceModelPull, # Force Ollama model pull even if detected
    [switch]$SkipOculus,     # Exclude Oculus Manifest generation
    [switch]$SkipSteam,      # Exclude Steam Shortcut logic
    [switch]$SkipVenv,       # Skip local Python .venv setup
    [string]$ModelsPath = "" # Override FoveAI_MODELS_ROOT
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $PSScriptRoot).Path
$BuildDir = Join-Path $RepoRoot "Build"
$EnvPath = Join-Path $RepoRoot ".env"

# Sovereign Naming Shards
$N_XR    = "Lumax-XR"
$N_Web   = "Lumax-Webui"
$N_Mobile = "Lumax-Mobile"

# Colors & Branding
function Write-Host-Cyan { param($txt) Write-Host "⚓️ $txt" -ForegroundColor Cyan }
function Write-Host-Yellow { param($txt) Write-Host "🚠 $txt" -ForegroundColor Yellow }
function Write-Host-Green { param($txt) Write-Host "✅ $txt" -ForegroundColor Green }
function Write-Host-Red { param($txt) Write-Host "❌ $txt" -ForegroundColor Red }
function Write-Host-Section { param($txt) Write-Host "`n=== $txt ===" -ForegroundColor DarkGray }

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-Command { param($cmd) return $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

Clear-Host
Write-Host "====================================================" -ForegroundColor DarkGray
Write-Host "   FoveAI-lite: Unified Setup & Service Bootstrap" -ForegroundColor Cyan -Bold
Write-Host "====================================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host "This installer will:" -ForegroundColor Gray
Write-Host "  1. Audit your system (CPU, RAM, GPU)" -ForegroundColor Gray
Write-Host "  2. Set up Python .venv + dependencies" -ForegroundColor Gray
Write-Host "  3. Create .env configuration" -ForegroundColor Gray
if (-not $SkipService) {
    Write-Host "  4. Install Windows background service + tray widget" -ForegroundColor Gray
}
if ($RegisterGlobal) {
    Write-Host '  5. Register foveai as a global command' -ForegroundColor Gray
}
if ($Build) {
    Write-Host "  6. Build Docker shards (if Docker available)" -ForegroundColor Gray
}
Write-Host ""

if (-not $Auto) {
    $confirm = Read-Host "Continue? [Y/n]"
    if ($confirm -and $confirm -notmatch "^[Yy]") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
}

# =====================================================================
# 1. System Audit
# =====================================================================
Write-Host-Section "Phase A: System Audit"
try {
    $CPU = Get-CimInstance Win32_Processor | Select-Object -First 1
    $RAM = Get-CimInstance Win32_ComputerSystem | Select-Object -First 1
    $GPU = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" } | Select-Object -First 1

    Write-Host-Cyan "CPU: $($CPU.Name) ($($CPU.NumberOfLogicalProcessors) logical cores)"
    Write-Host-Cyan "RAM: $([Math]::Round($RAM.TotalPhysicalMemory / 1GB, 2)) GB"
    
    if ($GPU) {
        Write-Host-Green "GPU (NVIDIA): $($GPU.Name) Detected."
    } else {
        Write-Host-Yellow "GPU: NVIDIA not detected via WMI. Local LLM/Vision performance may be compromised."
    }

    if ($RAM.TotalPhysicalMemory / 1GB -lt 16) {
        Write-Host-Yellow "Warning: Less than 16GB RAM detected. FoveAI full-stack may experience memory pressure."
    }
} catch {
    Write-Host-Yellow "System Audit partial failure. Continuing with default assumptions."
}

# =====================================================================
# 2. Dependency Verification
# =====================================================================
Write-Host-Section "Phase B: Dependency Verification"

$Deps = @{
    "Git"    = "git"
    "UV"     = "uv"
    "Python" = "python"
}

$OptionalDeps = @{
    "Docker" = "docker"
    "ADB"    = "adb"
}

$hasDocker = $false
$hasAdb = $false

foreach ($d in $Deps.Keys) {
    if (Test-Command $Deps[$d]) {
        Write-Host-Green "$d detected."
    } else {
        if ($d -eq "UV") {
            Write-Host-Yellow "UV not detected. Will attempt to install it for .venv sovereignty."
        } elseif ($d -eq "Python") {
            Write-Host-Red "CRITICAL: Python not detected. Please install Python 3.11+ and retry."
            exit 1
        } else {
            Write-Host-Red "CRITICAL: $d not detected. Please install and retry."
            exit 1
        }
    }
}

foreach ($d in $OptionalDeps.Keys) {
    if (Test-Command $OptionalDeps[$d]) {
        Write-Host-Green "$d detected (optional)."
        if ($d -eq "Docker") { $hasDocker = $true }
        if ($d -eq "ADB") { $hasAdb = $true }
    } else {
        Write-Host-Yellow "$d not detected (optional, only needed for mobile/VR shards)."
    }
}

# =====================================================================
# 3. Repository Calibration (.env)
# =====================================================================
Write-Host-Section "Phase C: Repository Calibration"

if (-not (Test-Path $EnvPath)) {
    Write-Host-Yellow ".env missing. Initializing from internal manifest..."
    
    $modelsRoot = if ($ModelsPath) { $ModelsPath } else { "D:/Lumax/models" }
    if (-not (Test-Path $modelsRoot)) {
        $modelsRoot = "$env:USERPROFILE\Lumax\models"
        if (-not (Test-Path $modelsRoot)) { New-Item -ItemType Directory -Path $modelsRoot -Force | Out-Null }
    }

    $DefaultEnv = @"
FoveAI_MODELS_ROOT=$modelsRoot
FoveAI_WEBUI_PASSWORD=1um6a1UM6a
FoveAI_IDENTITY_NAME=Jen
FoveAI_IDENTITY_GENDER=female
FoveAI_USE_ADB_REVERSE=true
"@
    $DefaultEnv | Out-File -FilePath $EnvPath -Encoding UTF8
    Write-Host-Green ".env initialized."
} else {
    Write-Host-Cyan ".env manifest detected."
    $EnvContent = Get-Content $EnvPath
    if ($EnvContent -match "1um6a1UM6a") {
        Write-Host-Yellow "Warning: Default FoveAI_WEBUI_PASSWORD detected. Change it in .env for security."
    }
}

# =====================================================================
# 4. Python Environment Sovereignty (uv)
# =====================================================================
if (-not $SkipVenv) {
    Write-Host-Section "Phase D: Python Environment Sovereignty"
    
    if (-not (Test-Command "uv")) {
        Write-Host-Cyan "Installing uv via astral.sh..."
        try {
            powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
            $env:Path += ";$HOME\.cargo\bin"
        } catch {
            Write-Host-Yellow "UV auto-install failed. Will try pip fallback."
        }
    }

    $RepoVenvPath = Join-Path $RepoRoot ".venv"
    $RepoVenvPython = Join-Path $RepoVenvPath "Scripts\python.exe"
    $ActiveVenvPath = $env:VIRTUAL_ENV
    $VenvPython = $RepoVenvPython

    if ($ActiveVenvPath) {
        $sameActive = $false
        try {
            $activeResolved = [System.IO.Path]::GetFullPath($ActiveVenvPath).TrimEnd('\')
            $repoResolved = [System.IO.Path]::GetFullPath($RepoVenvPath).TrimEnd('\')
            $sameActive = $activeResolved -ieq $repoResolved
        } catch { $sameActive = $false }
        if ($sameActive) {
            Write-Host-Cyan "Detected active repo .venv; reusing without recreate."
            $VenvPython = Join-Path $ActiveVenvPath "Scripts\python.exe"
        }
    }

    if (-not (Test-Path $VenvPython)) {
        if (Test-Command "uv") {
            Write-Host-Cyan "Creating local .venv with uv..."
            & uv venv
            $VenvPython = $RepoVenvPython
        } else {
            Write-Host-Cyan "Creating local .venv with python -m venv..."
            & python -m venv $RepoVenvPath
            $VenvPython = $RepoVenvPython
        }
    } else {
        Write-Host-Cyan "Reusing existing .venv."
    }

    if (-not (Test-Path $VenvPython)) {
        Write-Host-Red "Could not locate .venv Python at $VenvPython. Aborting."
        exit 1
    }

    # Pre-install PyTorch with CUDA if available
    Write-Host-Cyan "Installing PyTorch baseline (CUDA if available)..."
    $pytorchInstalled = $false
    try {
        if (Test-Command "uv") {
            & uv pip install --python $VenvPython --index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio
            if ($LASTEXITCODE -eq 0) { $pytorchInstalled = $true }
        }
    } catch {
        Write-Host-Yellow "CUDA wheel install failed; falling back to CPU PyTorch."
    }
    
    if (-not $pytorchInstalled) {
        if (Test-Command "uv") {
            & uv pip install --python $VenvPython torch torchvision torchaudio
        } else {
            & $VenvPython -m pip install torch torchvision torchaudio
        }
    }

    # Install full requirements
    Write-Host-Cyan "Installing requirements_foveai.txt (this may take several minutes)..."
    if (Test-Command "uv") {
        & uv pip install --python $VenvPython -r requirements_foveai.txt
    } else {
        & $VenvPython -m pip install -r requirements_foveai.txt
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host-Yellow "Some packages may have failed. Check output above."
    } else {
        Write-Host-Green "Local .venv anchored with all dependencies."
    }
    
    Write-Host-Cyan "To activate later: .\.venv\Scripts\activate"
    
    # =====================================================================
    # 4b. Per-Service Virtual Environments
    # =====================================================================
    Write-Host ""
    Write-Host-Cyan "Setting up per-service virtual environments..."
    Write-Host "  This isolates dependencies for each service to prevent conflicts."
    Write-Host "  (e.g., optimum version issues between creative and soul services)"
    
    $SetupScript = Join-Path $RepoRoot "Setup-VirtualEnvs.ps1"
    if (Test-Path $SetupScript) {
        try {
            & $SetupScript -Service all
            Write-Host-Green "Per-service venvs created successfully."
        } catch {
            Write-Host-Yellow "Per-service venv setup encountered an issue."
            Write-Host "  You can run it manually later: .\Setup-VirtualEnvs.ps1"
        }
    } else {
        Write-Host-Yellow "Setup-VirtualEnvs.ps1 not found. Skipping per-service venvs."
    }
} else {
    Write-Host-Yellow "Skipped .venv setup (-SkipVenv)."
}

# =====================================================================
# 5. Service Installation (Default)
# =====================================================================
if (-not $SkipService) {
    Write-Host-Section "Phase E: Windows Service Installation"
    
    if (-not (Test-Admin)) {
        Write-Host-Yellow "Administrator rights required for service install. Skipping."
        Write-Host-Yellow "Re-run as Administrator to install the service (or use -SkipService to skip)."
    } else {
        $SvcInstaller = Join-Path $RepoRoot "Service\Install_Lumax_Service.ps1"
        if (Test-Path $SvcInstaller) {
            Write-Host-Cyan "Invoking service installer..."
            & powershell -NoProfile -ExecutionPolicy Bypass -File $SvcInstaller
            if ($LASTEXITCODE -eq 0) {
                Write-Host-Green "Windows service installed and started."
            } else {
                Write-Host-Yellow "Service installer reported issues. Check logs."
            }
        } else {
            Write-Host-Red "Service installer not found at: $SvcInstaller"
        }
    }
}

# =====================================================================
# 6. Global PATH Registration (Optional)
# =====================================================================
if ($RegisterGlobal) {
    Write-Host-Section "Phase F: Global Command Registration"
    
    if (-not (Test-Admin)) {
        Write-Host-Yellow "Administrator rights required for PATH registration. Skipping."
        Write-Host-Yellow "Re-run with -RegisterGlobal as Administrator."
    } else {
        $RegScript = Join-Path $RepoRoot "Service\Register_Global_Lumax.ps1"
        if (Test-Path $RegScript) {
            Write-Host-Cyan 'Registering foveai as global command...'
            & powershell -NoProfile -ExecutionPolicy Bypass -File $RegScript
            Write-Host-Green 'Global command registered. Open a NEW terminal to use foveai.'
        } else {
            Write-Host-Red "PATH registration script not found at: $RegScript"
        }
    }
}

# =====================================================================
# 7. Docker Build (Optional)
# =====================================================================
if ($Build) {
    Write-Host-Section "Phase G: Docker Build (Optional)"
    if ($hasDocker) {
        Write-Host-Cyan "Igniting Docker Build for unified shards..."
        docker compose build
    } else {
        Write-Host-Yellow "Docker not available. Skipping container build."
    }
}

# =====================================================================
# 8. Model Pull (Optional, only if Docker Ollama container running)
# =====================================================================
if ($hasDocker) {
    Write-Host-Section "Phase H: Ollama Model Check"
    $OllamaContainer = "foveai_ollama_backup"
    if (docker ps --format '{{.Names}}' | Select-String -Pattern $OllamaContainer) {
        Write-Host-Cyan "Checking biological shards in $OllamaContainer..."
        $Models = @("qwen2.5-coder:3b", "moondream:latest", "nomic-embed-text:latest", "smollm2:latest")
        $PulledModels = docker exec $OllamaContainer ollama list
        
        foreach ($m in $Models) {
            if ($PulledModels -notmatch $m -or $ForceModelPull) {
                Write-Host-Yellow "Missing shard detected: $m. Initiating pull..."
                docker exec $OllamaContainer ollama pull $m
            } else {
                Write-Host-Green "$m is anchored."
            }
        }
    } else {
        Write-Host-Yellow "Ollama container not running. Model pull deferred to Sentry."
    }
}

# =====================================================================
# 9. Shard Discovery & Installation (XR + Mobile builds)
# =====================================================================
Write-Host-Section "Phase I: Vessel Installation"
Write-Host-Cyan "Scanning /frontend/Build for export fragments..."

if (-not (Test-Path $BuildDir)) {
    Write-Host-Yellow "Notice: /frontend/Build shard not found. Skipping XR/Mobile installation."
} else {
    $Builds = Get-ChildItem -Path $BuildDir -File
    foreach ($item in $Builds) {
        $newName = $null
        if ($item.Extension -eq ".exe") {
            if ($item.Name -like "*XR*") { $newName = "$N_XR$($item.Extension)" }
            elseif ($item.Name -like "*Webui*") { $newName = "$N_Web$($item.Extension)" }
        }
        elseif ($item.Extension -eq ".apk") {
            $newName = "$N_Mobile$($item.Extension)"
        }

        if ($newName -and $item.Name -ne $newName) {
            $targetPath = Join-Path $BuildDir $newName
            if (Test-Path $targetPath) { Remove-Item $targetPath -Force }
            Write-Host-Cyan "Renaming biological shard: $($item.Name) -> $newName"
            Rename-Item -Path $item.FullName -NewName $newName -Force
        }
    }

    $ActualXR = Join-Path $BuildDir "$N_XR.exe"
    $ActualMobile = Join-Path $BuildDir "$N_Mobile.apk"

    # Meta Quest Link
    if (-not $SkipOculus -and (Test-Path $ActualXR)) {
        Write-Host-Cyan "Manifesting Oculus Meta Link registration..."
        $OculusManifestDir = $null
        $ManifestCandidates = @(
            "D:\Oculus\CoreData\Manifests",
            "C:\Program Files\Oculus\CoreData\Manifests",
            "$env:ProgramFiles\Meta Horizon\CoreData\Manifests",
            "$env:LOCALAPPDATA\Oculus\Manifests"
        )
        foreach ($cand in $ManifestCandidates) {
            if (Test-Path $cand) {
                $OculusManifestDir = $cand
                break
            }
        }
        if (-not $OculusManifestDir) {
            if (Test-Path "D:\Oculus") {
                $OculusManifestDir = "D:\Oculus\CoreData\Manifests"
            } else {
                $OculusManifestDir = "$env:LOCALAPPDATA\Oculus\Manifests"
            }
        }
        if (-not (Test-Path $OculusManifestDir)) { New-Item -ItemType Directory -Path $OculusManifestDir -Force | Out-Null }

        $CanonicalName = "Lumax_XR_Sovereign"
        $ManifestPath = Join-Path $OculusManifestDir "$($CanonicalName).json"
        
        $FilesMap = @{}
        $FilesMap[$ActualXR] = ""
        $ManifestJSON = @{
            "canonicalName" = $CanonicalName
            "displayName" = "FoveAI-lite (XR Vessel)"
            "files" = $FilesMap
            "firewallExceptionsRequired" = $false
            "isCore" = $false
            "launchFile" = $ActualXR
            "launchParameters" = " "
            "manifestVersion" = 0
            "packageType" = "APP"
            "thirdParty" = $true
            "version" = "1"
            "versionCode" = 1
        } | ConvertTo-Json -Depth 6

        try {
            $ManifestJSON | Out-File -FilePath $ManifestPath -Encoding UTF8 -Force
            Write-Host-Green "Meta Quest Link entry anchored: $ManifestPath"
        } catch {
            Write-Host-Red "Failed to anchor Oculus manifest. Elevate to Admin for System manifests."
        }
    }

    # Mobile (ADB)
    if (Test-Path $ActualMobile) {
        Write-Host-Cyan "Detecting Mobile connectivity for $N_Mobile..."
        if ($hasAdb) {
            $Devices = adb devices | Select-String -Pattern "\tdevice$"
            if ($Devices) {
                Write-Host-Green "Mobile shard detected. Initiating APK push..."
                adb install -r $ActualMobile
            } else {
                Write-Host-Yellow "Quest not detected via adb. Ensure Developer Mode is active."
            }
        } else {
            Write-Host-Yellow "ADB not available. Skipping mobile APK push."
        }
    }
}

# =====================================================================
# Done
# =====================================================================
Write-Host "====================================================" -ForegroundColor DarkGray
Write-Host-Green "Setup Complete. FoveAI is ready."
Write-Host ""
Write-Host-Cyan "Next steps:"
Write-Host "  - Start console:       .\Start_FoveAI.ps1"
if (-not $SkipService) {
    Write-Host "  - Service status:      sc.exe query LumaxService"
    Write-Host "  - Open tray widget:    Look for the dot in your system tray"
}
if ($RegisterGlobal) {
    Write-Host '  - Global command:      Open a NEW terminal, then type foveai'
}
if ($SkipService) {
    Write-Host "  - Install service:     .\Service\Install_Lumax_Service.ps1  (as Admin)"
}
if (-not $RegisterGlobal) {
    Write-Host "  - Global PATH:         .\Service\Register_Global_Lumax.ps1  (as Admin)"
}
Write-Host "  - Logs:                .logs\"
Write-Host "  - Config:              Service\foveai_service_config.json"
Write-Host "  - WebUI:               http://localhost:8080"
if (-not $SkipVenv) {
    Write-Host "  - Activate venv:       .\.venv\Scripts\activate"
}
Write-Host "====================================================" -ForegroundColor DarkGray