e# LUMAX System Tray Widget
# Runs in user session (not as service). Shows status, toggle ON/OFF.
# Reads:  .logs\lumax_service_status.json
# Writes: .logs\lumax_service_cmd.txt
# 
param(
    [string]$ConfigPath = $null
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$LUMAX_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ConfigPath) { $ConfigPath = Join-Path $LUMAX_ROOT "Service\lumax_service_config.json" }

$StatusFile = Join-Path $LUMAX_ROOT ".logs\lumax_service_status.json"
$CommandFile = Join-Path $LUMAX_ROOT ".logs\lumax_service_cmd.txt"
$SvcLog = Join-Path $LUMAX_ROOT ".logs\lumax_service.log"
$TrayLog = Join-Path $LUMAX_ROOT ".logs\lumax_tray.log"

# --- Logging function ---
function Write-TrayLog {
    param($Level, $Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    try { Add-Content -Path $TrayLog -Value $line -ErrorAction SilentlyContinue } catch {}
}


$Config = @{ AvatarName = "Jen" }
if (Test-Path $ConfigPath) {
    try { $fileCfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json; foreach ($prop in $fileCfg.PSObject.Properties) { $Config[$prop.Name] = $prop.Value } } catch {}
}

# --- Icon creation (simple colored dot) ---
# GDI+ safe: create once, cache, reuse. Never call GetHicon() in a loop.
$script:_iconCache = @{}

function New-StatusIcon {
    param([string]$Key, [int]$R, [int]$G, [int]$B)
    $size = 16
    $bmp = New-Object System.Drawing.Bitmap $size, $size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    $gfx.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $gfx.Clear([System.Drawing.Color]::Transparent)
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, $R, $G, $B))
    $gfx.FillEllipse($brush, 1, 1, $size - 3, $size - 3)
    $brush.Dispose()
    $gfx.Dispose()
    $hIcon = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($hIcon)
    $bmp.Dispose()
    $script:_iconCache[$Key] = $icon
    return $icon
}

# Pre-create all three icons at startup to avoid timer-loop leaks
$null = New-StatusIcon "off"   180 50  50   # red
$null = New-StatusIcon "on"    50  220 100  # green
$null = New-StatusIcon "sleep" 200 150 50   # amber

function Get-CachedIcon {
    param([string]$Key)
    if ($script:_iconCache.ContainsKey($Key)) { return $script:_iconCache[$Key] }
    return $script:_iconCache["off"]
}

# --- Tray UI ---
$form = New-Object System.Windows.Forms.Form
$form.WindowState = "Minimized"
$form.ShowInTaskbar = $false
$form.FormBorderStyle = "None"
$form.Size = New-Object System.Drawing.Size(1, 1)

$trayIcon = New-Object System.Windows.Forms.NotifyIcon
$trayIcon.Visible = $true
$trayIcon.Text = "LUMAX Service"
$trayIcon.Icon = (Get-CachedIcon "off")
$trayIcon.BalloonTipTitle = "LUMAX"

$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip

$statusItem = New-Object System.Windows.Forms.ToolStripMenuItem
$statusItem.Text = "LUMAX: $($Config.AvatarName) * Matchbox Sovereign"
$statusItem.Enabled = $false
[void]$contextMenu.Items.Add($statusItem)

[void]$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$startMatchboxItem = New-Object System.Windows.Forms.ToolStripMenuItem
$startMatchboxItem.Text = "Launch Matchbox (WebXR)"
$startMatchboxItem.ForeColor = [System.Drawing.Color]::DeepSkyBlue
[void]$contextMenu.Items.Add($startMatchboxItem)

$toggleItem = New-Object System.Windows.Forms.ToolStripMenuItem
$toggleItem.Text = "Turn ON Services"
$toggleItem.ForeColor = [System.Drawing.Color]::Green
[void]$contextMenu.Items.Add($toggleItem)

$wakeItem = New-Object System.Windows.Forms.ToolStripMenuItem
$wakeItem.Text = "Wake"
$wakeItem.Visible = $false
[void]$contextMenu.Items.Add($wakeItem)

[void]$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$openConsoleItem = New-Object System.Windows.Forms.ToolStripMenuItem
$openConsoleItem.Text = "Open Console..."
[void]$contextMenu.Items.Add($openConsoleItem)

$openLogsItem = New-Object System.Windows.Forms.ToolStripMenuItem
$openLogsItem.Text = "Open Logs"
[void]$contextMenu.Items.Add($openLogsItem)

[void]$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

# Consent submenu
$consentMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$consentMenu.Text = "Connect Data..."
$googleConnectItem = New-Object System.Windows.Forms.ToolStripMenuItem
$googleConnectItem.Text = "Google (contacts, calendar)"
$microsoftConnectItem = New-Object System.Windows.Forms.ToolStripMenuItem
$microsoftConnectItem.Text = "Microsoft (contacts, calendar)"
$consentMenu.DropDownItems.Add($googleConnectItem)
$consentMenu.DropDownItems.Add($microsoftConnectItem)
[void]$contextMenu.Items.Add($consentMenu)

