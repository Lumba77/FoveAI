# Forwarding wrapper for backward compatibility -> Set-FoveAISetting.ps1
param(
    [Parameter(Mandatory=$false)]
    [string]$Key,
    
    [Parameter(Mandatory=$false)]
    [string]$Value,
    
    [Parameter(Mandatory=$false)]
    [int]$FoveaLevel = -1
)

$targetScript = Join-Path $PSScriptRoot "Set-FoveAISetting.ps1"
if (Test-Path $targetScript) {
    & $targetScript -Key $Key -Value $Value -FoveaLevel $FoveaLevel
} else {
    Write-Error "Set-FoveAISetting.ps1 not found."
}
