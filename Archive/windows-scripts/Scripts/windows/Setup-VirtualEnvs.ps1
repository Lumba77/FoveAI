# Unified Virtual Environment Setup for FoveAI
# Creates high-performance Python 3.10 environments:
# 1. .venv -> Core backend services (Soul, Memory, Mouth/TTS, etc.)

$ErrorActionPreference = 'Stop'
$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VENV_UNIFIED = Join-Path $FoveAI_ROOT ".venv"
$VENV_MOUTH = Join-Path $FoveAI_ROOT ".venv"
$REQ_UNIFIED = Join-Path $FoveAI_ROOT "requirements.txt"
$REQ_MOUTH = Join-Path $FoveAI_ROOT "requirements.txt"

Write-Host "=== FoveAI Venv Backend Setup ===" -ForegroundColor Cyan

# 1. Check for uv
$UV = Get-Command 'uv' -ErrorAction SilentlyContinue
if (-not $UV) {
    Write-Host "Error: 'uv' not found. Please install it with: powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Red
    exit 1
}
Write-Host "Using uv: $($UV.Source)"

# Helper function to set up a virtual environment
function Setup-Venv {
    param(
        [string]$Path,
        [string]$Req,
        [string]$Name
    )
    Write-Host "`nSetting up $Name environment at '$Path'..." -ForegroundColor Green
    if (Test-Path $Path) { 
        Write-Host "Removing existing environment at $Path..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $Path 
    }
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $UV venv --python 3.10 $Path
    $ErrorActionPreference = $oldEAP
    $py = Join-Path $Path "Scripts\python.exe"
    if (Test-Path $Req) {
        Write-Host "Installing requirements from $Req..."
        & $UV pip install --python $py -r $Req
    } else {
        Write-Warning "Requirements file $Req not found! Skipping pip install."
    }
}

# 2. Setup Environments
if ($VENV_MOUTH -eq $VENV_UNIFIED) {
    Setup-Venv -Path $VENV_UNIFIED -Req $REQ_UNIFIED -Name "Unified (.venv)"
} else {
    Setup-Venv -Path $VENV_UNIFIED -Req $REQ_UNIFIED -Name "Unified (.venv)"
    Setup-Venv -Path $VENV_MOUTH -Req $REQ_MOUTH -Name "Mouth (Isolated)"
}

Write-Host "`n=== Setup Complete! ===" -ForegroundColor Green
Write-Host "Unified Venv: $VENV_UNIFIED"
if ($VENV_MOUTH -ne $VENV_UNIFIED) {
    Write-Host "Mouth Venv:   $VENV_MOUTH"
}
