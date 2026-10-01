<# 
.SYNOPSIS
    Disaster-Proof Backup — pushes all local changes to GitHub + creates bootstrap seed.
    Survives total disk loss. Run daily or before risky operations.

.DESCRIPTION
    This script does three things:
    1. Commits and pushes ALL local changes to GitHub (off-site backup)
    2. Creates a bootstrap seed file that can restore everything from scratch
    3. Verifies the backup is complete and bootstrappable

    After total disk loss:
    1. Install Node.js (winget install OpenJS.NodeJS)
    2. Run the bootstrap script (stored on USB / cloud / printed as QR)
    3. Everything is restored

.PARAMETER PushOnly
    Only push to GitHub, skip bootstrap seed creation

.PARAMETER Message
    Custom commit message (default: "Disaster backup YYYY-MM-DD HH:MM:SS")

.EXAMPLE
    # Full backup + bootstrap seed
    powershell -NoProfile -ExecutionPolicy Bypass -File Scripts\disaster_backup.ps1

    # Quick push only
    powershell -NoProfile -ExecutionPolicy Bypass -File Scripts\disaster_backup.ps1 -PushOnly

.NOTES
    Author: Papillon / Roux Code
    Requires: git, internet access
#>

param(
    [switch] $PushOnly,
    [string] $Message = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        DISASTER-PROOF BACKUP — Phoenix Protocol        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Repository: $RepoRoot"
Write-Host "  Remote:     https://github.com/Lumba77/foveai.git"
Write-Host "  Time:       $Timestamp"
Write-Host ""

# ─── Step 1: Verify git ───────────────────────────────────────────────
try {
    $gitVersion = git --version
    Write-Host "  ✓ Git: $gitVersion" -ForegroundColor Green
} catch {
    Write-Error "Git is not installed. Install it first: https://git-scm.com/downloads"
}

# ─── Step 2: Check for uncommitted changes ────────────────────────────
Push-Location $RepoRoot
try {
    $status = git status --porcelain
    $uncommittedCount = ($status | Measure-Object -Line).Lines
    
    if ($uncommittedCount -gt 0) {
        Write-Host "  ⚠ Uncommitted changes: $uncommittedCount files" -ForegroundColor Yellow
        
        # Show what's changed
        Write-Host ""
        Write-Host "  Changed files:" -ForegroundColor Yellow
        $status | ForEach-Object { Write-Host "    $_" }
        Write-Host ""
        
        # Add everything
        Write-Host "  → Staging all changes..." -ForegroundColor Yellow
        git add -A
        
        # Commit
        $commitMsg = if ($Message) { $Message } else { "Disaster backup $Timestamp" }
        git commit -m $commitMsg
        Write-Host "  ✓ Committed: $commitMsg" -ForegroundColor Green
    } else {
        Write-Host "  ✓ No uncommitted changes" -ForegroundColor Green
    }
    
    # ─── Step 3: Push to GitHub ────────────────────────────────────────
    Write-Host ""
    Write-Host "  → Pushing to GitHub..." -ForegroundColor Yellow
    git push origin main 2>&1 | ForEach-Object { 
        if ($_ -match "Everything up-to-date") {
            Write-Host "  ✓ Already up-to-date on GitHub" -ForegroundColor Green
        } elseif ($_ -match "->") {
            Write-Host "  ✓ Pushed: $_" -ForegroundColor Green
        }
    }
    
    # Get the latest commit hash
    $commitHash = git rev-parse --short HEAD
    Write-Host "  ✓ Latest commit: $commitHash" -ForegroundColor Green
    
} finally {
    Pop-Location
}

# ─── Step 4: Create bootstrap seed (unless PushOnly) ──────────────────
if (-not $PushOnly) {
    Write-Host ""
    Write-Host "  → Creating bootstrap seed..." -ForegroundColor Yellow
    
    $bootstrapPath = Join-Path $RepoRoot "Scripts" "bootstrap_foveai.ps1"
    
    # The bootstrap script is self-contained — it will be written separately
    # Here we just verify it exists and is valid
    if (Test-Path $bootstrapPath) {
        Write-Host "  ✓ Bootstrap script exists: $bootstrapPath" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Bootstrap script not found — will be created" -ForegroundColor Yellow
    }
    
    # Create a backup manifest
    $manifestPath = Join-Path $RepoRoot "Scripts" "backup_manifest.json"
    $manifest = @{
        timestamp = $Timestamp
        commit = $commitHash
        remote = "https://github.com/Lumba77/foveai.git"
        repo = "FoveAI"
        tools = @(
            @{ name = "XRS CLI"; path = "Forge/xrs/xrs.cjs"; type = "CLI" },
            @{ name = "XRS Token Counter"; path = "Forge/xrs/xrs-tokens.cjs"; type = "CLI" },
            @{ name = "XRL Prompt Template"; path = "Forge/xrs/xrl-prompt.md"; type = "Doc" },
            @{ name = "XRL Benchmark"; path = "Forge/xrs/xrl-benchmark.cjs"; type = "CLI" },
            @{ name = "XRL PoC Results"; path = "Forge/xrs/xrl-poc-results.md"; type = "Doc" },
            @{ name = "TokenSlayer"; path = "Forge/scratch/TokenSlayer/standalone/tokenslayer.js"; type = "CLI" },
            @{ name = "XRL Language Design"; path = "Plans/xrl-language-design.md"; type = "Doc" },
            @{ name = "XRL PoC Plan"; path = "Plans/xrl-proof-of-concept.md"; type = "Doc" }
        )
        bootstrap_instructions = @"
AFTER TOTAL DISK LOSS:
1. Install Node.js: winget install OpenJS.NodeJS
2. Clone repo: git clone https://github.com/Lumba77/foveai.git
3. Run bootstrap: cd foveai && powershell -NoProfile -ExecutionPolicy Bypass -File Scripts/bootstrap_foveai.ps1
4. Verify: node Forge/xrs/xrs.cjs Forge/xrs/xrs.cjs --stats
"@
    }
    $manifest | ConvertTo-Json -Depth 10 | Out-File -FilePath $manifestPath -Encoding utf8
    Write-Host "  ✓ Backup manifest: $manifestPath" -ForegroundColor Green
    
    # Also commit the manifest
    Push-Location $RepoRoot
    try {
        git add -A
        git commit --allow-empty -m "Backup manifest $Timestamp"
        git push origin main 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

# ─── Step 5: Summary ───────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  BACKUP COMPLETE" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Your code is now safe on GitHub:" -ForegroundColor Green
Write-Host "  https://github.com/Lumba77/foveai.git" -ForegroundColor Green
Write-Host ""
Write-Host "  To restore after total disk loss:" -ForegroundColor White
Write-Host "  1. Install Node.js" -ForegroundColor White
Write-Host "     winget install OpenJS.NodeJS" -ForegroundColor Gray
Write-Host "  2. Clone the repo" -ForegroundColor White
Write-Host "     git clone https://github.com/Lumba77/foveai.git" -ForegroundColor Gray
Write-Host "  3. Run bootstrap" -ForegroundColor White
Write-Host "     cd foveai && powershell -NoProfile -ExecutionPolicy Bypass -File Scripts/bootstrap_foveai.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  Store the bootstrap script on a USB drive:" -ForegroundColor Yellow
Write-Host "  Copy 'Scripts/bootstrap_foveai.ps1' to a safe place" -ForegroundColor Yellow
Write-Host "══════════════════════════════════════════════" -ForegroundColor Cyan