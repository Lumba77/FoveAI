# install-super-memory.ps1
# Run: irm https://foveai.1um6a.se/install-super-memory.ps1 | iex
# Or local: .\skills\xrl-super-memory\references\install-super-memory.ps1
#Requires -Version 7.6
param(
    [string]$RepoRoot = 'C:\Users\danie\program\LUMAX',
    [string]$ProxyPort = '8400',
    [string]$DashboardPort = '8414',
    [switch]$SkipProxyCheck,
    [switch]$SkipWTProfile
)

$ErrorActionPreference = 'Stop'
$ModuleName = 'LumaxMemory'
$modulePaths = ($env:PSModulePath -split ';') | Where-Object { $_ -like "*$env:USERPROFILE*" }
$ModuleDir = if ($modulePaths) { Join-Path ($modulePaths | Select-Object -First 1) $ModuleName } else { Join-Path $env:USERPROFILE "Documents\PowerShell\Modules\$ModuleName" }
$WTSettingsPath = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'
if (-not (Test-Path $WTSettingsPath)) {
    $WTSettingsPath = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json'
}

function Test-ProxyHealth {
    if ($SkipProxyCheck) { return $true }
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$ProxyPort/health" -TimeoutSec 3
        Write-Host "Proxy status: $($r.status) | mode: $($r.mode) | cloud_cap: $($r.cloud_cap)" -ForegroundColor Cyan
        return $r.status -eq 'ONLINE'
    } catch {
        Write-Warning "Proxy not responding on port $ProxyPort. Start it with: node Tools/foveated-memory/server.js"
        return $false
    }
}

function Install-LumaxMemoryModule {
    if (Test-Path $ModuleDir) { Remove-Item -Path $ModuleDir -Recurse -Force }
    New-Item -ItemType Directory -Path $ModuleDir -Force | Out-Null

    $psm1 = @'
#Requires -Version 7.6
function Show-MemoryMeter {
    param([int]$Width = 40)
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8400/health' -TimeoutSec 3
    } catch { Write-Warning 'Proxy offline'; return }
    $pct = if ($h.context_chars -and $h.context_chars -gt 0) { [math]::Round(($h.trimmed_chars / $h.context_chars) * 100) } else { 7 }
    $filled = [math]::Round($Width * $pct / 100)
    $bar = ('█' * $filled).PadRight($Width, '░')
    Write-Host "`n  Memory ring  [$bar] $pct%" -ForegroundColor Cyan
    Write-Host "  mode=$($h.mode)  cap=$($h.cloud_cap)  preserve=$($h.preserve_last)  workspace=$($h.workspace)" -ForegroundColor DarkGray
}

function Show-MemoryPrompt {
    $branch = (git -C $global:LumaxRoot branch --show-current 2>$null) ?? 'main'
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8400/health' -TimeoutSec 2
        $cap = $h.cloud_cap ?? 'auto'
    } catch { $cap = 'offline' }
    $prompt = "`n`n[$(Get-Date -Format 'HH:mm:ss')] "
    $prompt += "$([char]0x2726) "
    $prompt += "FoveAI:$branch | mem:$cap "
    $prompt += "`n$([char]0x2192) "
    return $prompt
}

function Get-LumaxContext {
    param([int]$HistoryLines = 20)
    $ctx = [ordered]@{
        cwd = (Get-Location).Path
        time = Get-Date -Format 'o'
        branch = (git -C (Get-Location).Path branch --show-current 2>$null) ?? (git -C $global:LumaxRoot branch --show-current 2>$null) ?? 'main'
        repo = $global:LumaxRoot
        user = $env:USERNAME
    }
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8400/health' -TimeoutSec 2
        $ctx.mode = $h.mode
        $ctx.cap = $h.cloud_cap
        $ctx.workspace = $h.workspace
    } catch { $ctx.proxy = 'offline' }
    if (Get-Module PSReadline -ListAvailable) {
        try {
            $history = [Microsoft.PowerShell.PSConsoleReadLine]::GetHistoryItems()
            $ctx.recent_history = ($history | Select-Object -Last $HistoryLines | ForEach-Object { $_.CommandLine }) -join "`n"
        } catch { $ctx.recent_history = '' }
    }
    return $ctx
}

function Get-LumaxEnv {
    param([string]$Key)
    $envPath = Join-Path $global:LumaxRoot '.env'
    if (-not (Test-Path $envPath)) { return $null }
    foreach ($line in (Get-Content $envPath -Encoding utf8)) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $i = $line.IndexOf('=')
        if ($i -lt 0) { continue }
        $k = $line.Substring(0, $i).Trim()
        $v = $line.Substring($i + 1).Trim().Trim("'\"").Trim('"')
        if ($k -eq $Key) { return $v }
    }
    return $null
}

