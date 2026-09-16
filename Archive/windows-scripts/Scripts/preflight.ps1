param(
    [string]$RootPath = "",
    [ValidateSet("light", "standard", "deep")]
    [string]$Level = "light",
    [switch]$AutoHeal = $true,
    [switch]$EmitJson
)

$ErrorActionPreference = "Stop"

function Add-Result([System.Collections.ArrayList]$Results, [string]$Name, [bool]$Ok, [string]$Detail, [bool]$Critical = $false, [bool]$Healed = $false) {
    [void]$Results.Add([PSCustomObject]@{
        Name     = $Name
        Ok       = $Ok
        Detail   = $Detail
        Critical = $Critical
        Healed   = $Healed
    })
}

function Test-Cmd([string]$CommandName) {
    return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

$ProjectRoot = if ($RootPath -and (Test-Path $RootPath)) { $RootPath } elseif ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path } else { (Get-Location).Path }
$GodotConsole = Join-Path $ProjectRoot "Godot_v4.6.2-stable_win64_console.exe"
$GodotEditor = Join-Path $ProjectRoot "Godot_v4.6.2-stable_win64.exe"
$GodotProject = Join-Path $ProjectRoot "Godot"
$MetaJson = "C:\Program Files\MetaXRSimulator\v85.0\meta_openxr_simulator.json"
$MetaExe = "C:\Program Files\MetaXRSimulator\v85.0\MetaXRSimulator.exe"
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$ReportPath = Join-Path $ProjectRoot "preflight_report.json"

$results = New-Object System.Collections.ArrayList

# Core checks
$pathsOk = (Test-Path $ProjectRoot) -and (Test-Path $GodotProject)
Add-Result $results "project_paths" $pathsOk "root=$ProjectRoot; godot=$GodotProject" $true

$godotOk = (Test-Path $GodotConsole) -or (Test-Path $GodotEditor)
Add-Result $results "godot_binary" $godotOk "console=$GodotConsole; editor=$GodotEditor" $true

$metaJsonOk = Test-Path $MetaJson
Add-Result $results "meta_runtime_json" $metaJsonOk "json=$MetaJson" $false

$metaProc = Get-Process -Name "MetaXRSimulator" -ErrorAction SilentlyContinue
$metaRunning = $null -ne $metaProc
if (-not $metaRunning -and $AutoHeal -and (Test-Path $MetaExe)) {
    Start-Process $MetaExe | Out-Null
    Start-Sleep -Seconds 3
    $metaProc = Get-Process -Name "MetaXRSimulator" -ErrorAction SilentlyContinue
    $metaRunning = $null -ne $metaProc
}
Add-Result $results "meta_simulator_process" $metaRunning "exe=$MetaExe" $false $metaRunning

