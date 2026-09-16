# --- Lumax Top Bar Build System ---
# Generates a signed, authoritative EXE with AppBar priority.

$ProjectRoot = "C:\Users\lumba\Program\FoveAI"
$BuildDir = "$ProjectRoot\Tools\foveai_top_bar"
$DistDir = "$BuildDir\dist"
$ExeName = "LumaxTopBar.exe"
$InstallDir = "C:\Program Files\LumaxTopBar"
$SignTool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"

Write-Host "--- Lumax Authoritative Build System ---" -ForegroundColor Cyan

# 1. Enter Directory
Set-Location $BuildDir

# Kill any locked running Top Bar processes before compilation to prevent PermissionError
Write-Host "Stopping any running LumaxTopBar processes to unlock files..." -ForegroundColor Yellow
Stop-Process -Name "LumaxTopBar" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# 2. Compile EXE
Write-Host "Compiling EXE with uiAccess manifest..." -ForegroundColor Yellow
pyinstaller --noconfirm --onefile --windowed `
    --name "LumaxTopBar" `
    --manifest "foveai_top_bar.manifest" `
    --add-data "appbar_win32.py;." `
    --clean `
    "foveai_top_bar.py"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller failed." -ForegroundColor Red
    exit 1
}

# 3. Code Signing (Local Development Cert)
Write-Host "Signing EXE..." -ForegroundColor Yellow
$CertThumbprint = (Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.Subject -match "Lumax" } | Select-Object -First 1).Thumbprint

if (-not $CertThumbprint) {
    Write-Host "No Lumax certificate found. Creating temporary one..." -ForegroundColor Gray
    $Cert = New-SelfSignedCertificate -Type Custom -Subject "CN=Lumax Sovereign" -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3") -KeyUsage DigitalSignature -FriendlyName "Lumax Sovereign Developer" -CertStoreLocation "Cert:\CurrentUser\My"
    $CertThumbprint = $Cert.Thumbprint
}

if (Test-Path $SignTool) {
    & $SignTool sign /sha1 $CertThumbprint /fd sha256 /t http://timestamp.digicert.com "$DistDir\LumaxTopBar.exe"
} else {
    Write-Host "WARNING: SignTool not found at $SignTool. Skipping signing." -ForegroundColor Yellow
}

# 4. Deploy to Program Files
Write-Host "Deploying to $InstallDir..." -ForegroundColor Cyan
Stop-Process -Name "LumaxTopBar" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force
}

Copy-Item -Path "$DistDir\LumaxTopBar.exe" -Destination "$InstallDir\$ExeName" -Force

Write-Host "SUCCESS: Authoritative Lumax Top Bar deployed." -ForegroundColor Green
Write-Host "Launch with: & '$InstallDir\$ExeName'" -ForegroundColor Gray
