$WshShell = New-Object -ComObject WScript.Shell

# 1. Startup VBS Launcher
$startupFolder = [Environment]::GetFolderPath("Startup")
$vbsPath = Join-Path $startupFolder "FoveAITray.vbs"
$vbsContent = 'CreateObject("Wscript.Shell").Run """C:\Users\danie\program\LUMAX\FoveAI\.venv\Scripts\python.exe"" ""C:\Users\danie\program\LUMAX\FoveAI\Tools\lumax_tray\foveai_tray.py""", 0, False'
Set-Content -Path $vbsPath -Value $vbsContent -Force
Write-Host "✅ Startup VBS verified: $vbsPath" -ForegroundColor Green

# 2. Desktop Shortcut
$desktopPath = [Environment]::GetFolderPath("Desktop")
$desktopLnk = Join-Path $desktopPath "FoveAI System Tray.lnk"
$s1 = $WshShell.CreateShortcut($desktopLnk)
$s1.TargetPath = "C:\Users\danie\program\LUMAX\FoveAI\.venv\Scripts\python.exe"
$s1.Arguments = "Tools\lumax_tray\foveai_tray.py"
$s1.WorkingDirectory = "C:\Users\danie\program\LUMAX\FoveAI"
$s1.Description = "FoveAI System Tray Launcher & Orchestrator"
$s1.Save()
Write-Host "✅ Desktop shortcut verified: $desktopLnk" -ForegroundColor Green

# 3. Start Menu Shortcut
$startMenuPath = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
$startMenuLnk = Join-Path $startMenuPath "FoveAI System Tray.lnk"
$s2 = $WshShell.CreateShortcut($startMenuLnk)
$s2.TargetPath = "C:\Users\danie\program\LUMAX\FoveAI\.venv\Scripts\python.exe"
$s2.Arguments = "Tools\lumax_tray\foveai_tray.py"
$s2.WorkingDirectory = "C:\Users\danie\program\LUMAX\FoveAI"
$s2.Description = "FoveAI System Tray Launcher & Orchestrator"
$s2.Save()
Write-Host "✅ Start Menu shortcut verified: $startMenuLnk" -ForegroundColor Green