function Invoke-LumaxAI {
    param(
        [Parameter(Mandatory, ValueFromRemainingArguments)]
        [string]$Query,
        [string]$Mode = 'ask',
        [string]$Workspace = 'terminal',
        [switch]$NoContext
    )
    $proxyUrl = 'http://127.0.0.1:8400/v1/chat/completions'
    $model = Get-LumaxEnv 'FoveAI_MODEL_CLOUD_ID'
    if (-not $model) { $model = 'qwen2.5:14b' }

    $system = switch ($Mode) {
        'do' { 'You are the inline FoveAI terminal assistant. Help the user accomplish the task. Prefer shell/PowerShell commands or code. Be concise, actionable, and explain what you propose before giving commands.' }
        'remember' { 'You are the FoveAI memory assistant. Summarize the key fact the user wants to remember so it can be recalled later. Keep it atomic and include tags.' }
        default { 'You are the inline FoveAI terminal assistant. Answer the user concisely. You can see their working directory, git branch, recent command history, and memory state. Ask clarifying questions if needed.' }
    }

    $messages = @()
    $messages += @{ role = 'system'; content = $system }
    if (-not $NoContext) {
        $ctx = Get-LumaxContext
        $messages += @{ role = 'system'; name = 'context'; content = ($ctx | ConvertTo-Json -Depth 4) }
    }
    $messages += @{ role = 'user'; content = $Query }

    $body = @{
        model = $model
        messages = $messages
        stream = $false
        max_tokens = 1024
    } | ConvertTo-Json -Depth 8

    try {
        $resp = Invoke-RestMethod -Uri $proxyUrl -Method POST -Headers @{
            'Content-Type' = 'application/json'
            'Authorization' = "Bearer $Workspace"
        } -Body $body -TimeoutSec 120
        $content = $resp.choices[0].message.content
        Write-Host "`n[Lumax AI]" -ForegroundColor Cyan
        Write-Host $content -ForegroundColor White
        Write-Host ''
        return $content
    } catch {
        Write-Warning "FoveAI AI request failed: $_"
    }
}

function ask {
    param([Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Query)
    Invoke-LumaxAI -Mode ask -Query ($Query -join ' ')
}

function doit {
    param([Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Query)
    Invoke-LumaxAI -Mode do -Query ($Query -join ' ')
}

function remember {
    param([Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Fact)
    $summary = Invoke-LumaxAI -Mode remember -Query "Remember: $($Fact -join ' ')" -Workspace terminal
    if ($summary) {
        try {
            Invoke-RestMethod -Uri 'http://127.0.0.1:8400/api/memory/add' -Method POST -Headers @{ 'Content-Type' = 'application/json'; 'Authorization' = 'Bearer terminal' } -Body (@{ content = $summary; tags = @('terminal','remember') } | ConvertTo-Json -Depth 4) -TimeoutSec 10 | Out-Null
            Write-Host '[memory] fact stored' -ForegroundColor Green
        } catch { Write-Warning "Could not store memory: $_" }
    }
}

function recall {
    param([Parameter(ValueFromRemainingArguments)][string[]]$Query)
    try {
        $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8400/api/memory/search' -Method POST -Headers @{
            'Content-Type' = 'application/json'
            'Authorization' = 'Bearer terminal'
        } -Body (@{ query = ($Query -join ' '); limit = 5 } | ConvertTo-Json -Depth 4) -TimeoutSec 10
        Write-Host "`n[recall results]" -ForegroundColor Cyan
        $r.results | ForEach-Object { Write-Host "- $($_.content)" -ForegroundColor White }
    } catch {
        Write-Warning "recall failed: $_"
    }
}

function skill {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(ValueFromRemainingArguments)][string[]]$Args
    )
    $skillDir = Join-Path $global:LumaxRoot 'skills' $Name
    if (-not (Test-Path $skillDir)) {
        $skillDir = Get-ChildItem -Path (Join-Path $global:LumaxRoot 'skills') -Directory -Filter "*$Name*" | Select-Object -First 1
        if (-not $skillDir) { Write-Warning "Skill '$Name' not found"; return }
        $skillDir = $skillDir.FullName
    }
    $skillMd = Join-Path $skillDir 'SKILL.md'
    if (Test-Path $skillMd) {
        Write-Host "[skill] loading $Name..." -ForegroundColor Cyan
        $content = Get-Content $skillMd -Raw -Encoding utf8
        $summary = ($content -split "`n" | Select-Object -First 20) -join "`n"
        Invoke-LumaxAI -Mode do -Query "Use this FoveAI skill to help the user:`n`nSKILL: $Name`n`n$summary`n`nUser request: $($Args -join ' ')" -Workspace terminal
    } else {
        Write-Warning "SKILL.md missing for $Name"
    }
}

