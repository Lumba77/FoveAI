# Copy from C:\Users\lumba\Program\Lumax -> Lumax_current when source is newer OR dest missing.
# Skips vendor/cache dirs. Backs up existing .env before overwrite.
param(
    [string]$OldRoot = "C:\Users\lumba\Program\Lumax",
    [string]$NewRoot = "C:\Users\lumba\Program\Lumax_current",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $OldRoot)) { throw "Old root missing: $OldRoot" }
if (-not (Test-Path $NewRoot)) { throw "New root missing: $NewRoot" }

# Skip entire subtrees (huge or machine-local)
$skipDir = [regex]'\\(\.git|node_modules|\.godot|__pycache__|\.venv|build\\docker-buildkit-cache)(\\|$)'
$skipPathPart = @(
    '\scripts\llama.cpp\'
)

$copied = 0
$skipped = 0
$failed = 0
$scanned = 0
$log = New-Object System.Collections.Generic.List[string]
$errLog = New-Object System.Collections.Generic.List[string]

Get-ChildItem -LiteralPath $OldRoot -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $full = $_.FullName
    if ($skipDir.IsMatch($full)) { return }
    foreach ($p in $skipPathPart) {
        if ($full -like "*$p*") { return }
    }

    $script:scanned++
    $rel = $full.Substring($OldRoot.Length).TrimStart('\')
    $dest = Join-Path $NewRoot $rel
    $destDir = Split-Path -Parent $dest

    $srcTime = $_.LastWriteTimeUtc
    if (Test-Path -LiteralPath $dest) {
        $dt = (Get-Item -LiteralPath $dest).LastWriteTimeUtc
        if ($dt -ge $srcTime) {
            $script:skipped++
            return
        }
    }

    if ($WhatIf) {
        $log.Add("WHATIF: $rel")
        $script:copied++
        return
    }

    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    if ($rel -eq ".env" -and (Test-Path -LiteralPath $dest)) {
        $bak = "$dest.bak_before_sync_from_foveai"
        try {
            Copy-Item -LiteralPath $dest -Destination $bak -Force
            $log.Add("Backed up existing .env -> $(Split-Path $bak -Leaf)")
        } catch {
            $errLog.Add("ENV_BACKUP_FAIL: $rel :: $($_.Exception.Message)")
        }
    }

    try {
        Copy-Item -LiteralPath $full -Destination $dest -Force
        $log.Add("OK: $rel")
        $script:copied++
    } catch {
        $errLog.Add("FAIL: $rel :: $($_.Exception.Message)")
        $script:failed++
    }
}

Write-Host "--- sync_newer_from_foveai done ---" -ForegroundColor Cyan
Write-Host "Considered (files in old tree after skip rules): $scanned"
Write-Host "Copied/updated: $copied"
Write-Host "Skipped (dest already newer or same mtime): $skipped"
if ($failed -gt 0) { Write-Host "Failed (locked or other): $failed" -ForegroundColor Yellow }
if ($copied -eq 0 -and -not $WhatIf) {
    Write-Host ""
    Write-Host "No files copied — normal if you already ran this after editing Lumax_current." -ForegroundColor DarkYellow
    Write-Host "This script only copies when OLD is NEWER than current (or file missing here)." -ForegroundColor DarkYellow
    Write-Host "To pull from old again, edit/save files in Lumax first, or copy specific paths by hand." -ForegroundColor DarkYellow
}

$summaryPath = Join-Path $NewRoot "sync_from_foveai_summary.txt"
$summary = @(
    "sync_newer_from_foveai $(Get-Date -Format o)",
    "OldRoot=$OldRoot",
    "NewRoot=$NewRoot",
    "Scanned=$scanned Copied=$copied Skipped=$skipped Failed=$failed",
    ""
)
if ($log.Count -gt 0) { $summary += $log }
$summary | Set-Content -Path $summaryPath -Encoding utf8
Write-Host "Summary: $summaryPath"

if ($log.Count -gt 0 -and $copied -gt 0) {
    $logPath = Join-Path $NewRoot "sync_from_foveai_log.txt"
    $log | Set-Content -Path $logPath -Encoding utf8
    Write-Host "Detail log: $logPath ($($log.Count) lines)"
}
if ($errLog.Count -gt 0) {
    $ep = Join-Path $NewRoot "sync_from_foveai_errors.txt"
    $errLog | Set-Content -Path $ep -Encoding utf8
    Write-Host "Errors: $ep ($($errLog.Count) lines)" -ForegroundColor Yellow
}
