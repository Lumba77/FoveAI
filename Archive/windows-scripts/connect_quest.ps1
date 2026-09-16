# connect_quest.ps1 — Writes Godot/foveai_network_config.json (PC LAN + Soul host for Quest / Godot).
#
# Default: same-LAN Wi‑Fi — Synapse uses your PC's IPv4 (not 127.0.0.1 on the headset). No adb required.
#   .\connect_quest.ps1
#   .\connect_quest.ps1 -QuestIp "192.168.1.42"
#   .\connect_quest.ps1 -QuestSubnetPrefix "192.168.1"
#
# USB + adb reverse — Soul/STT on device loopback forwarded to the PC (127.0.0.1 in Godot on Quest).
#   .\connect_quest.ps1 --adb
#   .\connect_quest.ps1 --adb -IP "192.168.1.42"

param(
    [switch]$adb, #  .\connect_quest.ps1 --adb  (PowerShell also accepts -adb)
    [string]$IP = "",
    [string]$QuestIp = "",
    [string]$QuestSubnetPrefix = ""
)

$ErrorActionPreference = "Stop"

function Get-LumaxPcLanIp {
    param(
        [string]$QuestHostIp = "",
        [string]$QuestSubnetPrefix = ""
    )

    $rows = @()
    foreach ($a in Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue) {
        $ip = $a.IPAddress
        if ($ip -eq "127.0.0.1") { continue }
        if ($ip.StartsWith("169.254.")) { continue }
        $alias = [string]$a.InterfaceAlias
        $isVirtual = $false
        if ($alias -match 'vEthernet|Hyper-V|WSL|Docker|Default Switch|VirtualBox|VMware') { $isVirtual = $true }
        $rows += [PSCustomObject]@{
            IP        = $ip
            Alias     = $alias
            IsVirtual = $isVirtual
        }
    }
    if (-not $rows -or $rows.Count -eq 0) { return $null }

    $preferredPrefix = ""
    if ($QuestHostIp -match '^(\d+\.\d+\.\d+)\.') {
        $preferredPrefix = $Matches[1]
    }
    elseif ($QuestSubnetPrefix -match '^(\d+\.\d+\.\d+)$') {
        $preferredPrefix = $QuestSubnetPrefix
    }

    if ($preferredPrefix) {
        foreach ($r in $rows | Where-Object { -not $_.IsVirtual }) {
            if ($r.IP.StartsWith($preferredPrefix + ".")) { return $r.IP }
        }
        foreach ($r in $rows) {
            if ($r.IP.StartsWith($preferredPrefix + ".")) { return $r.IP }
        }
    }

    foreach ($r in $rows | Where-Object { -not $_.IsVirtual }) {
        if ($r.IP -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)') { return $r.IP }
    }
    foreach ($r in $rows) {
        if ($r.IP -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)') { return $r.IP }
    }
    return $rows[0].IP
}

function Write-LumaxNetworkConfigLan {
    param(
        [Parameter(Mandatory = $true)][string]$GodotDir
    )

    $pcLan = Get-LumaxPcLanIp -QuestHostIp $QuestIp -QuestSubnetPrefix $QuestSubnetPrefix
    if (-not $pcLan) {
        throw "Could not determine PC LAN IP."
    }

    $qsp = $QuestSubnetPrefix
    if (-not $qsp -or $qsp.Trim().Length -eq 0) {
        if ($pcLan -match '^(\d+\.\d+\.\d+)\.\d+$') {
            $qsp = $Matches[1]
        }
        else {
            $qsp = ""
        }
    }

    if (-not (Test-Path $GodotDir)) {
        New-Item -ItemType Directory -Path $GodotDir -Force | Out-Null
    }

    $cfg = [ordered]@{
        version               = 1
        pc_lan_ip             = $pcLan
        quest_ip              = $QuestIp
        quest_subnet_prefix   = $qsp
        nat_peer_default      = $pcLan
        soul_host             = $pcLan
        adb_reverse           = $false
        use_adb_reverse       = $false
        updated_utc           = (Get-Date).ToUniversalTime().ToString("o")
    }

    $jsonPath = Join-Path $GodotDir "foveai_network_config.json"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($jsonPath, ($cfg | ConvertTo-Json -Depth 5), $utf8NoBom)

    Write-Host "Wrote LAN config: $jsonPath" -ForegroundColor Green
    Write-Host "pc_lan_ip=$pcLan  soul_host=$pcLan  adb_reverse=false" -ForegroundColor Gray
    if ($qsp) {
        Write-Host "quest_subnet_prefix=$qsp.x" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1) Quest and PC on the same Wi‑Fi; Docker publishing 8000/8001/… on the PC." -ForegroundColor Gray
    Write-Host "2) Re-export / restart the Godot app so Synapse loads this file." -ForegroundColor Gray
    Write-Host "3) Optional USB + reverse: .\connect_quest.ps1 --adb" -ForegroundColor Gray
}