function Start-SuperTerminal {
    Start-Process wt.exe -ArgumentList 'new-tab', '--profile', 'FoveAI Super Memory', '-d', $global:LumaxRoot
}

function Start-MemoryKiosk {
    Start-Process 'http://127.0.0.1:8401'
}

function Start-SuperKiosk {
    Start-SuperTerminal
}

function Set-MemoryToggle {
    param(
        [Parameter(Mandatory)]
        [ValidateSet('compression','recall','strip')]
        [string]$Name,
        [Parameter(Mandatory)]
        [bool]$Value
    )
    $envName = "FoveAI_TOGGLE_$($Name.ToUpper())"
    Set-Item -Path "env:$envName" -Value $Value.ToString().ToLower()
    Write-Host "Toggle $Name = $Value" -ForegroundColor Green
}

function Register-LumaxWindowsTerminalProfile {
    $settingsPath = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'
    if (-not (Test-Path $settingsPath)) {
        $settingsPath = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json'
    }
    if (-not (Test-Path $settingsPath)) { throw 'Windows Terminal settings.json not found' }
    $json = Get-Content $settingsPath -Raw | ConvertFrom-Json -Depth 32
    if (-not $json.profiles) { $json | Add-Member -NotePropertyName profiles -NotePropertyValue @{list=@()} }
    if (-not $json.profiles.list) { $json.profiles | Add-Member -NotePropertyName list -NotePropertyValue @() }
    $json.profiles.list = @($json.profiles.list | Where-Object { $_.name -ne 'FoveAI Super Memory' })
    $bg = Join-Path $global:LumaxRoot 'skills\xrl-super-memory\templates\memory-bg.png'
    $profile = @{
        name = 'FoveAI Super Memory'
        commandline = 'pwsh.exe -NoExit -Command "Import-Module LumaxMemory -Force; Show-MemoryMeter; function prompt { Show-MemoryPrompt }"'
        startingDirectory = $global:LumaxRoot
        icon = 'ms-appx:///Images/Square44x44Logo.png'
        colorScheme = 'Tango Dark'
        useAcrylic = $true
        acrylicOpacity = 0.75
        backgroundImage = $bg
        backgroundImageStretchMode = 'uniformToFill'
        backgroundImageOpacity = 0.12
        font = @{ face = 'Cascadia Mono'; size = 11 }
        padding = '16'
    }
    $json.profiles.list += $profile
    $json | ConvertTo-Json -Depth 32 | Set-Content $settingsPath -Encoding utf8
    Write-Host 'Windows Terminal profile registered: FoveAI Super Memory' -ForegroundColor Green
}

# Add common shells to PATH if present
$shellPaths = @(
    'C:\Program Files\Git\usr\bin',
    'C:\Program Files\Git\bin',
    'C:\Program Files\PowerShell\7',
    'C:\msys64\usr\bin',
    'C:\cygwin64\bin'
)
foreach ($p in $shellPaths) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}

$global:LumaxRoot = if (Test-Path 'C:\Users\danie\program\LUMAX') { 'C:\Users\danie\program\LUMAX' } else { (Get-Location).Path }

Export-ModuleMember -Function Show-MemoryMeter, Show-MemoryPrompt, Invoke-LumaxAI, ask, do, remember, recall, skill, Start-SuperTerminal, Start-MemoryKiosk, Start-SuperKiosk, Set-MemoryToggle, Register-LumaxWindowsTerminalProfile
'@

    $psm1 | Set-Content (Join-Path $ModuleDir "$ModuleName.psm1") -Encoding utf8
    $manifest = @{
        RootModule = "$ModuleName.psm1"
        ModuleVersion = '1.1.0'
        Author = 'Hermes Agent'
        Description = 'Foveated memory visualization and AI-assisted terminal controls for FoveAI'
        PowerShellVersion = '7.6'
        FunctionsToExport = @('Show-MemoryMeter','Show-MemoryPrompt','Invoke-LumaxAI','ask','doit','remember','recall','skill','Start-SuperTerminal','Start-MemoryKiosk','Start-SuperKiosk','Set-MemoryToggle','Register-LumaxWindowsTerminalProfile')
    }
    $manifestPath = Join-Path $ModuleDir "$ModuleName.psd1"
    New-ModuleManifest -Path $manifestPath @manifest | Out-Null

    Import-Module $manifestPath -Force
    Write-Host "PowerShell module installed: $ModuleDir" -ForegroundColor Green
}

