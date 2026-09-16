param(
    [string]$OutboxDir = "",
    [int]$MaxCharsPerFile = 4000
)

$ErrorActionPreference = "Continue"

if (-not $OutboxDir) {
    $OutboxDir = Join-Path $PSScriptRoot "..\..\Backend\preflight\outbox"
}

if (-not (Test-Path $OutboxDir)) {
    Write-Output "Watchdog outbox not found: $OutboxDir"
    exit 0
}

function Read-Trimmed([string]$Path, [int]$MaxChars) {
    try {
        $txt = Get-Content -Path $Path -Raw -Encoding UTF8
        if (-not $txt) { return "" }
        if ($txt.Length -le $MaxChars) { return $txt }
        return $txt.Substring(0, $MaxChars) + "`n... (truncated)"
    } catch {
        return "Could not read: $Path"
    }
}

$files = @(
    "approval_request_latest.json",
    "improvement_suggestions_latest.json",
    "question_answer_latest.json",
    "architect_plan_latest.json",
    "container_watchdog_report_latest.json",
    "extended_test_probe_latest.json"
)

$parts = @()
$parts += "# Lumax Watchdog Brief"
$parts += "Timestamp: $(Get-Date -Format s)"
$parts += ""
$parts += "Use this brief first before asking expensive models."
$parts += "If uncertainty remains, escalate with targeted question only."
$parts += ""

foreach ($f in $files) {
    $p = Join-Path $OutboxDir $f
    if (Test-Path $p) {
        $parts += "## $f"
        $parts += (Read-Trimmed -Path $p -MaxChars $MaxCharsPerFile)
        $parts += ""
    }
}

$brief = ($parts -join "`n")
$dest = Join-Path $OutboxDir "watchdog_brief_latest.md"
$brief | Set-Content -Path $dest -Encoding UTF8

Write-Host "Brief generated: $dest" -ForegroundColor Cyan
Write-Output $brief

