# ═══════════════════════════════════════════════════════════════
#  FoveAI Route / Mode / Provider Switcher
#  Thin wrapper around Set-LumaxSetting.ps1 (single source of truth).
# ═══════════════════════════════════════════════════════════════
param(
    [Parameter(Position = 0)]
    [ValidateSet("menu", "local", "cloud", "status", "fovea")]
    [string]$Action = "menu",
    [Parameter(Position = 1)]
    [ValidateRange(0, 6)]
    [int]$FoveaLevel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$SetScript = Join-Path $RepoRoot "Scripts\windows\Set-LumaxSetting.ps1"

function Get-CurrentMode {
    try {
        $lines = Get-Content (Join-Path $RepoRoot ".env") -Raw
        if ($lines -match 'FoveAI_COGNITIVE_MODE\s*=\s*(\w+)') { return $Matches[1].ToLower() }
    } catch {}
    return "unknown"
}

function Get-CurrentProvider {
    try {
        $lines = Get-Content (Join-Path $RepoRoot ".env") -Raw
        if ($lines -match 'FoveAI_CHAT_PROVIDER\s*=\s*([^\r\n]+)') { return $Matches[1].Trim().ToLower() }
    } catch {}
    return "unknown"
}

function Get-CurrentFovea {
    try {
        $lines = Get-Content (Join-Path $RepoRoot ".env") -Raw
        if ($lines -match 'FoveAI_PROXY_AGGRESSION\s*=\s*(\d+)') { return $Matches[1] }
    } catch {}
    return "0"
}

function Get-FoveaLabel {
    param([int]$Level)
    $labels = @{
        0 = "Auto (model-detected)"
        1 = "L1 Max Compression (x0.32)"
        2 = "L2 Standard (x1.0)"
        3 = "L3 Moderate (x2.0)"
        4 = "L4 Light (x4.0)"
        5 = "L5 Minimal (x10.0)"
        6 = "L6 Almost Raw (x25.0)"
    }
    return $labels[$Level] & "Unknown"
}

function Show-Status {
    $mode = Get-CurrentMode
    $provider = Get-CurrentProvider
    $fovea = Get-CurrentFovea
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor DarkCyan
    Write-Host "║   FoveAI Route Status                             ║" -ForegroundColor DarkCyan
    Write-Host "╠══════════════════════════════════════════════════╣" -ForegroundColor DarkCyan
    Write-Host "║   Cognitive Mode:  $mode" -ForegroundColor $(if ($mode -eq 'cloud') { 'Cyan' } else { 'Green' })
    Write-Host "║   Chat Provider:    $provider" -ForegroundColor White
    Write-Host "║   Fovea Level:      $fovea — $(Get-FoveaLabel -Level $fovea)" -ForegroundColor Magenta
    Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor DarkCyan
    Write-Host ""
}

function Show-Menu {
    Show-Status
    Write-Host "Choose route:" -ForegroundColor Yellow
    Write-Host "  [1] Local  — LM Studio (127.0.0.1:7272)" -ForegroundColor Green
    Write-Host "  [2] Cloud  — Ollama Cloud (ollama.com)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Foveation:" -ForegroundColor Yellow
    0..6 | ForEach-Object { Write-Host "  [f$_] $(Get-FoveaLabel -Level $_)" -ForegroundColor DarkGray }
    Write-Host "  [Q] Quit" -ForegroundColor DarkGray
    Write-Host ""
    $choice = Read-Host "Selection"
    switch ($choice.ToLower()) {
        "1"  { & $SetScript -Mode local }
        "2"  { & $SetScript -Mode cloud }
        { $_ -match "^f(\d)$" } { & $SetScript -FoveaLevel $matches[1] }
        "q"  { exit 0 }
        default { Write-Host "Invalid choice" -ForegroundColor Red }
    }
}

switch ($Action.ToLower()) {
    "local"  { & $SetScript -Mode local }
    "cloud"  { & $SetScript -Mode cloud }
    "status" { Show-Status }
    "menu"   { Show-Menu }
    "fovea"  {
        if ($PSBoundParameters.ContainsKey('FoveaLevel')) {
            & $SetScript -FoveaLevel $FoveaLevel
        } else {
            Show-Menu
        }
    }
}
