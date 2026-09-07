param(
    [string]$RootPath = "",
    [string]$ProjectPath = "",
    [string]$GodotExe = "",
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Get-Sha256Map([string]$Root, [string[]]$RelPaths) {
    $m = @{}
    foreach ($rp in $RelPaths) {
        $full = Join-Path $Root $rp
        if (Test-Path $full) {
            try {
                $h = Get-FileHash -Path $full -Algorithm SHA256
                $m[$rp] = $h.Hash
            } catch {
                $m[$rp] = "ERROR:$($_.Exception.Message)"
            }
        } else {
            $m[$rp] = "MISSING"
        }
    }
    return $m
}

$root = if ($RootPath -and (Test-Path $RootPath)) { $RootPath } else { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$proj = if ($ProjectPath -and (Test-Path $ProjectPath)) { $ProjectPath } else { Join-Path $root "Godot" }
$godot = if ($GodotExe -and (Test-Path $GodotExe)) { $GodotExe } else { Join-Path $root "Godot_v4.6.2-stable_win64_console.exe" }
if (-not (Test-Path $godot)) { $godot = Join-Path $root "Godot_v4.6.2-stable_win64.exe" }

if (-not (Test-Path (Join-Path $proj "project.godot"))) {
    throw "Guardian sync: Godot project not found at $proj"
}
if (-not (Test-Path $godot)) {
    throw "Guardian sync: Godot executable not found."
}

$guardFiles = @(
    "Godot/Nexus/SkeletonKey.gd",
    "Godot/scripts/avatar_controller.gd",
    "Godot/addons/godot-xr-tools/functions/function_pointer.gd",
    "Godot/addons/godot-xr-tools/functions/function_pointer.tscn",
    "Godot/Nexus/Lumax_Core.tscn",
    "Godot/Senses/AuralAwareness.gd",
    "Godot/Senses/MultiVisionHandler.gd"
)

$before = Get-Sha256Map -Root $root -RelPaths $guardFiles

Write-Host "Guardian sync: headless cache refresh..." -ForegroundColor Cyan
$sync = Start-Process $godot -ArgumentList "--path `"$proj`" --editor --quit --headless" -PassThru -Wait
if ($sync.ExitCode -ne 0) {
    throw "Guardian sync: headless editor pass failed (exit=$($sync.ExitCode))."
}

$after = Get-Sha256Map -Root $root -RelPaths $guardFiles
$changed = @()
foreach ($k in $before.Keys) {
    if ($before[$k] -ne $after[$k]) {
        $changed += $k
    }
}

$reportDir = Join-Path $root "build\guardian"
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$reportPath = Join-Path $reportDir "guardian_sync_report.json"
$report = [PSCustomObject]@{
    timestamp = (Get-Date).ToString("s")
    project = $proj
    godot_exe = $godot
    changed_guard_files = $changed
    before = $before
    after = $after
}
$report | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding UTF8

if ($changed.Count -gt 0) {
    Write-Host ("Guardian: file drift detected after cache refresh: " + ($changed -join ", ")) -ForegroundColor Yellow
    if ($Strict) {
        throw ("Guardian strict mode: drift detected in " + ($changed -join ", "))
    }
} else {
    Write-Host "Guardian: source files stable; cache refreshed." -ForegroundColor Green
}
Write-Host "Report: $reportPath"
