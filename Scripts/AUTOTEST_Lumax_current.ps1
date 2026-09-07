# Sentinel loop for the transplant receiver tree (Lumax_current).
# Same flow as Lumax/AUTOTEST.ps1: Guardian headless cache refresh + drift check, then XR run + logs.
# Godot binary: uses Lumax_current if present, else falls back to sibling ..\Lumax (typical install).

param(
    [switch]$KillAllGodot
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$GodotProject = Join-Path $Root "Godot"
$DEBUG_LOG = Join-Path $Root "godot_debug_output.txt"
$ERROR_LOG = Join-Path $Root "godot_error_output.txt"
$GuardianSync = Join-Path $Root "scripts\automation\godot_guardian_sync.ps1"

$GodotExe = Join-Path $Root "Godot_v4.6.2-stable_win64_console.exe"
if (-not (Test-Path $GodotExe)) { $GodotExe = Join-Path $Root "Godot_v4.6.2-stable_win64.exe" }
if (-not (Test-Path $GodotExe)) {
    $siblingLumax = Join-Path (Split-Path $Root -Parent) "Lumax"
    $GodotExe = Join-Path $siblingLumax "Godot_v4.6.2-stable_win64_console.exe"
    if (-not (Test-Path $GodotExe)) { $GodotExe = Join-Path $siblingLumax "Godot_v4.6.2-stable_win64.exe" }
}

Write-Host "Lumax_current sentinel: root=$Root" -ForegroundColor Cyan

$xrJson = "C:\Program Files\MetaXRSimulator\v85.0\meta_openxr_simulator.json"
if (Test-Path $xrJson) {
    $env:XR_RUNTIME_JSON = $xrJson
} else {
    Write-Host "Meta XR Simulator JSON not found; XR may fall back: $xrJson" -ForegroundColor Yellow
    Remove-Item Env:XR_RUNTIME_JSON -ErrorAction SilentlyContinue
}

# 1. Guardian: refresh .godot import cache; fail in Strict if Godot rewrites guarded sources
Write-Host "Guardian sync (Lumax_current)..." -ForegroundColor Yellow
if (Test-Path $GuardianSync) {
    & $GuardianSync -RootPath $Root -ProjectPath $GodotProject -GodotExe $GodotExe -Strict
} else {
    Write-Host "Guardian script missing; headless sync only." -ForegroundColor Yellow
    if (-not (Test-Path $GodotExe)) { throw "Godot executable not found." }
    Start-Process $GodotExe -ArgumentList "--path `"$GodotProject`" --editor --quit --headless" -Wait
}

if (Test-Path $DEBUG_LOG) { Remove-Item $DEBUG_LOG }
if (Test-Path $ERROR_LOG) { Remove-Item $ERROR_LOG }
Write-Host "Launching Godot XR (project under Lumax_current)..." -ForegroundColor Green
$proc = Start-Process $GodotExe -ArgumentList "--path `"$GodotProject`" --xr-mode on" -PassThru -NoNewWindow -RedirectStandardOutput $DEBUG_LOG -RedirectStandardError $ERROR_LOG

$manifested = $false
$xrReadyPattern = "XR started|OpenXR Initialized SUCCESS"
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Path $DEBUG_LOG) {
        $content = Get-Content $DEBUG_LOG -Raw
        if ($content -match $xrReadyPattern) {
            Start-Sleep -Seconds 2
            $manifested = $true
            break
        }
    }
    Start-Sleep -Seconds 1
}

if ($manifested) {
    Write-Host "XR ready; waiting 15s before screen capture..." -ForegroundColor Cyan
    Start-Sleep -Seconds 15
    $shotDir = Join-Path $Root "div\image"
    if (-not (Test-Path $shotDir)) { New-Item -ItemType Directory -Path $shotDir -Force | Out-Null }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $Screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $Bitmap = New-Object System.Drawing.Bitmap $Screen.Width, $Screen.Height
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    $Graphics.CopyFromScreen($Screen.X, $Screen.Y, 0, 0, $Bitmap.Size)
    $Bitmap.Save((Join-Path $shotDir "auto_test_vision_foveai_current.png"), [System.Drawing.Imaging.ImageFormat]::Png)
} else {
    Write-Host "XR readiness timed out." -ForegroundColor Red
}

Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
if ($KillAllGodot) {
    Get-Process -Name "Godot*" -ErrorAction SilentlyContinue | Stop-Process -Force
}

Write-Host "--- DEBUG (tail) ---" -ForegroundColor Yellow
if (Test-Path $DEBUG_LOG) { Get-Content $DEBUG_LOG -Tail 30 }
Write-Host "--- ERROR (tail) ---" -ForegroundColor Red
if (Test-Path $ERROR_LOG) { Get-Content $ERROR_LOG -Tail 30 }
