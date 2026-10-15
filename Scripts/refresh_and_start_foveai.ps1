# FoveAI Refresh and Start Script
# Kills all related processes, rebuilds dependencies, and starts the system fresh

param(
    [Parameter(Position=0)]
    [string]$TargetVessel = $null
)

$FoveAI_ROOT = $PSScriptRoot
$venvPath = if ($Env:FoveAI_VENV_PATH) { $Env:FoveAI_VENV_PATH } else { ".venv" }
$VENV_DIR = Join-Path $FoveAI_ROOT $venvPath
$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_LIB = Join-Path $VENV_DIR "Lib\site-packages"
$LOG_DIR = Join-Path $FoveAI_ROOT ".logs"

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force }

# Force SOUL to see its libraries
$Env:PYTHONPATH = "$FoveAI_ROOT;$FoveAI_ROOT\Mind;$FoveAI_ROOT\backend\Cognition;$VENV_LIB"

$Global:ActiveProcs = @{}

# Define Services
$Services = @{
    "SOUL"   = @{ Path="$FoveAI_ROOT\backend\Cognition"; Cmd="compagent.py" }
    "MEMORY" = @{ Path="$FoveAI_ROOT\backend\Memory";    Cmd="-m uvicorn memory_service:app --host 0.0.0.0 --port 8002" }
    "VITE"   = @{ Path="$FoveAI_ROOT\frontend\XR_Vessel"; Cmd="/c npm run dev"; Exe="cmd.exe" }
    "WEBUI"  = @{ Path="$FoveAI_ROOT\frontend\Web_Vessel"; Cmd="web_app.py" }
    "OLLAMA" = @{ Path="$FoveAI_ROOT"; Cmd="serve"; Exe="C:\OllamaCLI\ollama.exe" }
    "LMS"    = @{ Path="$FoveAI_ROOT"; Cmd="server start --port 1234"; Exe="C:\Users\lumba\.lmstudio\bin\lms.exe" }
    "TUNNEL" = @{ Path="$FoveAI_ROOT"; Cmd="tunnel --config config.yml run"; Exe="$FoveAI_ROOT\cloudflared.exe" }
}

function Stop-All {
    Write-Host ">>> Stopping all services..." -ForegroundColor Yellow
    foreach ($name in $Global:ActiveProcs.Keys) {
        $p = $Global:ActiveProcs[$name]
        if ($p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped $name."
        }
    }

    # Kill processes by common FoveAI names
    $Names = @("cloudflared", "ollama") # REMOVED node/npm to prevent killing the Gemini CLI
    foreach ($name in $Names) {
        Stop-Process -Name $name -Force -ErrorAction SilentlyContinue
    }

    # Kill processes on FoveAI ports
    $Ports = @(8000, 8002, 5176, 8080, 1234)
    foreach ($port in $Ports) {
        $procId = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue).OwningProcess
        if ($procId) {
            foreach ($processId in $procId) {
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                Write-Host "Killed process on port $port (PID: $processId)" -ForegroundColor Gray
            }
        }
    }

    Write-Host "All services stopped." -ForegroundColor Gray
}

function Clean-NPM-Cache {
    Write-Host ">>> Cleaning NPM cache..." -ForegroundColor Yellow
    try {
        Push-Location "Frontend\XR_Vessel"
        npm cache clean --force 2>$null
        Pop-Location
        Write-Host "NPM cache cleaned." -ForegroundColor Green
    } catch {
        Write-Host "Failed to clean NPM cache: $($_.Exception.Message)" -ForegroundColor Red
        Pop-Location
    }
}