[void]$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$quitItem = New-Object System.Windows.Forms.ToolStripMenuItem
$quitItem.Text = "Quit Tray"
[void]$contextMenu.Items.Add($quitItem)

$trayIcon.ContextMenuStrip = $contextMenu

# --- Actions ---
function Send-Command {
    param([string]$Cmd)
    $Cmd | Out-File -FilePath $CommandFile -Encoding utf8 -Force -ErrorAction SilentlyContinue
}

$toggleItem.Add_Click({
    if ($script:LastEnabled) {
        Send-Command "DISABLE"
        $toggleItem.Text = "Turn ON"
        $toggleItem.ForeColor = [System.Drawing.Color]::Green
    } else {
        Send-Command "ENABLE"
        $toggleItem.Text = "Turn OFF"
        $toggleItem.ForeColor = [System.Drawing.Color]::Red
    }
})

$wakeItem.Add_Click({ Send-Command "WAKE" })

$startMatchboxItem.Add_Click({
    $consolePath = Join-Path $LUMAX_ROOT "Start_LUMAX.ps1"
    if (Test-Path $consolePath) {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$consolePath`" vr"
    }
})

$openConsoleItem.Add_Click({
    $consolePath = Join-Path $LUMAX_ROOT "Start_LUMAX.ps1"
    if (Test-Path $consolePath) {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$consolePath`""
    }
})

$openLogsItem.Add_Click({
    if (Test-Path $SvcLog) {
        Start-Process notepad.exe $SvcLog
    } elseif (Test-Path (Join-Path $LUMAX_ROOT ".logs")) {
        Start-Process explorer.exe (Join-Path $LUMAX_ROOT ".logs")
    }
})

# Services submenu
$servicesMenu = New-Object System.Windows.Forms.ToolStripMenuItem
$servicesMenu.Text = "Services"
[void]$contextMenu.Items.Add($servicesMenu)

$servicesEnableItem = New-Object System.Windows.Forms.ToolStripMenuItem
$servicesEnableItem.Text = "Enable"
$servicesEnableItem.ForeColor = [System.Drawing.Color]::Green
[void]$servicesMenu.DropDownItems.Add($servicesEnableItem)

$servicesDisableItem = New-Object System.Windows.Forms.ToolStripMenuItem
$servicesDisableItem.Text = "Disable"
$servicesDisableItem.ForeColor = [System.Drawing.Color]::Red
[void]$servicesMenu.DropDownItems.Add($servicesDisableItem)

[void]$servicesMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$servicesRestartItem = New-Object System.Windows.Forms.ToolStripMenuItem
$servicesRestartItem.Text = "Restart Windows Service"
$servicesRestartItem.ForeColor = [System.Drawing.Color]::Orange
[void]$servicesMenu.DropDownItems.Add($servicesRestartItem)

$servicesStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem
$servicesStatusItem.Text = "Status: Unknown"
$servicesStatusItem.Enabled = $false
[void]$servicesMenu.DropDownItems.Add($servicesStatusItem)

$servicesRestartItem.Add_Click({
    Write-TrayLog "INFO" "Tray: Restarting Windows Service..."
    try {
        # Stop the service
        Stop-Service -Name "LumaxService" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        # Clear any stale lock
        $LockDir = Join-Path $env:LOCALAPPDATA "LUMAX\locks"
        $LockFile = Join-Path $LockDir "lumax_services.lock"
        if (Test-Path $LockFile) { Remove-Item $LockFile -Force -ErrorAction SilentlyContinue }
        # Start the service
        Start-Service -Name "LumaxService" -ErrorAction SilentlyContinue
        Write-TrayLog "INFO" "Tray: Windows Service restart initiated"
        [System.Windows.Forms.MessageBox]::Show("LUMAX Windows Service restart initiated.``n`nAllow ~5 seconds for it to initialize.", "Service Restart", "OK", "Information")
    } catch {
        Write-TrayLog "ERROR" "Tray: Failed to restart Windows Service: $_"
        [System.Windows.Forms.MessageBox]::Show("Failed to restart Windows Service.`n`nError: $_`n`nTry running as Administrator.", "Service Restart Failed", "OK", "Error")
    }
})

$servicesEnableItem.Add_Click({
    Send-Command "ENABLE"
    Write-TrayLog "INFO" "Tray: Services enabled via menu"
})

$servicesDisableItem.Add_Click({
    Send-Command "DISABLE"
    Write-TrayLog "INFO" "Tray: Services disabled via menu"
})

$googleConnectItem.Add_Click({
    Start-Process "http://127.0.0.1:8080/api/consent/google/auth"
})

$microsoftConnectItem.Add_Click({
    Start-Process "http://127.0.0.1:8080/api/consent/microsoft/auth"
})

$quitItem.Add_Click({
    $script:running = $false
    $trayIcon.Visible = $false
    $trayIcon.Dispose()
    $form.Close()
})

