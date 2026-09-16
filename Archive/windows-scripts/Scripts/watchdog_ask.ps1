param(
    [Parameter(Mandatory = $true)]
    [string]$Question,
    [string]$InboxDir = "",
    [string]$OutboxDir = "",
    [int]$TimeoutSec = 45
)

$ErrorActionPreference = "Continue"

if (-not $InboxDir) {
    $InboxDir = Join-Path $PSScriptRoot "..\..\Backend\preflight\inbox"
}
if (-not $OutboxDir) {
    $OutboxDir = Join-Path $PSScriptRoot "..\..\Backend\preflight\outbox"
}

New-Item -ItemType Directory -Force -Path $InboxDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutboxDir | Out-Null

$questionPath = Join-Path $InboxDir "question_latest.json"
$answerPath = Join-Path $OutboxDir "question_answer_latest.json"

$beforeWrite = if (Test-Path $answerPath) { (Get-Item $answerPath).LastWriteTimeUtc } else { [datetime]::MinValue }

$payload = @{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    question      = $Question
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $questionPath -Encoding UTF8

Write-Host "Question submitted to watchdog inbox." -ForegroundColor Cyan
Write-Host "Waiting up to $TimeoutSec sec for answer..."

$start = Get-Date
while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSec) {
    if (Test-Path $answerPath) {
        $afterWrite = (Get-Item $answerPath).LastWriteTimeUtc
        if ($afterWrite -gt $beforeWrite) {
            $ans = Get-Content -Path $answerPath -Raw -Encoding UTF8
            Write-Output $ans
            exit 0
        }
    }
    Start-Sleep -Seconds 2
}

Write-Output (@{
    status = "timeout"
    note = "No fresh answer observed in outbox within timeout."
    answer_path = $answerPath
} | ConvertTo-Json -Depth 5)

