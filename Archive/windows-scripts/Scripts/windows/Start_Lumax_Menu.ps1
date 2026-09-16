<#
.SYNOPSIS
  Lumax Launch Menu - Choose between VR, Web, CON, Soul Coder, or other services

.DESCRIPTION
  Interactive launcher for FoveAI-lite services:
  1. Start VR session (default)
  2. Start Soul Coder (coding agent)
  3. Start Full Backend (soul + embers + ops)
  4. Web UI Only (settings interface)
  5. CON Vessel (console chat mode)
  6. Custom Docker Compose

  Console hotkeys when running Start_FoveAI.ps1:
    [S] VR    [W] Web    [C] CON    [X] Stop Vessel
    [U] Unload services    [L] Load services
    [M] Toggle metrics mode (full/minimal)
    [Q] Quit console

.EXAMPLE
  .\Start.ps1 menu
  # Show launch menu
#>

param(
    [string]$Command = "default"
)

$ErrorActionPreference = "Continue"
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# === Colors ===
$Colors = @{
    Success = [System.ConsoleColor]::Green
    Warning = [System.ConsoleColor]::Yellow
    Error = [System.ConsoleColor]::Red
    Info = [System.ConsoleColor]::Cyan
    Highlight = [System.ConsoleColor]::Magenta
    Gray = [System.ConsoleColor]::DarkGray
}

function Write-Menu-Header {
    Clear-Host
    Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor $Colors.Highlight
    Write-Host "║          FoveAI-lite Launch Menu                               ║" -ForegroundColor $Colors.Highlight
    Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor $Colors.Highlight
    Write-Host ""
}

function Show-Menu {
    Write-Menu-Header
    
    Write-Host "Select launch option:" -ForegroundColor $Colors.Info
    Write-Host ""
    Write-Host "  [1] VR Session (default -Ultra)" -ForegroundColor $Colors.Info
    Write-Host "      └─ Headset + PCVR + GPU focus" -ForegroundColor $Colors.Gray
    Write-Host ""
    Write-Host "  [2] Soul Coder (Ollama coding agent)" -ForegroundColor $Colors.Info
    Write-Host "      └─ Qwen 9B/2B coding model + pause/resume" -ForegroundColor $Colors.Gray
    Write-Host ""
    Write-Host "  [3] Full Backend (soul + embers + ops)" -ForegroundColor $Colors.Info
    Write-Host "      └─ Cognition + sleep/dreams + watchdog" -ForegroundColor $Colors.Gray
    Write-Host ""
    Write-Host "  [4] Web UI Only (settings interface)" -ForegroundColor $Colors.Info
    Write-Host "      └─ http://localhost:8080" -ForegroundColor $Colors.Gray
    Write-Host ""
    Write-Host "  [5] CON Vessel (console direct chat)" -ForegroundColor $Colors.Highlight
    Write-Host "      └─ Text/voice chat from the console window" -ForegroundColor $Colors.Gray
    Write-Host ""
    Write-Host "  [6] Custom Docker Compose" -ForegroundColor $Colors.Warning
    Write-Host "      └─ Bring your own docker compose flags" -ForegroundColor $Colors.Gray
    Write-Host ""
    Write-Host "  [Q] Quit" -ForegroundColor $Colors.Error
    Write-Host ""
    
    Write-Host "Console controls when running: [S]VR [W]Web [C]CON [X]Stop [U]Unload [L]Load [M]Metrics [Q]Quit" -ForegroundColor $Colors.Gray
    Write-Host ""
    
    $choice = Read-Host "Choose (1-6, Q)"
    
    switch ($choice) {
        "1" {
            Write-Host ""
            Write-Host "Starting VR session..." -ForegroundColor $Colors.Success
            & (Join-Path $PSScriptRoot "Start_FoveAI.ps1") vr
        }
        
        "2" {
            Write-Host ""
            Write-Host "Starting Soul Coder..." -ForegroundColor $Colors.Success
            & (Join-Path $PSScriptRoot "Scripts\Start_Lumax_SoulCoder.ps1")
        }
        
        "3" {
            Write-Host ""
            Write-Host "Starting Full Backend..." -ForegroundColor $Colors.Success
            & (Join-Path $PSScriptRoot "Scripts\Start_Lumax_VR.ps1") -FullBackend
        }
        
        "4" {
            Write-Host ""
            Write-Host "Starting Web UI..." -ForegroundColor $Colors.Success
            & (Join-Path $PSScriptRoot "Start_FoveAI.ps1") web
        }
        
        "5" {
            Write-Host ""
            Write-Host "Starting CON Vessel..." -ForegroundColor $Colors.Highlight
            & (Join-Path $PSScriptRoot "Start_FoveAI.ps1") con
        }
        
        "6" {
            Write-Host ""
            Write-Host "Enter docker compose command:" -ForegroundColor $Colors.Warning
            $cmd = Read-Host "(e.g., up -d, logs -f foveai_soul, down)"
            Write-Host ""
            docker compose $cmd.Split(" ")
        }
        
        "Q" {
            exit 0
        }
        
        default {
            Write-Host "Invalid choice. Try again." -ForegroundColor $Colors.Error
            Start-Sleep -Seconds 2
            Show-Menu
        }
    }
}

# === Main ===
switch ($Command.ToLower()) {
    "menu" {
        Show-Menu
        Show-Menu  # Loop for next choice
    }
    
    "soul-coder" {
        & (Join-Path $PSScriptRoot "Scripts\Start_Lumax_SoulCoder.ps1")
    }
    
    "vr" {
        & (Join-Path $PSScriptRoot "Start_FoveAI.ps1") vr
    }
    
    "web" {
        & (Join-Path $PSScriptRoot "Start_FoveAI.ps1") web
    }
    
    "con" {
        & (Join-Path $PSScriptRoot "Start_FoveAI.ps1") con
    }
    
    "full" {
        & (Join-Path $PSScriptRoot "Scripts\Start_Lumax_VR.ps1") -FullBackend
    }
    
    default {
        # Default: show menu once then run VR
        Show-Menu
    }
}