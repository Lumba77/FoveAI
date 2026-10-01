#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start the Creative Service using its dedicated virtual environment.
    
.DESCRIPTION
    Launches the creative_service.py using the isolated .venv/creative environment.
    This ensures the service has its own dependencies without conflicts from other services.
    
.EXAMPLE
    .\start_creative_venv.ps1
    .\start_creative_venv.ps1 -Port 8004  # Run on alternate port
#>

param(
    [int]$Port = 8003,
    [switch]$Background
)

$ScriptDir = Split-Path $MyInvocation.MyCommand.Path -Parent
$RepoRoot = Split-Path $ScriptDir -Parent | Split-Path -Parent
$VenvPython = Join-Path $RepoRoot ".venv\creative\Scripts\python.exe"

# Check venv exists
if (-not (Test-Path $VenvPython)) {
    Write-Host "Error: Creative venv not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run: .\Setup-VirtualEnvs.ps1 -Service creative" -ForegroundColor Yellow
    exit 1
}

# Set environment variables from .env
$EnvFile = Join-Path $RepoRoot ".env"
if (Test-Path $EnvFile) {
    Write-Host "Loading environment from $EnvFile"
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and $line -notmatch '^#' -and $line -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value -match '^["''](.*)["'']$') {
                $value = $matches[1]
            }
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Ensure InvokeAI integration is configured
if (-not $env:FoveAI_INVOKEAI_MODELS_CSV) {
    $env:FoveAI_INVOKEAI_MODELS_CSV = Join-Path $RepoRoot "tools\invokeai_models_inventory.csv"
}
if (-not $env:FoveAI_INVOKEAI_MODELS_ROOT) {
    $env:FoveAI_INVOKEAI_MODELS_ROOT = "C:\Users\lumba\Program\InvokeAI\models"
}

Write-Host "Starting Creative Service on port $Port"
Write-Host "Using Python: $VenvPython"

$arguments = @(
    (Join-Path $ScriptDir "creative_service.py"),
    "--port", $Port
)

if ($Background) {
    Start-Process -FilePath $VenvPython -ArgumentList $arguments -WorkingDirectory $ScriptDir -WindowStyle Hidden
    Write-Host "Service started in background"
} else {
    & $VenvPython $arguments
}