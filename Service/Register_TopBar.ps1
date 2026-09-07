# FoveAI Top Bar Re-Registration Script
# Re-installs the LumaxTopBar to Windows Startup folder
# Run this once to re-enable auto-start on boot

param(
    [switch]$Uninstall
)

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "LumaxTopBar.lnk"
$TopBarScript = Join-Path $FoveAI_ROOT "Tools" "foveai_top_bar" "foveai_top_bar.py"

function Write-Status { param($Color, $Msg) Write-Host $Msg -ForegroundColor $Color }

if ($Uninstall) {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Status Green "✅ Top bar shortcut removed from Startup."
    } else {
        Write-Status Yellow "⚠ No top bar shortcut found in Startup."
    }
    
    # Also kill any running top bar
    $running = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*foveai_top_bar*"
    }
    if ($running) {
        $running | Stop-Process -Force
        Write-Status Green "✅ Top bar process stopped."
    }
    exit 0
}

# Check if top bar script exists
if (-not (Test-Path $TopBarScript)) {
    Write-Status Red "❌ Top bar script not found at: $TopBarScript"
    Write-Status Yellow "   Expected at: Tools/foveai_top_bar/foveai_top_bar.py"
    exit 1
}

# Check if Python is available
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    Write-Status Red "❌ Python not found in PATH"
    exit 1
}

# Create shortcut in Startup folder
try {
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $pythonPath
    $shortcut.Arguments = "`"$TopBarScript`""
    $shortcut.WorkingDirectory = $FoveAI_ROOT
    $shortcut.IconLocation = "$pythonPath,0"
    $shortcut.Description = "FoveAI Top Bar — System Command Center"
    $shortcut.Save()
    Write-Status Green "✅ Top bar shortcut installed to Startup:"
    Write-Status Gray "   $ShortcutPath"
} catch {
    Write-Status Red "❌ Failed to create shortcut: $_"
    exit 1
}

# Start the top bar now
Write-Status Cyan "🚀 Starting LumaxTopBar..."
try {
    $process = Start-Process -FilePath $pythonPath -ArgumentList "`"$TopBarScript`"" -WindowStyle Normal -PassThru
    Write-Status Green "✅ LumaxTopBar started (PID: $($process.Id))"
} catch {
    Write-Status Yellow "⚠ Could not start top bar: $_"
    Write-Status Yellow "   It will start automatically on next login."
}

Write-Status ""
Write-Status Green "=== Registration Complete ==="
Write-Status Gray "The LumaxTopBar will now start automatically when you log in."
Write-Status Gray "To remove: .\Register_TopBar.ps1 -Uninstall"
Write-Status Gray "To start now: python Tools/foveai_top_bar/foveai_top_bar.py"