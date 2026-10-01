# Register FoveAI Taskbar Tray App (FoveAI_Taskbar.pyw) across Desktop, Start Menu, and Startup
$ErrorActionPreference = 'Stop'

$RepoDir = "C:\Users\danie\program\LUMAX\FoveAI"
$PythonW = "$RepoDir\.venv\Scripts\pythonw.exe"
$TaskbarPyw = "$RepoDir\FoveAI_Taskbar.pyw"

if (-not (Test-Path $PythonW)) {
    $PythonW = "pythonw.exe"
}

$WshShell = New-Object -ComObject WScript.Shell

# 1. Desktop Shortcuts
$DesktopPaths = @(
    "C:\Users\danie\OneDrive\Skrivbord\FoveAI System Tray.lnk",
    "C:\Users\danie\OneDrive\Skrivbord\FoveAI Tray.lnk"
)

foreach ($path in $DesktopPaths) {
    $sc = $WshShell.CreateShortcut($path)
    $sc.TargetPath = $PythonW
    $sc.Arguments = "`"$TaskbarPyw`" --takeover"
    $sc.WorkingDirectory = $RepoDir
    $sc.Description = "FoveAI Advanced System Tray App (RAM/VRAM Guard, XRLF Model Selector, Foveated Memory)"
    $sc.IconLocation = "$PythonW,0"
    $sc.Save()
    Write-Host "Updated Desktop Shortcut: $path -> $TaskbarPyw"
}

# 2. Start Menu Shortcut
$StartMenuPath = "C:\Users\danie\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\FoveAI System Tray.lnk"
$scStart = $WshShell.CreateShortcut($StartMenuPath)
$scStart.TargetPath = $PythonW
$scStart.Arguments = "`"$TaskbarPyw`" --takeover"
$scStart.WorkingDirectory = $RepoDir
$scStart.Description = "FoveAI Advanced System Tray App"
$scStart.IconLocation = "$PythonW,0"
$scStart.Save()
Write-Host "Updated Start Menu Shortcut: $StartMenuPath"

# 3. Windows Startup VBS Script
$StartupVbs = "C:\Users\danie\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\FoveAITray.vbs"
$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """$PythonW"" ""$TaskbarPyw"" --takeover", 0, False
"@
Set-Content -Path $StartupVbs -Value $VbsContent -Encoding ASCII
Write-Host "Updated Startup VBS Script: $StartupVbs"

# 4. HKCU Run Registry Key
try {
    $RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Set-ItemProperty -Path $RegPath -Name "FoveAITray" -Value "`"$PythonW`" `"$TaskbarPyw`""
    Write-Host "Updated Registry HKCU Startup Key: FoveAITray"
} catch {
    Write-Warning "Could not set HKCU Run key: $_"
}

Write-Host "SUCCESS: FoveAI Advanced Taskbar Tray App registered everywhere."