function Install-DashboardAssets {
    $publicDir = Join-Path $RepoRoot 'Tools\foveated-memory\public'
    if (-not (Test-Path $publicDir)) { New-Item -ItemType Directory -Path $publicDir -Force | Out-Null }
    $src = Join-Path $RepoRoot 'skills\xrl-super-memory\templates'
    Copy-Item -Path (Join-Path $src 'super-memory-dashboard.html') -Destination (Join-Path $publicDir 'index.html') -Force
    Copy-Item -Path (Join-Path $src 'super-memory-prompt-gui.html') -Destination (Join-Path $publicDir 'prompt-kiosk.html') -Force
    Write-Host "Dashboard assets copied to $publicDir" -ForegroundColor Green
}

function Add-DashboardRouteToProxy {
    $server = Join-Path $RepoRoot 'Tools\foveated-memory\server.js'
    $marker = "// === SUPER-MEMORY DASHBOARD STATIC ROUTE ==="
    $content = Get-Content $server -Raw -Encoding utf8
    if ($content -match [regex]::Escape($marker)) {
        Write-Host "Dashboard route already present in server.js" -ForegroundColor DarkGray
        return
    }
    $snippet = @"

$marker
const path = require('path');
app.use('/memory', express.static(path.join(__dirname, 'public')));
if (!global._dashboardServer) {
  global._dashboardServer = require('http').createServer(app).listen($DashboardPort, '127.0.0.1', function () {
    console.log('[SuperMemory] dashboard at http://127.0.0.1:$DashboardPort/memory');
  });
}
"@
    $listenPattern = "const _server = app.listen(config.proxy_port, '127.0.0.1', () => {"
    $insertAfter = "});"
    $idx = $content.IndexOf($listenPattern)
    if ($idx -ge 0) {
        $endIdx = $content.IndexOf($insertAfter, $idx)
        if ($endIdx -ge 0) {
            $insertPos = $endIdx + $insertAfter.Length
            $content = $content.Substring(0, $insertPos) + $snippet + $content.Substring($insertPos)
            $content | Set-Content $server -Encoding utf8 -NoNewline
            Write-Host "Dashboard route added to server.js (restart proxy to activate)" -ForegroundColor Yellow
            return
        }
    }
    Write-Warning "Could not locate proxy listen block to inject dashboard route"
}

function Ensure-BackgroundImage {
    $img = Join-Path $RepoRoot 'skills\xrl-super-memory\templates\memory-bg.png'
    if (Test-Path $img) { return }
    try {
        Add-Type -AssemblyName System.Drawing
        $bmp = New-Object System.Drawing.Bitmap 1920, 1080
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.Clear([System.Drawing.Color]::FromArgb(255, 15, 23, 42))
        $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(40, 34, 211, 238))
        for ($r = 180; $r -lt 400; $r += 12) {
            $g.DrawEllipse($pen, 960 - $r, 540 - $r, 2 * $r, 2 * $r)
        }
        $bmp.Save($img, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        Write-Host "Generated background image: $img" -ForegroundColor Green
    } catch {
        Write-Warning "Could not generate background image: $_"
    }
}

# ── Main ──────────────────────────────────────────────────────────────
Write-Host "`n$([char]0x2726) Installing FoveAI Super Memory`n" -ForegroundColor Cyan
$proxyOk = Test-ProxyHealth
Ensure-BackgroundImage
Install-LumaxMemoryModule
Install-DashboardAssets
Add-DashboardRouteToProxy

if (-not $SkipWTProfile) {
    try { Register-LumaxWindowsTerminalProfile } catch { Write-Warning $_ }
}

Write-Host "`nDone." -ForegroundColor Green
Write-Host "  Dashboard : http://127.0.0.1:$DashboardPort/memory" -ForegroundColor Cyan
Write-Host "  Kiosk     : http://127.0.0.1:$DashboardPort/memory/prompt-kiosk.html" -ForegroundColor Cyan
Write-Host "  Commands  : Show-MemoryMeter, ask, doit, remember, recall, skill, Start-SuperTerminal" -ForegroundColor Cyan
if (-not $proxyOk) {
    Write-Host "`nRestart the proxy to activate the dashboard route:" -ForegroundColor Yellow
    Write-Host "  taskkill /F /IM node.exe; node Tools/foveated-memory/server.js" -ForegroundColor Yellow
}
