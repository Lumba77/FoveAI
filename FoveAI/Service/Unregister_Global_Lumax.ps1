# Unregister 'foveai' command globally
# Removes the FoveAI root directory from the system PATH.
# Run as Administrator.

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

# Get current system PATH
$currentPath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$pathEntries = $currentPath -split ";" | Where-Object { $_ -ne "" }

if ($pathEntries -notcontains $FoveAI_ROOT) {
    Write-Host "'foveai' was not registered globally." -ForegroundColor Yellow
    exit 0
}

# Remove from PATH
$newPath = ($pathEntries | Where-Object { $_ -ne $FoveAI_ROOT }) -join ";"
[System.Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")

Write-Host "Removed $FoveAI_ROOT from system PATH." -ForegroundColor Green
Write-Host "'foveai' is no longer available globally." -ForegroundColor Gray