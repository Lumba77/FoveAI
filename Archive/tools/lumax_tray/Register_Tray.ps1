<#
.SYNOPSIS
  Register or unregister the FoveAI System Tray Icon for auto-start on Windows login.
.DESCRIPTION
  Creates a VBS launcher in the Windows Startup folder that runs the tray icon silently.
  The tray icon provides Start/Stop Stack, Open Web UI, Service Status, and more.
#>

param(
    [switch]$Uninstall
)

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$StartupFolder = [Environment]::GetFolderPath("Startup")
$VbsPath = Join-Path $StartupFolder "FoveAITray.vbs"
$TrayScript = Join-Path $FoveAI_ROOT "FoveAI_Taskbar.pyw"

function Write-Status { param($Color, $Msg) Write-Host $Msg -ForegroundColor $Color }

if ($Uninstall) {
    if (Test-Path $VbsPath) {
        Remove-Item $VbsPath -Force
        Write-Status Green "✅ Tray icon shortcut removed from Startup."
    } else {
        Write-Status Yellow "⚠ No tray icon shortcut found in Startup."
    }
    
    # Also kill any running tray icon
    $running = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*FoveAI_Taskbar*" -or $_.CommandLine -like "*foveai_tray*"
    }
    if ($running) {
        $running | Stop-Process -Force
        Write-Status Green "✅ Tray icon process stopped."
    }
    exit 0
}

# Check if tray script exists
if (-not (Test-Path $TrayScript)) {
    Write-Status Red "❌ Tray script not found at: $TrayScript"
    exit 1
}

# Use local workspace .venv python if available
$venvPython = Join-Path $FoveAI_ROOT ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path $venvPython) { $venvPython } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $pythonPath) {
    Write-Status Red "❌ Python not found in PATH or .venv"
    exit 1
}

# Create VBS launcher in Startup folder
try {
    $vbsContent = @"
CreateObject("Wscript.Shell").Run """$pythonPath"" ""$TrayScript""", 0, False
"@
    Set-Content -Path $VbsPath -Value $vbsContent -Force
    Write-Status Green "✅ Tray icon VBS launcher installed to Startup:"
    Write-Status Gray "   $VbsPath"
} catch {
    Write-Status Red "❌ Failed to create VBS launcher: $_"
    exit 1
}

# Start the tray icon now
Write-Status Cyan "🚀 Starting LumaxTray..."
try {
    $process = Start-Process -FilePath $pythonPath -ArgumentList "`"$TrayScript`"" -WindowStyle Normal -PassThru
    Write-Status Green "✅ LumaxTray started (PID: $($process.Id))"
} catch {
    Write-Status Yellow "⚠ Could not start tray icon: $_"
    Write-Status Yellow "   It will start automatically on next login."
}

Write-Status ""
Write-Status Green "=== Registration Complete ==="
Write-Status Gray "The FoveAI Tray Icon will now start automatically when you log in."
Write-Status Gray "To remove: .\Register_Tray.ps1 -Uninstall"
Write-Status Gray "To start now: python Tools/foveai_tray/foveai_tray.py"