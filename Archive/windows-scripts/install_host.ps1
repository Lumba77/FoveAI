# FoveAI Native Messaging Host — Installer
# Run: powershell -ExecutionPolicy Bypass -File install_host.ps1
# This registers the host with Chrome so the extension can talk to it.

$ErrorActionPreference = 'Stop'

$nativeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $nativeDir 'com.foveai.foveai_host.json'

# Update the manifest to use absolute paths (Chrome requires this)
$batPath = Join-Path $nativeDir 'foveai_host.bat'

# Auto-read FoveAI_EXT_ID from .env file (line 106 in the project root)
$envPath = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $nativeDir))) '.env'
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath -Raw
    if ($envContent -match 'FoveAI_EXT_ID=(\S+)') {
        $env:FoveAI_EXT_ID = $matches[1].Trim()
        Write-Host "[INFO] Read FoveAI_EXT_ID from .env: $($env:FoveAI_EXT_ID)"
    }
}

# Build allowed_origins — use specific extension ID if provided, else wildcard
$allowedOrigins = @('chrome-extension://*/')
if ($env:FoveAI_EXT_ID) {
    $extId = $env:FoveAI_EXT_ID.Trim()
    $allowedOrigins = @("chrome-extension://$extId/")
    Write-Host "[INFO] Using extension ID: $extId"
} else {
    Write-Host "[INFO] No FoveAI_EXT_ID set — using wildcard (works for development)"
    Write-Host "[TIP] Set FoveAI_EXT_ID in .env file for production"
}

# Rewrite manifest with absolute bat path
$manifest = @{
    name        = 'com.foveai.foveai_host'
    description = 'FoveAI Native Messaging Host — system control from browser'
    path        = $batPath
    type        = 'stdio'
    allowed_origins = $allowedOrigins
} | ConvertTo-Json -Depth 3

# Write UTF-8 WITHOUT BOM — Chrome rejects BOM in native messaging manifests
[System.IO.File]::WriteAllText($manifestPath, $manifest, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] Manifest written: $manifestPath"
Write-Host "[OK] Native host path: $batPath"

# Verify the bat and py files exist
if (-not (Test-Path $batPath)) {
    Write-Host "[WARN] foveai_host.bat not found at $batPath — creating it..."
    $pyPath = Join-Path $nativeDir 'nm_host.py'
    $foveaiRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $nativeDir))
    Set-Content -Path $batPath -Value "@echo off`r`npython `"$pyPath`" `"$foveaiRoot`"`r`n" -Encoding ASCII
    Write-Host "[OK] Created foveai_host.bat"
}
if (-not (Test-Path (Join-Path $nativeDir 'nm_host.py'))) {
    Write-Host "[ERROR] nm_host.py not found in $nativeDir"
    exit 1
}

# Register in Windows registry (HKCU — no admin needed)
$regKey = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.foveai.foveai_host'
if (-not (Test-Path $regKey)) {
    New-Item -Path $regKey -Force | Out-Null
}
Set-ItemProperty -Path $regKey -Name '(Default)' -Value $manifestPath
Write-Host "[OK] Registry key created: $regKey"
Write-Host ""
Write-Host "=========================================="
Write-Host "  FoveAI native messaging host installed!"
Write-Host "=========================================="
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open chrome://extensions/ and reload the FoveAI extension"
Write-Host "  2. Click the FoveAI icon in your toolbar"
Write-Host "  3. Click 'Detect Installed' to scan for LLM backends"
