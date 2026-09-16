param(
    [Parameter(Mandatory = $true)]
    [string]$TaskPrompt,
    [string]$RootPath = "",
    [string]$LocalModel = "qwen2.5-coder:latest",
    [string]$GeminiInstructionsPath = "",
    [ValidateSet("advice", "apply")]
    [string]$Mode = "advice"
)

$ErrorActionPreference = "Continue"

function Test-Cmd([string]$CommandName) {
    return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Looks-LowConfidence([string]$Text) {
    if (-not $Text) { return $true }
    $bad = @(
        "i don't know",
        "not sure",
        "cannot determine",
        "insufficient context",
        "unable to"
    )
    foreach ($b in $bad) {
        if ($Text.ToLower().Contains($b)) { return $true }
    }
    return $false
}

$ProjectRoot = if ($RootPath -and (Test-Path $RootPath)) { $RootPath } elseif ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path } else { (Get-Location).Path }
$routerLog = Join-Path $ProjectRoot "agent_router_last.txt"
$usedProvider = "none"
$output = ""

$commonContext = @"
Project root: $ProjectRoot
Mode: $Mode
Methodology file: Methodology.md
Task: $TaskPrompt
"@

# 1) Local-first (Ollama coder)
if (Test-Cmd "ollama") {
    try {
        $usedProvider = "ollama:$LocalModel"
        $output = (ollama run $LocalModel "$commonContext" 2>&1 | Out-String).Trim()
    } catch {
        $output = ""
    }
}

# 2) Escalate to Gemini CLI when local is weak/empty
if ((-not $output) -or (Looks-LowConfidence $output)) {
    if (Test-Cmd "gemini") {
        $usedProvider = "gemini-cli"
        $gPrompt = $commonContext
        if ($GeminiInstructionsPath -and (Test-Path $GeminiInstructionsPath)) {
            $gPrompt += "`nUse instruction file: $GeminiInstructionsPath"
        }
        try {
            $output = (gemini -p "$gPrompt" 2>&1 | Out-String).Trim()
        } catch {
            if (-not $output) { $output = "Gemini CLI call failed." }
        }
    }
}

if (-not $output) {
    $output = "No provider response. Check ollama/gemini CLI availability."
}

$log = @()
$log += "Timestamp: $(Get-Date -Format s)"
$log += "Provider: $usedProvider"
$log += "Mode: $Mode"
$log += ""
$log += $output
$log | Set-Content -Path $routerLog -Encoding UTF8

Write-Host "Provider: $usedProvider" -ForegroundColor Cyan
Write-Host "Router log: $routerLog"
Write-Output $output

