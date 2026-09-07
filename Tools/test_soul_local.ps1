<#
.SYNOPSIS
Tests the Sovereign Core (Soul) in isolation to print raw startup logs.

.DESCRIPTION
Runs compagent.py directly within the Python virtual environment.
This bypasses the sleipnir_launcher.js log filters, allowing you to see 
the pure output from Llama.cpp, including any Out-Of-Memory exceptions 
or loading sequences.
#>

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location -Path $workspaceRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  TESTING THE SOUL (compagent.py) IN ISOLATION" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Ensure we have the .venv
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "[ERROR] Virtual environment '.\.venv' not found!" -ForegroundColor Red
    exit 1
}

Write-Host "[SYSTEM] Activating virtual environment..." -ForegroundColor DarkGray
& ".\.venv\Scripts\Activate.ps1"

Write-Host "[SYSTEM] Launching Sovereign Core..." -ForegroundColor Yellow
Write-Host "[SYSTEM] Any crashes or Memory Errors will be printed below:`n" -ForegroundColor DarkGray

python Backend\Cognition\compagent.py
