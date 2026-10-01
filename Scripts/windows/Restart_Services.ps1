# FoveAI Service Restart with New Configuration
# Kills existing services and restarts them to pick up .env changes

[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseDeclaredVarsMoreThanAssignments', 'modelPath', Justification='Variable is used in configuration check below')]
param([switch]$KillOnly)

$FoveAI_ROOT = $PSScriptRoot

function Write-Status {
    param([string]$Message, [string]$Color = "White")
    $colors = @{ "Green" = "32"; "Yellow" = "33"; "Red" = "31"; "Cyan" = "36"; "White" = "37" }
    $code = $colors[$Color]
    Write-Host "$([char]27)[${code}m$Message$([char]27)[0m"
}

# Kill existing FoveAI Python services
Write-Status "`n=== Stopping FoveAI Services ===" "Cyan"

$ports = @(8000, 8001, 8002, 8003, 8004, 8080)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Status "Killing $($proc.ProcessName) (PID $($proc.Id)) on port $port" "Yellow"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

# Also kill by process names we know
$pythons = Get-Process python -ErrorAction SilentlyContinue | Where-Object { 
    $_.Path -like "*FoveAI-lite*" 
}
foreach ($p in $pythons) {
    Write-Status "Killing FoveAI python PID $($p.Id)" "Yellow"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

if ($KillOnly) {
    Write-Status "`nServices stopped. Run Start_FoveAI.ps1 manually to restart." "Green"
    exit 0
}

# Verify model exists (used in configuration check)
$modelPath = $env:FoveAI_MODEL_PATH
if (-not $modelPath) {
    # Load from .env
    $envFile = Join-Path $FoveAI_ROOT ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^FoveAI_MODEL_PATH=(.*)$') {
                $modelPath = $matches[1].Trim()
            }
        }
    }
}

Write-Status "`n=== Configuration Check ===" "Cyan"
if ($modelPath -and (Test-Path $modelPath)) {
    Write-Status "Soul model: $modelPath [EXISTS]" "Green"
} elseif ($modelPath) {
    Write-Status "Soul model: $modelPath [MISSING - CRITICAL]" "Red"
} else {
    Write-Status "Soul model: NOT CONFIGURED" "Red"
}

# Check Ollama models
Write-Status "`nChecking Ollama models..." "Cyan"
try {
    $ollamaModels = curl -s http://localhost:11434/api/tags | ConvertFrom-Json
    $modelNames = $ollamaModels.models.name
    $required = @("dolphin3:8b", "nomic-embed-text:latest")
    foreach ($r in $required) {
        if ($modelNames -contains $r) {
            Write-Status "  $r [OK]" "Green"
        } else {
            Write-Status "  $r [MISSING - run: ollama pull $r]" "Yellow"
        }
    }
} catch {
    Write-Status "  Ollama not responding on :11434" "Red"
}

Write-Status "`n=== Restart Complete ===" "Green"
Write-Status "Now run: .\Start_FoveAI.ps1" "Cyan"
Write-Status "Or use the system tray icon to restart services.`n" "White"