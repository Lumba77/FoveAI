# push_all.ps1 - Ultimate Sync for Lumax (v2.6)
# Syncs everything under Godot/ to Quest except .godot (editor cache — never upload).
# Per-folder .import sidecars are included so the headset can resolve UIDs without a local import.

param (
    [string]$Target = "godot",
    [string]$QuestRoot = "/sdcard/Projects/Lumax-Vulkan"
)

$ErrorActionPreference = "Stop"

# Auto-detect the Quest ID
Write-Host "🔍 Searching for Quest..." -ForegroundColor Gray
$adbDevices = adb devices | Select-String -Pattern "\tdevice$"
if ($adbDevices.Count -eq 0) {
    Write-Host "❌ Error: Quest not found! Reconnect USB or WiFi." -ForegroundColor Red
    exit 1
}
$DEVICE_ID = $adbDevices[0].ToString().Split("`t")[0].Trim()
Write-Host "🎯 Target Device: $DEVICE_ID" -ForegroundColor Cyan

# Repo root = folder containing this script (Lumax_current, Lumax, etc.)
$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$SourceGodot = Join-Path $RepoRoot "Godot"

# Never push these names (PC-only / huge / breaks on device). .import files beside assets ARE pushed.
$NeverPush = @(
    ".godot"
)

# 1. RESET THE AI BRIDGE (Quest -> PC)
Write-Host "🔄 Resetting AI Communication Ports (STT/TTS/WEB)..." -ForegroundColor Yellow
adb -s $DEVICE_ID reverse --remove-all
adb -s $DEVICE_ID reverse tcp:8000 tcp:8000 # Soul
adb -s $DEVICE_ID reverse tcp:8001 tcp:8001 # Ears
adb -s $DEVICE_ID reverse tcp:8002 tcp:8002 # Mouth
adb -s $DEVICE_ID reverse tcp:8003 tcp:8003 # Creativity /dream
adb -s $DEVICE_ID reverse tcp:8004 tcp:8004 # Chatterbox TTS UI
adb -s $DEVICE_ID reverse tcp:8005 tcp:8005 # Turbo TTS
adb -s $DEVICE_ID reverse tcp:8006 tcp:8006 # Sentry
adb -s $DEVICE_ID reverse tcp:8020 tcp:8020 # Optional legacy XTTS (not foveai_turbochat)
adb -s $DEVICE_ID reverse tcp:8080 tcp:8080 # Web Bridge
adb -s $DEVICE_ID reverse tcp:6006 tcp:6006 # Console
adb -s $DEVICE_ID reverse tcp:6007 tcp:6007 # Logs

# 2. PERFORM SYNC
function Push-Safe {
    param($src, $dest)
    Write-Host "📂 Scanning: $src" -ForegroundColor Cyan

    # Drop stale editor cache on Quest if an old sync ever created it
    adb -s $DEVICE_ID shell "rm -rf `"$dest/.godot`"" 2>$null

    $items = Get-ChildItem -Path $src -Force
    foreach ($item in $items) {
        if ($NeverPush -contains $item.Name) {
            Write-Host "⏭️  Skip (not for Quest): $($item.Name)" -ForegroundColor DarkGray
            continue
        }

        Write-Host "📤 Syncing: $($item.Name)" -ForegroundColor Gray
        $targetPath = $dest + "/" + $item.Name
        
        # NUCLEAR SAFE: Wipe the target on Quest first to prevent nesting (addons/addons)
        adb -s $DEVICE_ID shell "rm -rf $targetPath"
        adb -s $DEVICE_ID push $item.FullName $dest
    }
}

# The Target "godot" now performs a CLEAN, FAST overwrite of the code + root project.
if ($Target -eq "godot") {
    Write-Host "🚀 Running Core Logic Sync..." -ForegroundColor Green
    Push-Safe $SourceGodot $QuestRoot
} elseif ($Target -eq "clean") {
    Write-Host "🧹 TOTAL REFRESH: Purging and Re-uploading entire project to Quest..." -ForegroundColor Red
    # 1. Nuking everything on the Quest for this project
    adb -s $DEVICE_ID shell "rm -rf $QuestRoot"
    adb -s $DEVICE_ID shell "mkdir -p $QuestRoot"
    
    # 2. Re-creating the directory and performing a full sync
    Push-Safe $SourceGodot $QuestRoot
}

Write-Host "`n✅ Full Ready! Target: $Target" -ForegroundColor Green
Write-Host "Project is located at: $QuestRoot" -ForegroundColor Gray