if ($Level -ne "light") {
    $dockerCmdOk = Test-Cmd "docker"
    Add-Result $results "docker_compose_available" $dockerCmdOk "docker command available=$dockerCmdOk" $false

    if ($dockerCmdOk -and (Test-Path $ComposeFile)) {
        $composeRaw = ""
        try { $composeRaw = docker compose -f $ComposeFile ps --format json 2>$null } catch { $composeRaw = "" }
        $lines = @($composeRaw -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
        $running = 0
        foreach ($l in $lines) { if ($l -match '"State":"running"') { $running++ } }
        $svcOk = $running -gt 0

        if (-not $svcOk -and $AutoHeal) {
            try { docker compose -f $ComposeFile up -d | Out-Null } catch {}
            Start-Sleep -Seconds 2
            try { $composeRaw = docker compose -f $ComposeFile ps --format json 2>$null } catch { $composeRaw = "" }
            $lines = @($composeRaw -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
            $running = 0
            foreach ($l in $lines) { if ($l -match '"State":"running"') { $running++ } }
            $svcOk = $running -gt 0
        }
        Add-Result $results "docker_services_running" $svcOk "running=$running/$($lines.Count)" $false $svcOk
    } else {
        Add-Result $results "docker_services_running" $false "compose missing or docker unavailable" $false
    }
}

if ($Level -eq "deep") {
    $bridgeOk = $false
    $detail = "http://127.0.0.1:8000/health"
    try {
        $resp = Invoke-WebRequest -Uri $detail -TimeoutSec 2 -UseBasicParsing
        $bridgeOk = ($resp.StatusCode -eq 200)
    } catch {}
    if (-not $bridgeOk -and $AutoHeal -and (Test-Cmd "docker") -and (Test-Path $ComposeFile)) {
        try { docker compose -f $ComposeFile up -d | Out-Null } catch {}
        Start-Sleep -Seconds 2
        try {
            $resp = Invoke-WebRequest -Uri $detail -TimeoutSec 2 -UseBasicParsing
            $bridgeOk = ($resp.StatusCode -eq 200)
        } catch {}
    }
    Add-Result $results "soul_bridge_health" $bridgeOk $detail $true $bridgeOk
}

$criticalFail = @($results | Where-Object { $_.Critical -and -not $_.Ok })

$report = [PSCustomObject]@{
    Timestamp = (Get-Date).ToString("s")
    RootPath = $ProjectRoot
    Level = $Level
    AutoHeal = [bool]$AutoHeal
    CriticalFailures = $criticalFail.Count
    Results = $results
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding UTF8

Write-Host "=== PREFLIGHT ($Level) ===" -ForegroundColor Cyan
foreach ($r in $results) {
    $m = if ($r.Ok) { "✅" } else { "❌" }
    Write-Host ("{0} {1} :: {2}" -f $m, $r.Name, $r.Detail)
}
Write-Host "Report: $ReportPath"

if ($EmitJson) {
    Get-Content $ReportPath
}

if ($criticalFail.Count -gt 0) { exit 2 } else { exit 0 }

param(
    [ValidateSet("light", "standard", "deep")]
    [string]$Level = "light",
    [switch]$AutoHeal,
    [string]$ProjectRoot = "",
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

function New-Result([string]$Name, [bool]$Ok, [string]$Detail, [bool]$Critical = $true) {
    [PSCustomObject]@{
        name = $Name
        ok = $Ok
        critical = $Critical
        detail = $Detail
    }
}

function Invoke-QuickWebHealth([string]$Url, [int]$TimeoutSec = 3) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSec -UseBasicParsing
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-DockerPs([string]$ComposeFile) {
    try {
        $out = docker compose -f $ComposeFile ps --format json 2>$null
        if (-not $out) { return @{ ok = $false; detail = "docker compose unavailable or no services" } }
        $lines = $out -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 }
        if ($lines.Count -eq 0) { return @{ ok = $false; detail = "no services in compose output" } }
        $running = 0
        foreach ($line in $lines) {
            if ($line -match '"State":"running"') { $running++ }
        }
        return @{ ok = ($running -gt 0); detail = "running=$running/$($lines.Count)" }
    } catch {
        return @{ ok = $false; detail = "docker command error: $($_.Exception.Message)" }
    }
}

$root = if ($ProjectRoot -and (Test-Path $ProjectRoot)) { $ProjectRoot } elseif ($PSScriptRoot) { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) } else { (Get-Location).Path }
$godotProject = Join-Path $root "Godot"
$projectGodot = Join-Path $godotProject "project.godot"
$godotExeConsole = Join-Path $root "Godot_v4.6.2-stable_win64_console.exe"
$godotExeGui = Join-Path $root "Godot_v4.6.2-stable_win64.exe"
$composeFile = Join-Path $root "docker-compose.yml"
$metaJson = "C:\Program Files\MetaXRSimulator\v85.0\meta_openxr_simulator.json"
$metaExe = "C:\Program Files\MetaXRSimulator\v85.0\MetaXRSimulator.exe"

$results = @()

# Core checks (always)
$results += New-Result "project_paths" ((Test-Path $projectGodot)) ("project.godot=" + (Test-Path $projectGodot))
$hasGodotExe = (Test-Path $godotExeConsole) -or (Test-Path $godotExeGui)
$results += New-Result "godot_binary" $hasGodotExe ("console=" + (Test-Path $godotExeConsole) + " gui=" + (Test-Path $godotExeGui))
$results += New-Result "meta_runtime_json" (Test-Path $metaJson) $metaJson $false

# Level checks
$metaRunning = (Get-Process -Name "MetaXRSimulator" -ErrorAction SilentlyContinue) -ne $null
$results += New-Result "meta_simulator_process" $metaRunning ("running=" + $metaRunning) $false

if ($Level -in @("standard", "deep")) {
    $dockerExists = Test-Path $composeFile
    $results += New-Result "docker_compose_available" $dockerExists ("compose=" + $composeFile) $false
    if ($dockerExists) {
        $d = Test-DockerPs $composeFile
        $results += New-Result "docker_services_running" $d.ok $d.detail $false
    }
}

if ($Level -eq "deep") {
    $bridgeOk = Invoke-QuickWebHealth "http://127.0.0.1:8000/health" 3
    $results += New-Result "soul_bridge_health" $bridgeOk "http://127.0.0.1:8000/health" $false
}

# Auto-heal actions by level
if ($AutoHeal) {
    if (-not ($results | Where-Object { $_.name -eq "meta_simulator_process" }).ok) {
        if (Test-Path $metaExe) {
            Start-Process $metaExe | Out-Null
            Start-Sleep -Seconds 3
            $metaRunning = (Get-Process -Name "MetaXRSimulator" -ErrorAction SilentlyContinue) -ne $null
            $results += New-Result "heal_start_meta_simulator" $metaRunning "started MetaXRSimulator"
        } else {
            $results += New-Result "heal_start_meta_simulator" $false "MetaXRSimulator.exe missing" $false
        }
    }

    if ($Level -in @("standard", "deep")) {
        $dockerCheck = $results | Where-Object { $_.name -eq "docker_services_running" } | Select-Object -Last 1
        if ($dockerCheck -and -not $dockerCheck.ok -and (Test-Path $composeFile)) {
            try {
                docker compose -f $composeFile up -d | Out-Null
                Start-Sleep -Seconds 2
                $d = Test-DockerPs $composeFile
                $results += New-Result "heal_docker_compose_up" $d.ok $d.detail $false
            } catch {
                $results += New-Result "heal_docker_compose_up" $false $_.Exception.Message $false
            }
        }
    }

    if ($Level -eq "deep") {
        $bridgeCheck = $results | Where-Object { $_.name -eq "soul_bridge_health" } | Select-Object -Last 1
        if ($bridgeCheck -and -not $bridgeCheck.ok) {
            Start-Sleep -Seconds 2
            $retryOk = Invoke-QuickWebHealth "http://127.0.0.1:8000/health" 3
            $results += New-Result "heal_bridge_health_retry" $retryOk "retry /health after heal" $false
        }
    }
}

$criticalFailed = @($results | Where-Object { $_.critical -and -not $_.ok })
$ok = $criticalFailed.Count -eq 0

$summary = [PSCustomObject]@{
    timestamp = (Get-Date).ToString("s")
    root = $root
    level = $Level
    autoHeal = [bool]$AutoHeal
    ok = $ok
    criticalFailed = $criticalFailed
    results = $results
}

if (-not $ReportPath) {
    $ReportPath = Join-Path $root "preflight_report.json"
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding UTF8

Write-Host ("Preflight level=" + $Level + " ok=" + $ok + " report=" + $ReportPath)
foreach ($r in $results) {
    $mark = if ($r.ok) { "OK" } else { "FAIL" }
    Write-Host (" - [" + $mark + "] " + $r.name + " :: " + $r.detail)
}

if (-not $ok) { exit 2 }
exit 0