function Clear-Chrome-Cache {
    Write-Host ">>> Clearing Chrome cache for foveai.1um6a.se..." -ForegroundColor Yellow
    try {
        # Clear Chrome cache for specific domain
        $chromeCacheDir = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache"
        if (Test-Path $chromeCacheDir) {
            # Clear Chrome cache by deleting cache files
            Get-ChildItem -Path $chromeCacheDir -File | Remove-Item -Force -ErrorAction SilentlyContinue
            Write-Host "Chrome cache cleared." -ForegroundColor Green

            # Also clear Chrome cookies for the domain
            $chromeCookies = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Network\Cookies"
            if (Test-Path $chromeCookies) {
                # Note: We can't directly edit the Cookies SQLite database without proper tools
                # This would require using sqlite3 or similar, which may not be available
                Write-Host "Note: Chrome cookies require manual clearing via Chrome settings." -ForegroundColor Yellow
            }
        } else {
            Write-Host "Chrome cache directory not found." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to clear Chrome cache: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Clear-Cloudflare-Cache {
    Write-Host ">>> Clearing Cloudflare cache..." -ForegroundColor Yellow
    try {
        # Check if cloudflared is available
        $cloudflaredPath = "$FoveAI_ROOT\cloudflared.exe"
        if (Test-Path $cloudflaredPath) {
            Write-Host "Using cloudflared at: $cloudflaredPath" -ForegroundColor Gray

            # Clear Cloudflare tunnel cache
            $cacheDir = "$env:LOCALAPPDATA\cloudflared"
            if (Test-Path $cacheDir) {
                Remove-Item -Path "$cacheDir\*" -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "Cloudflare cache directory cleared." -ForegroundColor Green
            }

            # Restart cloudflared to clear in-memory cache
            $tunnelProc = Get-Process -Name cloudflared -ErrorAction SilentlyContinue
            if ($tunnelProc) {
                Stop-Process -Id $tunnelProc.Id -Force
                Write-Host "Cloudflare tunnel restarted to clear cache." -ForegroundColor Green
            }
        } else {
            Write-Host "cloudflared.exe not found at expected location." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to clear Cloudflare cache: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Rebuild-XR-Vessel {
    Write-Host ">>> Refreshing XR Vessel (OMEGA_079)..." -ForegroundColor Yellow
    try {
        Push-Location "Frontend\XR_Vessel"

        # Only install if node_modules is missing
        if (-not (Test-Path "node_modules")) {
            Write-Host "node_modules missing. Installing XR Vessel dependencies..." -ForegroundColor Cyan
            $installResult = npm install 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "XR Vessel dependencies installed successfully." -ForegroundColor Green
            } else {
                Write-Host "Warning: npm install had issues, but continuing..." -ForegroundColor Yellow
                Write-Host $installResult -ForegroundColor Gray
            }
        }

        # Always run bump to update the version (Cache-busting)
        Write-Host "Bumping vessel version..." -ForegroundColor Gray
        npm run bump

        Pop-Location
    } catch {
        Write-Host "Failed to refresh XR Vessel: $($_.Exception.Message)" -ForegroundColor Red
        Pop-Location
    }
}

function Start-All {
    Write-Host ">>> Starting all services..." -ForegroundColor Cyan
    foreach ($name in $Services.Keys) {
        $cfg = $Services[$name]
        $exe = if ($cfg.Exe) { $cfg.Exe } else { $VENV_PYTHON }
        $out = Join-Path $LOG_DIR "$($name)_out.log"
        $err = Join-Path $LOG_DIR "$($name)_err.log"

        Write-Host "Starting $name..." -NoNewline
        try {
            $workingDir = if ($cfg.Path.StartsWith("$FoveAI_ROOT")) { $cfg.Path } else { Join-Path $FoveAI_ROOT $cfg.Path }
            $p = Start-Process -FilePath $exe -ArgumentList $cfg.Cmd -WorkingDirectory $workingDir `
                -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
            $Global:ActiveProcs[$name] = $p
            Write-Host " [OK] PID: $($p.Id)" -ForegroundColor Green
        } catch {
            Write-Host " [FAILED] $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

# --- Main Execution ---
Clear-Host
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   FoveAI REFRESH AND START SCRIPT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "This script will:" -ForegroundColor White
Write-Host "  1. Stop all running FoveAI processes" -ForegroundColor White
Write-Host "  2. Clean NPM cache" -ForegroundColor White
Write-Host "  3. Clear Chrome cache for foveai.1um6a.se" -ForegroundColor White
Write-Host "  4. Clear Cloudflare cache" -ForegroundColor White
Write-Host "  5. Rebuild XR Vessel dependencies" -ForegroundColor White
Write-Host "  6. Start all services fresh" -ForegroundColor White
Write-Host "----------------------------------------"

# Stop everything first
Stop-All

# Clear caches
Clean-NPM-Cache
Clear-Chrome-Cache
Clear-Cloudflare-Cache

# Clean and rebuild
Rebuild-XR-Vessel

# Wait a moment for cleanup
Start-Sleep -Seconds 2

# Start fresh
Start-All

Write-Host ">>> Waiting for system stabilization (10s)..." -ForegroundColor Gray
Start-Sleep -Seconds 10

Write-Host ">>> Injecting Neural Link..." -ForegroundColor Green
Start-Process "chrome.exe" "https://foveai.1um6a.se/"

Write-Host "`n[!] SYSTEM ACTIVE. Press ENTER at any time to SHUTDOWN and QUIT." -ForegroundColor White
Read-Host

Stop-All