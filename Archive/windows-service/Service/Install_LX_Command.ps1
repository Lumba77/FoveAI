# FoveAI CLI Command Installer
# Adds FoveAI root to PATH and sets up the 'start' alias.

$FoveAI_ROOT = $PSScriptRoot
$COMMAND_NAME = "foveai"

Write-Host "Installing FoveAI 'foveai' command..." -ForegroundColor Cyan

# 1. Add to Session Path
if ($env:Path -notlike "*$FoveAI_ROOT*") {
    $env:Path += ";$FoveAI_ROOT"
}

# 2. Add to User Path (Permanent)
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$FoveAI_ROOT*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$FoveAI_ROOT", "User")
    Write-Host "✅ Added $FoveAI_ROOT to User PATH." -ForegroundColor Green
}

# 3. Handle PowerShell Alias
$profilePath = $PROFILE
if (-not (Test-Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}

$aliasLine = "function $COMMAND_NAME { & `"$FoveAI_ROOT\foveai.cmd`" @args }"
$profileContent = Get-Content $profilePath -ErrorAction SilentlyContinue
if ($profileContent -notcontains $aliasLine) {
    Add-Content -Path $profilePath -Value "`n# FoveAI Orchestrator Alias`n$aliasLine"
    Write-Host "✅ Added 'foveai' alias to your PowerShell Profile." -ForegroundColor Green
}

Write-Host "`nInstallation Complete! Restart your terminal or run:" -ForegroundColor Gray
Write-Host "  . `$PROFILE" -ForegroundColor Yellow
Write-Host "Then just type: $COMMAND_NAME" -ForegroundColor Green
