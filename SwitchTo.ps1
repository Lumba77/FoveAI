param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$ArgsList
)

$LumaxRoot = "C:\Users\danie\program\LUMAX"
$HistoryDir = "$LumaxRoot\.env_history"
if (-not (Test-Path $HistoryDir)) { New-Item -ItemType Directory -Path $HistoryDir | Out-Null }

$AllEnvFiles = @{
    "lumax" = "$LumaxRoot\.env"
    "spatial" = "$LumaxRoot\FoveAI\.env"
    "proxy" = "$LumaxRoot\Tools\foveated-memory\.env"
    "foveated" = "$LumaxRoot\Tools\foveated-memory\.env"
}

function Backup-Envs([array]$FilesToBackup) {
    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $backupPath = "$HistoryDir\$timestamp"
    New-Item -ItemType Directory -Path $backupPath | Out-Null
    foreach ($file in $FilesToBackup) {
        if (Test-Path $file) {
            $dest = Join-Path $backupPath (Split-Path $file -Leaf)
            $parent = (Get-Item $file).Directory.Name
            Copy-Item $file "$backupPath\${parent}_env.bak"
        }
    }
    return $timestamp
}

function Revert-Envs([int]$steps) {
    $backups = Get-ChildItem -Path $HistoryDir -Directory | Sort-Object CreationTime -Descending
    if ($backups.Count -eq 0) {
        Write-Host "No history found to revert." -ForegroundColor Red
        return
    }
    
    $targetIndex = $steps - 1
    if ($targetIndex -ge $backups.Count) { $targetIndex = $backups.Count - 1 }
    
    $targetBackup = $backups[$targetIndex]
    Write-Host "Reverting to state from $($targetBackup.Name)..." -ForegroundColor Yellow
    
    foreach ($val in $AllEnvFiles.Values) {
        $parent = (Get-Item $val).Directory.Name
        $bakFile = "$($targetBackup.FullName)\${parent}_env.bak"
        if (Test-Path $bakFile) {
            Copy-Item $bakFile $val -Force
        }
    }
    Write-Host "Successfully reverted!" -ForegroundColor Green
}

function Update-EnvVar($filePath, $key, $value) {
    if (-not (Test-Path $filePath)) { return }
    $content = Get-Content $filePath
    $updated = $false
    for ($i = 0; $i -lt $content.Length; $i++) {
        if ($content[$i] -match "^$key=") {
            $content[$i] = "$key=$value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $content += "$key=$value"
    }
    $content | Set-Content $filePath
}

$command = $ArgsList -join " "

if ($command -match "^revert\s*(\d*)$") {
    $steps = 1
    if ($matches[1]) { $steps = [int]$matches[1] }
    Revert-Envs $steps
    exit
}

# --- Action Routers ---
if ($command -match "(?i)telephone\s+(\w+)") {
    $contact = $matches[1]
    Write-Host "📞 Action Router Triggered!" -ForegroundColor Magenta
    Write-Host "Routing current active chat session to voice call with: $($contact.ToUpper())"
    # Placeholder for actual XRLF / VoIP integration script execution
    Write-Host "[XRLF] Executing VoIP handshake... (Feature Stub)" -ForegroundColor DarkGray
    exit
}

# --- Standard Mode Inference ---
$mode = "unknown"
$model = ""

if ($command -match "(?i)cloud") { $mode = "cloud" }
elseif ($command -match "(?i)local") { $mode = "local" }
elseif ($command -match "(?i)gemini|flash|pro|gpt|claude|kimi") { 
    $mode = "cloud" 
    $model = $command
}
elseif ($command -match "(?i)gguf|smart-router|llama|qwen") { 
    $mode = "local" 
    $model = $command
}

# --- Target Filtering (only/just/solo/for) ---
$targetFiles = @()
$targetLabel = "ALL SYSTEMS"

if ($command -match "(?i)(?:only|just|solo|for)\s*(?:for)?\s*(lumax|spatial|proxy|foveated)") {
    $targetName = $matches[1].ToLower()
    $targetFiles += $AllEnvFiles[$targetName]
    $targetLabel = $targetName.ToUpper()
} 
elseif ($command -match "(?i)(lumax|spatial|proxy|foveated)\s*(only|just|solo)") {
    $targetName = $matches[1].ToLower()
    $targetFiles += $AllEnvFiles[$targetName]
    $targetLabel = $targetName.ToUpper()
}
else {
    $targetFiles = $AllEnvFiles.Values
}

if ($mode -eq "unknown") {
    Write-Host "Could not infer mode from command: '$command'" -ForegroundColor Red
    Write-Host "Try 'SwitchTo cloud', 'SwitchTo local', or 'SwitchTo Gemini Flash'"
    exit
}

Write-Host "🧠 Smart Inference:" -ForegroundColor Cyan
Write-Host "   Command:  $command"
Write-Host "   Mode:     $($mode.ToUpper())"
Write-Host "   Target:   $targetLabel"
if ($model) { Write-Host "   Model:    $model" }

Backup-Envs $targetFiles | Out-Null

Write-Host "`n🔄 Applying changes to $targetLabel..." -ForegroundColor Yellow

foreach ($file in $targetFiles) {
    if ($mode -eq "cloud") {
        Update-EnvVar $file "LUMAX_COGNITIVE_MODE" "cloud"
        Update-EnvVar $file "XRLF_RUNTIME_MODE" "cloud"
        Update-EnvVar $file "LUMAX_CHAT_PROVIDER" "ollama_cloud"
        if ($model) { Update-EnvVar $file "LUMAX_MODEL_CLOUD_ID" $model }
    } else {
        Update-EnvVar $file "LUMAX_COGNITIVE_MODE" "local"
        Update-EnvVar $file "XRLF_RUNTIME_MODE" "local"
        Update-EnvVar $file "LUMAX_CHAT_PROVIDER" "lm_studio"
        if ($model) { Update-EnvVar $file "LUMAX_MODEL_LOCAL_ID" $model }
    }
}

Write-Host "✅ Switch complete!" -ForegroundColor Green
