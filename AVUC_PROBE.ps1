# FoveAI AVUC (AI Verification / User Certification) PROBE
# Purpose: Empirically verify project state on Quest before User Certification.

$QUEST_IP = "100.64.150.192"
$TARGET_DIR = "/sdcard/Projects/Lumax-Vulkan/Godot/"
# Local Godot tree: repo root = this script's directory
$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$LocalGodotRoot = Join-Path $RepoRoot "Godot"

function Get-QuestFileHash($filePath) {
    $output = adb shell md5sum "$TARGET_DIR$filePath"
    if ($output -match "^([a-f0-9]+)") { return $matches[1] }
    return $null
}

function Get-LocalFileHash($filePath) {
    $hash = Get-FileHash -Path (Join-Path $LocalGodotRoot $filePath) -Algorithm MD5
    return $hash.Hash.ToLower()
}

Write-Host "`n--- AVUC PROBE: STARTING INTEGRITY CHECK ---" -ForegroundColor Cyan

# 1. HASH VERIFICATION (DISK SYNC)
$files = @("Mind/Lumax_Display.tscn", "Mind/WebUI.gd", "Mind/TactileInput_v2.gd", "Nexus/SkeletonKey.gd", "scripts/avatar_controller.gd")
foreach ($f in $files) {
    $local = Get-LocalFileHash $f
    $remote = Get-QuestFileHash $f
    if ($local -eq $remote) {
        Write-Host "[PASS] Sync Verified: $f" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Sync Mismatch: $f (Local: $local vs Remote: $remote)" -ForegroundColor Red
    }
}

# 2. VIEWPORT SIZE VERIFICATION
$displayContent = adb shell "cat ${TARGET_DIR}Mind/Lumax_Display.tscn"
if ($displayContent -match "viewport_size = Vector2\(1000, 500\)") {
    Write-Host "[PASS] Viewport Size: 500px (Slim)" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Viewport Size: OLD/UNSUPPORTED" -ForegroundColor Red
}

# 3. LOG AUDIT (RUNTIME STATUS)
Write-Host "`n--- AVUC PROBE: LOG AUDIT ---" -ForegroundColor Cyan
$logs = adb logcat -d | Select-String "FoveAI" | Select-Object -Last 5
if ($logs) {
    $logs | ForEach-Object { Write-Host "  LOG: $_" -ForegroundColor Gray }
} else {
    Write-Host "  NOTICE: No recent FoveAI logs found." -ForegroundColor Yellow
}

Write-Host "`n--- AVUC PROBE: COMPLETE ---" -ForegroundColor Cyan
