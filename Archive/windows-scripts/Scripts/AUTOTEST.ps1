# 🤖 JEN SENTINEL LOOP (v2.0)
# Headless import + XR run; logs to godot_*_output.txt. Optional screen capture if "XR started" appears.

param(
    [switch]$KillAllGodot
)

Write-Host "🤖 Initiating Optimized Sentinel Loop..." -ForegroundColor Cyan

$xrJson = "C:\Program Files\MetaXRSimulator\v85.0\meta_openxr_simulator.json"
if (Test-Path $xrJson) {
    $env:XR_RUNTIME_JSON = $xrJson
} else {
    Write-Host "⚠️ Meta XR Simulator JSON not found; XR mode may fall back or fail: $xrJson" -ForegroundColor Yellow
    Remove-Item Env:XR_RUNTIME_JSON -ErrorAction SilentlyContinue
}
# Define Paths
$GodotExe = "C:\Users\lumba\Program\Lumax\Godot_v4.6.2-stable_win64_console.exe"
$GodotProject = "C:\Users\lumba\Program\Lumax\Godot"
$DEBUG_LOG = "C:\Users\lumba\Program\Lumax\godot_debug_output.txt"
$ERROR_LOG = "C:\Users\lumba\Program\Lumax\godot_error_output.txt"
$GuardianSync = "C:\Users\lumba\Program\Lumax\scripts\automation\godot_guardian_sync.ps1"

# 1. Guardian Sync (authoritative source + cache refresh, no full cache purge)
Write-Host "🧠 Guardian Sync..." -ForegroundColor Yellow
if (Test-Path $GuardianSync) {
    & $GuardianSync -RootPath "C:\Users\lumba\Program\Lumax" -ProjectPath $GodotProject -GodotExe $GodotExe -Strict
} else {
    Write-Host "⚠️ Guardian script missing; falling back to headless sync." -ForegroundColor Yellow
    $syncProc = Start-Process $GodotExe -ArgumentList "--path `"$GodotProject`" --editor --quit --headless" -PassThru -Wait
}

# 2. Launch Manifest
if (Test-Path $DEBUG_LOG) { Remove-Item $DEBUG_LOG }
if (Test-Path $ERROR_LOG) { Remove-Item $ERROR_LOG }
Write-Host "🚀 Waking her up with Meta Simulator SDK..." -ForegroundColor Green
$proc = Start-Process $GodotExe -ArgumentList "--path `"$GodotProject`" --xr-mode on" -PassThru -NoNewWindow -RedirectStandardOutput $DEBUG_LOG -RedirectStandardError $ERROR_LOG

# 3. Dynamic Vision Capture (Godot XR Tools prints "XR started"; Lumax/SkeletonKey prints OpenXR SUCCESS)
Write-Host "⏳ Watching for manifestation trigger..." -ForegroundColor Gray
$manifested = $false
$xrReadyPattern = "XR started|OpenXR Initialized SUCCESS"
for ($i=0; $i -lt 30; $i++) {
    if (Test-Path $DEBUG_LOG) {
        $content = Get-Content $DEBUG_LOG -Raw
        if ($content -match $xrReadyPattern) {
            Start-Sleep -Seconds 2 # Short buffer for rendering
            $manifested = $true
            break
        }
    }
    Start-Sleep -Seconds 1
}

if ($manifested) {
    Write-Host "📸 Trigger Received. Waiting 15s for filming..." -ForegroundColor Cyan
    Start-Sleep -Seconds 15
    Write-Host "📸 Capturing Vision..." -ForegroundColor Green
    $shotDir = "c:\Users\lumba\Program\Lumax\div\image"
    if (-not (Test-Path $shotDir)) { New-Item -ItemType Directory -Path $shotDir -Force | Out-Null }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $Screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $Bitmap = New-Object System.Drawing.Bitmap $Screen.Width, $Screen.Height
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    $Graphics.CopyFromScreen($Screen.X, $Screen.Y, 0, 0, $Bitmap.Size)
    $Bitmap.Save("$shotDir\auto_test_vision.png", [System.Drawing.Imaging.ImageFormat]::Png)
} else {
    Write-Host "⚠️ Manifestation timed out." -ForegroundColor Red
}

# 4. Purge (only the spawned XR process by default; use -KillAllGodot to nuke every Godot_*)
Write-Host "🛑 Purging manifestation..." -ForegroundColor Red
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
if ($KillAllGodot) {
    Get-Process -Name "Godot*" -ErrorAction SilentlyContinue | Stop-Process -Force
}

Write-Host "📜 Final Mind Pass (DEBUG):" -ForegroundColor Yellow
if (Test-Path $DEBUG_LOG) { Get-Content $DEBUG_LOG -Tail 30 }
Write-Host "📜 Final Mind Pass (ERROR):" -ForegroundColor Red
if (Test-Path $ERROR_LOG) { Get-Content $ERROR_LOG -Tail 30 }
