[CmdletBinding(PositionalBinding = $false)]
param(
    [int]$TimeoutSec = 45,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Words
)

$ErrorActionPreference = "Continue"

if (-not $Words -or $Words.Count -eq 0) {
    Write-Output "Usage: q <question text>"
    exit 0
}

$question = ($Words -join " ").Trim()
$askScript = Join-Path $PSScriptRoot "watchdog_ask.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -File $askScript -Question $question -TimeoutSec $TimeoutSec

