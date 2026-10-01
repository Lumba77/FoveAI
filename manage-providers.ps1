# ═══════════════════════════════════════════════════════
# PROVIDER MANAGEMENT — Add Custom Providers
# ═══════════════════════════════════════════════════════
# This script manages custom providers in the providers.json file
# allowing you to add new model providers without manual editing.
#
# Usage: .\manage-providers.ps1 <action> [params]
# Example: .\manage-providers.ps1 list
#          .\manage-providers.ps1 add "my-provider" "http://localhost:1234/v1" "my-api-key"
#          .\manage-providers.ps1 remove "my-provider"

param(
    [Parameter(Mandatory=$false)]
    [string]$Action = "list",
    
    [Parameter(Mandatory=$false)]
    [string]$ProviderId,
    
    [Parameter(Mandatory=$false)]
    [string]$BaseUrl,
    
    [Parameter(Mandatory=$false)]
    [string]$ApiKey,
    
    [Parameter(Mandatory=$false)]
    [string]$Type = "openai_compatible"
)

$ErrorActionPreference = "Stop"

# Paths
$ProjectRoot = "C:\Users\danie\program\LUMAX"
$ProvidersPath = Join-Path $ProjectRoot ".xrlf\providers.json"

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "PROVIDER MANAGEMENT" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

# Load providers
if (-not (Test-Path $ProvidersPath)) {
    Write-Host "ERROR: Providers file not found at $ProvidersPath" -ForegroundColor Red
    exit 1
}

$Providers = Get-Content $ProvidersPath | ConvertFrom-Json

switch ($Action) {
    "list" {
        Write-Host "`nAvailable Providers:" -ForegroundColor Green
        $Providers.providers.PSObject.Properties | ForEach-Object {
            $Provider = $_.Value
            Write-Host "`n  📦 $($_.Name)" -ForegroundColor Cyan
            Write-Host "     Type: $($Provider.type)" -ForegroundColor White
            Write-Host "     Base URL: $($Provider.base_url)" -ForegroundColor White
            Write-Host "     Default Model: $($Provider.default_model)" -ForegroundColor White
            if ($Provider.api_key_env) {
                Write-Host "     API Key Env: $($Provider.api_key_env)" -ForegroundColor White
            }
            if ($Provider.models) {
                Write-Host "     Models: $($Provider.models.PSObject.Properties.Name -join ', ')" -ForegroundColor Gray
            }
        }
    }
    
    "add" {
        if (-not $ProviderId -or -not $BaseUrl) {
            Write-Host "ERROR: ProviderId and BaseUrl required for add action" -ForegroundColor Red
            Write-Host "Usage: .\manage-providers.ps1 add <provider-id> <base-url> [api-key] [type]" -ForegroundColor Yellow
            exit 1
        }
        
        if ($Providers.providers.$ProviderId) {
            Write-Host "ERROR: Provider '$ProviderId' already exists" -ForegroundColor Red
            exit 1
        }
        
        $NewProvider = @{
            type = $Type
            base_url = $BaseUrl
            api_key = if ($ApiKey) { $ApiKey } else { "not-needed" }
            default_model = "auto"
            models = @{}
        }
        
        if ($ApiKey) {
            $NewProvider.api_key_env = "${ProviderId.ToUpper()}_API_KEY"
            # Add to main .env
            $MainEnvPath = Join-Path $ProjectRoot ".env"
            if (Test-Path $MainEnvPath) {
                $EnvContent = Get-Content $MainEnvPath -Raw
                $EnvContent += "`n${ProviderId.ToUpper()}_API_KEY=$ApiKey"
                Set-Content -Path $MainEnvPath -Value $EnvContent -NoNewline
                Write-Host "  ✓ Added API key to main .env" -ForegroundColor Green
            }
        }
        
        $Providers.providers | Add-Member -MemberType NoteProperty -Name $ProviderId -Value $NewProvider -Force
        
        $Providers | ConvertTo-Json -Depth 10 | Set-Content -Path $ProvidersPath -NoNewline
        
        Write-Host "`n✓ Provider '$ProviderId' added successfully" -ForegroundColor Green
        Write-Host "  Base URL: $BaseUrl" -ForegroundColor White
        Write-Host "  Type: $Type" -ForegroundColor White
        if ($ApiKey) {
            Write-Host "  API Key: ****" -ForegroundColor White
        }
    }
    
    "remove" {
        if (-not $ProviderId) {
            Write-Host "ERROR: ProviderId required for remove action" -ForegroundColor Red
            exit 1
        }
        
        if (-not $Providers.providers.$ProviderId) {
            Write-Host "ERROR: Provider '$ProviderId' not found" -ForegroundColor Red
            exit 1
        }
        
        $Providers.providers.PSObject.Properties.Remove($ProviderId)
        
        $Providers | ConvertTo-Json -Depth 10 | Set-Content -Path $ProvidersPath -NoNewline
        
        Write-Host "`n✓ Provider '$ProviderId' removed successfully" -ForegroundColor Green
    }
    
    default {
        Write-Host "ERROR: Unknown action '$Action'" -ForegroundColor Red
        Write-Host "Available actions: list, add, remove" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "`n═══════════════════════════════════════════════════════" -ForegroundColor Cyan
