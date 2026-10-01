# Bootstrap-FoveAI.ps1
# This script recreates the 10 FoveAI virtual environments natively on Windows.
# Run this from the root of your C:\Users\lumba\Program\FoveAI directory.

$ErrorActionPreference = "Stop"

$venvs = @{
    "soul"      = "requirements_soul.txt"
    "memory"    = "requirements_memory.txt"
    "creative"  = "requirements_creative.txt"
    "webui"     = "requirements_webui.txt"
    "ears"      = "requirements_ears.txt"
    "mouth"     = "requirements_mouth.txt"
    "ops"       = "requirements_ops.txt"
    "sentry"    = "requirements_sentry.txt"
    "soul_donor" = "requirements_foveai_donor.txt"
    "main"      = "requirements_main.txt"
}

Write-Host "--- FoveAI Windows Bootstrap Starting ---" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    New-Item -ItemType Directory -Path ".venv" | Out-Null
}

foreach ($name in $venvs.Keys) {
    $reqFile = $venvs[$name]
    $venvPath = ".venv\$name"
    
    Write-Host "`n[+] Setting up Environment: $name" -ForegroundColor Green
    
    if (Test-Path $venvPath) {
        Write-Host "    Found existing venv at $venvPath. Skipping creation..." -ForegroundColor Yellow
    } else {
        Write-Host "    Creating virtual environment..."
        python -m venv $venvPath
    }

    $pipPath = "$venvPath\Scripts\pip.exe"
    
    if (Test-Path $reqFile) {
        Write-Host "    Installing requirements from $reqFile..."
        & $pipPath install --quiet -r $reqFile
    } else {
        Write-Warning "    Requirement file $reqFile not found!"
    }
}

Write-Host "`n--- All Environments Prepared ---" -ForegroundColor Cyan
Write-Host "You can now start services using your .ps1 start scripts."
