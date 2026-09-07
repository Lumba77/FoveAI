param(
    [Parameter(Mandatory=$false)]
    [string]$Key,
    
    [Parameter(Mandatory=$false)]
    [string]$Value,
    
    [Parameter(Mandatory=$false)]
    [int]$FoveaLevel = -1
)

# Resolve repository root (FoveAI directory)
$ScriptDir = Get-Item $PSScriptRoot
$FoveAIRoot = if ($ScriptDir.Parent.Name -eq "Scripts") { $ScriptDir.Parent.Parent.FullName } else { $ScriptDir.Parent.FullName }
$envFile = Join-Path $FoveAIRoot ".env"

if (-not (Test-Path $envFile)) {
    # Fallback check
    $envFile = "C:\Users\danie\program\LUMAX\FoveAI\.env"
}

if ($FoveaLevel -ge 0) {
    $Key = "XRLF_PROXY_AGGRESSION"
    $Value = $FoveaLevel.ToString()
}

if (-not $Key) {
    Write-Error "Key must be provided if FoveaLevel is not set."
    exit 1
}

$lines = @()
if (Test-Path $envFile) {
    $rawContent = Get-Content $envFile -Raw -Encoding utf8
    if ($rawContent) {
        $lines = $rawContent -split "`r`n|`n"
    }
}

$found = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
    $line = $lines[$i].Trim()
    if ($line -match "^$Key=(.*)$") {
        $lines[$i] = "$Key=$Value"
        $found = $true
        break
    }
}

if (-not $found) {
    $lines += "$Key=$Value"
}

$lines -join "`n" | Set-Content $envFile -Encoding UTF8

Write-Host "Set $Key=$Value in $envFile" -ForegroundColor Green

# Automatically trigger service restarts for critical keys
$restartScript = Join-Path $PSScriptRoot "Restart_Services.ps1"
if (Test-Path $restartScript) {
    if ($Key -eq "XRLF_PROXY_AGGRESSION" -or $Key.StartsWith("FoveAI_")) {
        Write-Host "Restarting services to apply configuration change..." -ForegroundColor Cyan
        & $restartScript
    }
}
