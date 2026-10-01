#Requires -Version 5.1
# Build LumaxStressMeter.exe (one-file, no console window).
# Requires Python 3 with pip. Run from this folder: .\build_exe.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --clean --onefile --windowed --name LumaxStressMeter `
    --hidden-import appbar_win32 `
    stress_meter.py

Write-Host "Output: $PSScriptRoot\dist\LumaxStressMeter.exe" -ForegroundColor Green