$trayIcon.Add_Click({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        # Single-click: toggle
        if ($script:LastEnabled) {
            Send-Command "DISABLE"
        } else {
            Send-Command "ENABLE"
        }
    }
})

# --- Update Loop ---
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$script:LastEnabled = $false
$script:LastState = "AWAKE"
$script:running = $true

$script:LastRitualShown = $null

$timer.Add_Tick({
    $status = $null
    $fileAgeSec = [int]::MaxValue
    if (Test-Path $StatusFile) {
        try {
            $jsonText = [System.IO.File]::ReadAllText($StatusFile)
            if ($jsonText) {
                $status = $jsonText | ConvertFrom-Json -ErrorAction SilentlyContinue
            }
            $fileAgeSec = ((Get-Date) - (Get-Item $StatusFile).LastWriteTime).TotalSeconds
        } catch {
            $status = $null
        }
    }
    
    # Update Services submenu status
    $enabled = if ($status) { $status.enabled } else { $false }
    $state = if ($status) { $status.state } else { "UNKNOWN" }
    $serviceCount = if ($status -and $status.services) { ($status.services.PSObject.Properties | Where-Object { $_.Value.running }).Count } else { 0 }
    $servicesStatusItem.Text = "Status: $(if ($enabled) { 'ON' } else { 'OFF' }) - $serviceCount running"
    $servicesStatusItem.ForeColor = if ($enabled) { [System.Drawing.Color]::Green } else { [System.Drawing.Color]::Red }
    
    $enabled = if ($status) { $status.enabled } else { $false }
    $state = if ($status) { $status.state } else { "UNKNOWN" }
    $avatar = if ($status -and $status.avatar) { $status.avatar } else { $Config.AvatarName }
    $ritual = if ($status -and $status.ritual) { $status.ritual } else { $null }
    $script:LastEnabled = $enabled
    $script:LastState = $state
    
    # Detect stale status file (service process may have died)
    $isStale = ($fileAgeSec -gt 30)
    $isMissing = ($fileAgeSec -eq [int]::MaxValue)
    
    # Show wake ritual as balloon tip once per wake
    if ($ritual -and $ritual -ne $script:LastRitualShown -and $state -eq "AWAKE" -and -not $isStale) {
        $script:LastRitualShown = $ritual
        $trayIcon.BalloonTipText = $ritual
        $trayIcon.BalloonTipTitle = "$avatar is awake"
        $trayIcon.ShowBalloonTip(8000)
    }
    
    $statusText = "LUMAX: $avatar * "
    
    if ($isMissing) {
        # No status file at all — service never ran or was wiped
        $statusText += "off"
        $trayIcon.Icon = (Get-CachedIcon "off")
        $trayIcon.Text = "LUMAX ($avatar) — OFF (no status)"
        $toggleItem.Text = "Turn ON"
        $toggleItem.ForeColor = [System.Drawing.Color]::Green
        $wakeItem.Visible = $false
    } elseif ($isStale) {
        # Status file exists but old — service likely crashed
        $statusText += "stale"
        $trayIcon.Icon = (Get-CachedIcon "sleep")
        $trayIcon.Text = "LUMAX ($avatar) — STALE (service may have stopped)"
        $toggleItem.Text = "Turn ON"
        $toggleItem.ForeColor = [System.Drawing.Color]::Yellow
        $wakeItem.Visible = $false
        # Auto-attempt heal once per 60 seconds if stale
        if (-not $script:LastHealAttempt -or ((Get-Date) - $script:LastHealAttempt).TotalSeconds -gt 60) {
            $script:LastHealAttempt = Get-Date
            Send-Command "ENABLE"
            Write-TrayLog "INFO" "Tray auto-heal: sent ENABLE command due to stale status ($([int]$fileAgeSec)s old)"
        }
    } elseif ($enabled) {
        if ($state -eq "SLEEP") {
            $statusText += "sleep"
            $trayIcon.Icon = (Get-CachedIcon "sleep")
            $trayIcon.Text = "LUMAX ($avatar) — SLEEP"
        } else {
            $statusText += "on"
            $trayIcon.Icon = (Get-CachedIcon "on")
            $trayIcon.Text = "LUMAX ($avatar) — ACTIVE"
        }
        $toggleItem.Text = "Turn OFF"
        $toggleItem.ForeColor = [System.Drawing.Color]::Red
        $wakeItem.Visible = ($state -eq "SLEEP")
    } else {
        $statusText += "off"
        $trayIcon.Icon = (Get-CachedIcon "off")
        $trayIcon.Text = "LUMAX ($avatar) — OFF"
        $toggleItem.Text = "Turn ON"
        $toggleItem.ForeColor = [System.Drawing.Color]::Green
        $wakeItem.Visible = $false
    }
    
    $statusItem.Text = $statusText
})

$timer.Start()

# Show startup balloon if service just started
$trayIcon.BalloonTipText = "LUMAX tray active. Click to toggle."
$trayIcon.ShowBalloonTip(3000)

# Keep form alive
[System.Windows.Forms.Application]::Run($form)