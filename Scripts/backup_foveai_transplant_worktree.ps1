# Backs up the transplant working tree before risky grafts (6-step UI/avatar protocol).
# Default: C:\Users\lumba\Program\Lumax_current -> Lumax_current_backup_YYYYMMDD_HHMMSS
#
# Usage (from anywhere):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lumba\Program\Lumax\scripts\backup_foveai_transplant_worktree.ps1"
# Optional:
#   -Parent "D:\Work" -Source "Lumax_current"
#   -ExcludeGit    # faster, smaller — backup is not a full git clone for rollback

param(
    [string] $Parent = "C:\Users\lumba\Program",
    [string] $Source = "Lumax_current",
    [switch] $ExcludeGit
)

$ErrorActionPreference = "Stop"
$src = Join-Path $Parent $Source
if (-not (Test-Path -LiteralPath $src)) {
    Write-Error "Source folder does not exist: $src"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$destName = "${Source}_backup_$stamp"
$dst = Join-Path $Parent $destName

Write-Host "Backing up:`n  FROM $src`n  TO   $dst"

if (Test-Path -LiteralPath $dst) {
    Write-Error "Destination already exists: $dst"
}

$robolog = Join-Path $env:TEMP "robocopy_foveai_backup_$stamp.log"
$args = @(
    $src, $dst,
    "/E", "/COPY:DAT", "/DCOPY:DAT",
    "/R:2", "/W:2",
    "/LOG:$robolog", "/TEE"
)
if ($ExcludeGit) {
    $args += "/XD", (Join-Path $src ".git")
}

$proc = Start-Process -FilePath "robocopy.exe" -ArgumentList $args -Wait -PassThru -NoNewWindow
# robocopy: 0-7 = success semantics; >=8 = failure
if ($proc.ExitCode -ge 8) {
    Write-Error "robocopy failed with exit $($proc.ExitCode). See $robolog"
}

Write-Host "OK: backup complete at $dst"
Write-Host "Log: $robolog"
