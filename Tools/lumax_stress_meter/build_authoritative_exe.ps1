# build_authoritative_exe.ps1
# Automates the creation of a signed EXE with uiAccess privileges to stay above the Start Menu.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "--- Lumax Authoritative Build System ---" -ForegroundColor Cyan

# 1. Check for PyInstaller
if (!(Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "Installing PyInstaller..."
    pip install pyinstaller
}

# 2. Handle Self-Signed Certificate
$CertName = "LumaxLocalDev"
$Cert = Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.Subject -like "*CN=$CertName*" } | Select-Object -First 1

if (!$Cert) {
    Write-Host "Generating local signing certificate..."
    $Cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=$CertName" -KeyUsage DigitalSignature -FriendlyName "Lumax Local Signing" -CertStoreLocation "Cert:\CurrentUser\My"
    
    # Export and Import to Trusted Root (Requires Admin for the import part, but CurrentUser usually works for local execution)
    Write-Host "NOTE: To activate Z-order authority, you may need to manually export this cert and add it to 'Trusted Root Certification Authorities'." -ForegroundColor Yellow
}

# 3. Build the EXE
Write-Host "Compiling EXE with uiAccess manifest..."
pyinstaller --noconfirm --onefile --windowed `
    --name "LumaxStressMeter" `
    --manifest "stress_meter.manifest" `
    --clean `
    "stress_meter.py"

# 4. Sign the EXE
$ExePath = Join-Path $ScriptDir "dist\LumaxStressMeter.exe"
if (Test-Path $ExePath) {
    Write-Host "Signing EXE..."
    Set-AuthenticodeSignature -FilePath $ExePath -Certificate $Cert
    Write-Host "SUCCESS: Signed EXE created at $ExePath" -ForegroundColor Green
    Write-Host "IMPORTANT: You MUST move this EXE to 'C:\Program Files\' for the Start Menu bypass to work." -ForegroundColor Cyan
} else {
    Write-Error "Build failed: EXE not found."
}