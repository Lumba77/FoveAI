# Create FoveAI Start Menu shortcuts
$shell = New-Object -ComObject WScript.Shell
$startMenu = [Environment]::GetFolderPath("StartMenu")
$foveaiMenu = Join-Path $startMenu "Programs\FoveAI"
if (-not (Test-Path $foveaiMenu)) { New-Item -ItemType Directory -Path $foveaiMenu -Force | Out-Null }

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# --- Tray shortcut ---
$trayLnk = Join-Path $foveaiMenu "FoveAI Tray.lnk"
$tray = $shell.CreateShortcut($trayLnk)
$tray.TargetPath = "powershell.exe"
$tray.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$FoveAI_ROOT\Service\LumaxTray.ps1`""
$tray.WorkingDirectory = $FoveAI_ROOT
$tray.IconLocation = "powershell.exe,0"
$tray.Description = "FoveAI System Tray — click for ON/OFF, right-click for menu"
$tray.Save()

# --- Console shortcut ---
$conLnk = Join-Path $foveaiMenu "FoveAI Console.lnk"
$con = $shell.CreateShortcut($conLnk)
$con.TargetPath = "powershell.exe"
$con.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$FoveAI_ROOT\Start_FoveAI.ps1`""
$con.WorkingDirectory = $FoveAI_ROOT
$con.IconLocation = "powershell.exe,0"
$con.Description = "FoveAI Full Dashboard — live meters and controls"
$con.Save()

Write-Host "Created Start Menu shortcuts:" -ForegroundColor Green
Write-Host "  → FoveAI Tray" -ForegroundColor Cyan
Write-Host "  → FoveAI Console" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now search 'FoveAI' in the Start Menu." -ForegroundColor Yellow