function Write-LumaxNetworkConfigAdb {
    param(
        [Parameter(Mandatory = $true)][string]$QuestEndpoint,
        [Parameter(Mandatory = $true)][string]$GodotDir
    )

    $questHost = ""
    if ($QuestEndpoint -match '^(\d+\.\d+\.\d+\.\d+):\d+$') {
        $questHost = $Matches[1]
    }
    $pcLan = Get-LumaxPcLanIp -QuestHostIp $questHost -QuestSubnetPrefix $QuestSubnetPrefix
    if (-not $pcLan) { $pcLan = "" }

    if (-not (Test-Path $GodotDir)) {
        New-Item -ItemType Directory -Path $GodotDir -Force | Out-Null
    }

    $obj = [ordered]@{
        version          = 1
        pc_lan_ip        = $pcLan
        quest_ip         = $questHost
        quest_subnet_prefix = $QuestSubnetPrefix
        nat_peer_default = $pcLan
        soul_host        = "127.0.0.1"
        adb_reverse      = $true
        use_adb_reverse  = $true
        updated_utc      = (Get-Date).ToUniversalTime().ToString("o")
    }
    $jsonPath = Join-Path $GodotDir "foveai_network_config.json"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($jsonPath, ($obj | ConvertTo-Json -Depth 5), $utf8NoBom)
    Write-Host "Wrote NAT / bridge config: $jsonPath (pc_lan_ip=$pcLan, quest_ip=$questHost, soul_host=127.0.0.1 adb reverse)" -ForegroundColor DarkCyan
}

# --- Default: LAN (no adb) ---
if (-not $adb) {
    Write-Host "--- Lumax connect_quest (LAN default) ---" -ForegroundColor Cyan
    $godotDir = Join-Path $PSScriptRoot "Godot"
    Write-LumaxNetworkConfigLan -GodotDir $godotDir
    exit 0
}

# --- --adb: USB / Wi‑Fi ADB + port reverse ---
Write-Host "--- Lumax connect_quest (--adb: reverse to PC) ---" -ForegroundColor Cyan

$godotDir = Join-Path $PSScriptRoot "Godot"

$devices = adb devices | Select-String -Pattern "\tdevice$"
if ($null -eq $devices) {
    Write-Host "No adb devices. Connect Quest via USB or Wi‑Fi adb, or use LAN mode without --adb: .\connect_quest.ps1" -ForegroundColor Red
    exit 1
}

$targetDevice = ""
if ($IP -ne "") {
    $targetDevice = "$IP:5555"
}
else {
    if ($devices -match "(\d+\.\d+\.\d+\.\d+:5555)") {
        $targetDevice = $matches[1]
        Write-Host "Found existing Wi‑Fi connection: $targetDevice" -ForegroundColor Green
    }
    else {
        Write-Host "No Wi‑Fi adb target. Scanning USB Quest…" -ForegroundColor Yellow
        adb tcpip 5555
        Start-Sleep -Seconds 2

        $ip_info = adb shell "ip addr show wlan0"
        if ($ip_info -match "inet (\d+\.\d+\.\d+\.\d+)") {
            $IP = $matches[1]
            $targetDevice = "$IP:5555"
            Write-Host "Detected Quest IP: $IP" -ForegroundColor Green
            adb connect $targetDevice
        }
        else {
            Write-Host "Could not detect Quest IP. Pass it: .\connect_quest.ps1 --adb -IP 192.168.x.x" -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host "`nEnsuring connection to $targetDevice..." -ForegroundColor Yellow
$null = adb connect $targetDevice
adb devices

Write-LumaxNetworkConfigAdb -QuestEndpoint $targetDevice -GodotDir $godotDir

Write-Host "`nSetting up port reverse (Quest -> PC)..." -ForegroundColor Yellow
adb -s $targetDevice reverse --remove-all
adb -s $targetDevice reverse tcp:8000 tcp:8000
adb -s $targetDevice reverse tcp:8001 tcp:8001
adb -s $targetDevice reverse tcp:8002 tcp:8002
adb -s $targetDevice reverse tcp:8003 tcp:8003
adb -s $targetDevice reverse tcp:8004 tcp:8004
adb -s $targetDevice reverse tcp:8005 tcp:8005
adb -s $targetDevice reverse tcp:8006 tcp:8006
adb -s $targetDevice reverse tcp:8020 tcp:8020
adb -s $targetDevice reverse tcp:8080 tcp:8080
adb -s $targetDevice reverse tcp:6006 tcp:6006
adb -s $targetDevice reverse tcp:6007 tcp:6007

Write-Host "`nDone: config written, ports reversed. Godot on Quest uses 127.0.0.1 for Docker via adb." -ForegroundColor Green
