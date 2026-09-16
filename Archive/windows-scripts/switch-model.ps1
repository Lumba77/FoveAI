# ═══════════════════════════════════════════════════════
# ATOMIC MODEL SWITCHER — Prevents Configuration Conflicts
# ═══════════════════════════════════════════════════════
# This script atomically switches model configuration to prevent
# the common problem where developers forget to update some
# variables when switching between local/cloud/XRLF models.
#
# Usage: .\switch-model.ps1 <model-profile>
# Example: .\switch-model.ps1 devin-swe-1-6-fast
#          .\switch-model.ps1 foveai-pfoveai-omni-router
#          .\switch-model.ps1 kimi-k2.7-code

param(
    [Parameter(Mandatory=$true)]
    [string]$ModelProfile
)

$ErrorActionPreference = "Stop"

# Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = "C:\Users\danie\program\LUMAX"
$ModelProfilesPath = Join-Path $ScriptDir "memory_data\model-profiles.json"
$MainEnvPath = Join-Path $ProjectRoot ".env"
$ProxyEnvPath = Join-Path $ScriptDir ".env"

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "ATOMIC MODEL SWITCHER" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Switching to: $ModelProfile" -ForegroundColor Yellow

# ── Optional: Set proxy mode ─────────────────────────────────────────────
$ProxyMode = "routing"  # default
if ($args -contains "--transparent") {
    $ProxyMode = "transparent"
    Write-Host "Proxy Mode: TRANSPARENT (direct passthrough)" -ForegroundColor Yellow
} elseif ($args -contains "--routing") {
    $ProxyMode = "routing"
    Write-Host "Proxy Mode: ROUTING (foveation enabled)" -ForegroundColor Yellow
}

# Load model profiles
if (-not (Test-Path $ModelProfilesPath)) {
    Write-Host "ERROR: Model profiles not found at $ModelProfilesPath" -ForegroundColor Red
    exit 1
}

$Profiles = Get-Content $ModelProfilesPath | ConvertFrom-Json

if (-not $Profiles.$ModelProfile) {
    Write-Host "ERROR: Model profile '$ModelProfile' not found" -ForegroundColor Red
    Write-Host "Available profiles:" -ForegroundColor Cyan
    $Profiles.PSObject.Properties.Name | ForEach-Object { Write-Host "  - $_" }
    exit 1
}

$ModelConfig = $Profiles.$ModelProfile
Write-Host "Loaded profile: $($ModelConfig.label)" -ForegroundColor Green

# ── Step 1: Calculate atomic configuration changes ──────────────────────
$ConfigChanges = @{
    "XRLF_COGNITIVE_MODE" = $ModelConfig.cognitive_mode
    "XRLF_CHAT_PROVIDER" = $ModelConfig.provider
    "XRLF_PROXY_TARGET" = $ModelConfig.upstream_url
    "XRLF_SPOOF_CONTEXT_WINDOW" = $ModelConfig.spoof_context_window
    "XRLF_PROXY_AGGRESSION" = $ModelConfig.proxy_aggression
    "XRLF_CLOUD_MAX_TOKENS_CAP" = $ModelConfig.cloud_max_tokens_cap
    "XRLF_PROXY_MODE" = $ProxyMode
}

# Handle cognitive mode specific settings
if ($ModelConfig.cognitive_mode -eq "local") {
    $ConfigChanges["XRLF_LOCAL_BASE_URL"] = "http://127.0.0.1:8402/v1"
    $ConfigChanges["XRLF_RUNTIME_URL"] = "http://127.0.0.1:8402"
    $ConfigChanges["FoveAI_COGNITIVE_MODE"] = "local"
    $ConfigChanges["FoveAI_CHAT_PROVIDER"] = "lm_studio"
} elseif ($ModelConfig.cognitive_mode -eq "cloud") {
    $ConfigChanges["XRLF_LOCAL_BASE_URL"] = $ModelConfig.upstream_url
    $ConfigChanges["FoveAI_COGNITIVE_MODE"] = "cloud"
    $ConfigChanges["FoveAI_CHAT_PROVIDER"] = $ModelConfig.provider
}

# ── Step 2: Apply changes to main .env (FoveAI_ variables) ─────────────────
Write-Host "`nStep 1: Updating main .env (FoveAI_ variables)..." -ForegroundColor Cyan

if (Test-Path $MainEnvPath) {
    $EnvContent = Get-Content $MainEnvPath -Raw
    $EnvLines = $EnvContent -split "`r?`n"
    $UpdatedLines = @()
    $ProcessedKeys = @{}
    
    # First pass: update existing lines
    foreach ($Line in $EnvLines) {
        $LineTrimmed = $Line.Trim()
        $Match = $false
        
        foreach ($Key in $ConfigChanges.Keys) {
            $LumaxKey = $Key -replace "XRLF_", "FoveAI_"
            if ($LineTrimmed -match "^${LumaxKey}=") {
                $UpdatedLines += "${LumaxKey}=$($ConfigChanges[$Key])"
                $ProcessedKeys[$LumaxKey] = $true
                $Match = $true
                Write-Host "  ✓ Updated $LumaxKey" -ForegroundColor Green
                break
            }
        }
        
        if (-not $Match) {
            $UpdatedLines += $Line
        }
    }
    
    # Second pass: add missing keys
    foreach ($Key in $ConfigChanges.Keys) {
        $LumaxKey = $Key -replace "XRLF_", "FoveAI_"
        if (-not $ProcessedKeys.ContainsKey($LumaxKey)) {
            $UpdatedLines += "${LumaxKey}=$($ConfigChanges[$Key])"
            Write-Host "  + Added $LumaxKey" -ForegroundColor Yellow
        }
    }
    
    $EnvContent = $UpdatedLines -join "`n"
    Set-Content -Path $MainEnvPath -Value $EnvContent -NoNewline
    Write-Host "  → Main .env updated" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Main .env not found, skipping" -ForegroundColor Yellow
}

