# Register 'foveai' command globally
# Adds the FoveAI root directory to the system PATH so 'foveai' works from any directory.
# Run as Administrator. Non-destructive — only adds if not already present.

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "ERROR: Must run as Administrator." -ForegroundColor Red
    exit 1
}

$FoveAI_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$cmdPath = Join-Path $FoveAI_ROOT "foveai.cmd"

if (-not (Test-Path $cmdPath)) {
    Write-Host "ERROR: foveai.cmd not found at $cmdPath" -ForegroundColor Red
    exit 1
}

# Get current system PATH
$currentPath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$pathEntries = $currentPath -split ";" | Where-Object { $_ -ne "" }

# Check if already registered
if ($pathEntries -contains $FoveAI_ROOT) {
    Write-Host "'foveai' is already registered globally." -ForegroundColor Green
    Write-Host "You can run 'foveai' from any directory." -ForegroundColor Gray
    exit 0
}

# Add to PATH
$newPath = ($pathEntries + $FoveAI_ROOT) -join ";"
[System.Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")

Write-Host "Added $FoveAI_ROOT to system PATH." -ForegroundColor Green
Write-Host ""
Write-Host "=== Registration Complete ===" -ForegroundColor Green
Write-Host "Open a NEW terminal window, then type:" -ForegroundColor Cyan
Write-Host "  foveai        # Full dashboard" -ForegroundColor White
Write-Host "  foveai vr     # Start VR vessel" -ForegroundColor White
Write-Host "  foveai web    # Start Web vessel" -ForegroundColor White
Write-Host "  foveai con    # Start CON vessel" -ForegroundColor White
Write-Host ""
Write-Host "To unregister: Service\Unregister_Global_Lumax.ps1" -ForegroundColor Gray