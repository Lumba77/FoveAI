# swap_vhdx.ps1
# This script safely swaps ext4.vhdx with ext4_2.vhdx for the Docker WSL distribution.

$dockerPath = "C:\Users\lumba\AppData\Local\Docker\wsl\main\DockerDesktopWSL\main"
$primary = Join-Path $dockerPath "ext4.vhdx"
$secondary = Join-Path $dockerPath "ext4_2.vhdx"
$temp = Join-Path $dockerPath "ext4_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').vhdx"

Write-Host "--- Docker VHDX Swap Utility ---" -ForegroundColor Cyan

# 1. Stop Docker and WSL processes
Write-Host "Killing Docker and WSL processes..." -ForegroundColor Yellow
$processesToKill = @("Docker Desktop", "com.docker.backend", "com.docker.build", "docker-agent", "docker-sandbox", "vmmemWSL", "wslservice", "wslhost", "wslrelay")
foreach ($p in $processesToKill) {
    Get-Process -Name $p -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# 2. Shutdown WSL for good measure
Write-Host "Forcing WSL shutdown..."
wsl --shutdown
Start-Sleep -Seconds 5

# 3. Check for files
if (!(Test-Path $primary)) {
    Write-Error "Primary file not found: $primary"
    exit
}
if (!(Test-Path $secondary)) {
    Write-Error "Secondary file not found: $secondary"
    exit
}

# 4. Perform the swap
Write-Host "Performing swap..." -ForegroundColor Yellow
try {
    # Rename primary to temp
    Rename-Item -Path $primary -NewName (Split-Path $temp -Leaf) -ErrorAction Stop
    Write-Host "Renamed primary to backup: $temp"
    
    # Rename secondary to primary
    Rename-Item -Path $secondary -NewName "ext4.vhdx" -ErrorAction Stop
    Write-Host "Renamed secondary to primary: ext4.vhdx"
    
    # Optionally rename temp to secondary if you want a true swap
    Rename-Item -Path $temp -NewName "ext4_2.vhdx" -ErrorAction Stop
    Write-Host "Swap complete! Backup is now ext4_2.vhdx." -ForegroundColor Green
}
catch {
    Write-Error "Failed to swap files: $_"
    Write-Host "Attempting to restore original state..." -ForegroundColor Red
    if (Test-Path $temp) { Rename-Item -Path $temp -NewName "ext4.vhdx" -ErrorAction SilentlyContinue }
}

Write-Host "`nDone. You can now restart Docker Desktop." -ForegroundColor Cyan