# ── Step 3: Apply changes to proxy .env (XRLF_ variables) ─────────────────
Write-Host "`nStep 2: Updating proxy .env (XRLF_ variables)..." -ForegroundColor Cyan

if (Test-Path $ProxyEnvPath) {
    $EnvContent = Get-Content $ProxyEnvPath -Raw
    $EnvLines = $EnvContent -split "`r?`n"
    $UpdatedLines = @()
    $ProcessedKeys = @{}
    
    # First pass: update existing lines
    foreach ($Line in $EnvLines) {
        $LineTrimmed = $Line.Trim()
        $Match = $false
        
        foreach ($Key in $ConfigChanges.Keys) {
            if ($LineTrimmed -match "^${Key}=") {
                $UpdatedLines += "${Key}=$($ConfigChanges[$Key])"
                $ProcessedKeys[$Key] = $true
                $Match = $true
                Write-Host "  ✓ Updated $Key" -ForegroundColor Green
                break
            }
        }
        
        if (-not $Match) {
            $UpdatedLines += $Line
        }
    }
    
    # Second pass: add missing keys
    foreach ($Key in $ConfigChanges.Keys) {
        if (-not $ProcessedKeys.ContainsKey($Key)) {
            $UpdatedLines += "${Key}=$($ConfigChanges[$Key])"
            Write-Host "  + Added $Key" -ForegroundColor Yellow
        }
    }
    
    $EnvContent = $UpdatedLines -join "`n"
    Set-Content -Path $ProxyEnvPath -Value $EnvContent -NoNewline
    Write-Host "  → Proxy .env updated" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Proxy .env not found, skipping" -ForegroundColor Yellow
}

# ── Step 4: Sync API keys if needed ───────────────────────────────────────
Write-Host "`nStep 4: Syncing API keys..." -ForegroundColor Cyan

if ($ModelConfig.api_key_env -and $ModelConfig.api_key_env -ne "") {
    $ApiKeyEnv = $ModelConfig.api_key_env
    $MainEnvContent = Get-Content $MainEnvPath -Raw
    $ProxyEnvContent = Get-Content $ProxyEnvPath -Raw
    
    # Check if API key exists in main .env
    if ($MainEnvContent -match "^${ApiKeyEnv}=(.+)$") {
        $ApiKeyValue = $matches[1].Trim()
        
        # Sync to proxy .env
        if ($ProxyEnvContent -match "^${ApiKeyEnv}=.*$") {
            $ProxyEnvContent = $ProxyEnvContent -replace "^${ApiKeyEnv}=.*$", "${ApiKeyEnv}=$ApiKeyValue"
        } else {
            $ProxyEnvContent += "`n${ApiKeyEnv}=$ApiKeyValue"
        }
        
        Set-Content -Path $ProxyEnvPath -Value $ProxyEnvContent -NoNewline
        Write-Host "  ✓ Synced $ApiKeyEnv" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $ApiKeyEnv not set in main .env" -ForegroundColor Yellow
    }
}

# ── Step 5: Update active-model.json ───────────────────────────────────────
Write-Host "`nStep 5: Updating active-model.json..." -ForegroundColor Cyan

$ActiveModelPath = Join-Path $ScriptDir "memory_data\active-model.json"
$ActiveModelData = @{
    model = $ModelProfile
    appliedAt = (Get-Date).ToString("o")
}

try {
    $ActiveModelData | ConvertTo-Json -Depth 10 | Set-Content -Path $ActiveModelPath -NoNewline
    Write-Host "  ✓ Updated active-model.json" -ForegroundColor Green
} catch {
    Write-Host "  ⚠ Failed to update active-model.json: $_" -ForegroundColor Yellow
}

# ── Step 6: Verification Summary ─────────────────────────────────────────
Write-Host "`nStep 6: Configuration verification..." -ForegroundColor Cyan
Write-Host "`n═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "CONFIGURATION APPLIED SUCCESSFULLY" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Model: $($ModelConfig.label)" -ForegroundColor White
Write-Host "Provider: $($ModelConfig.provider)" -ForegroundColor White
Write-Host "Mode: $($ModelConfig.cognitive_mode)" -ForegroundColor White
Write-Host "Upstream: $($ModelConfig.upstream_url)" -ForegroundColor White
Write-Host "Context Window: $($ModelConfig.spoof_context_window)" -ForegroundColor White
Write-Host "Proxy Aggression: $($ModelConfig.proxy_aggression)" -ForegroundColor White
Write-Host "Proxy Mode: $ProxyMode" -ForegroundColor White
Write-Host "`n⚠️  RESTART THE FOVEATED MEMORY PROXY TO APPLY CHANGES" -ForegroundColor Yellow
Write-Host "   cd $ScriptDir && node server.js" -ForegroundColor Gray
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
