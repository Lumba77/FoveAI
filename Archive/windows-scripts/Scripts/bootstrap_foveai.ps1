<#
.SYNOPSIS
    FoveAI Bootstrap — Restores everything after total disk loss.
    This is the Phoenix Protocol seed. Keep this file on a USB drive.

.DESCRIPTION
    After total disk loss, this script rebuilds the entire FoveAI environment:
    1. Verifies Node.js is installed
    2. Clones the repo from GitHub
    3. Verifies all critical tools work
    4. Prints a recovery report

    This script is intentionally SELF-CONTAINED — no dependencies beyond:
    - Node.js (winget install OpenJS.NodeJS)
    - Git (included with Windows, or winget install Git.Git)
    - Internet access

.PARAMETER RepoDir
    Where to clone the repo (default: current directory)

.PARAMETER SkipClone
    Skip git clone (if repo already exists)

.EXAMPLE
    # Full bootstrap from scratch
    powershell -NoExecutionPolicy -File bootstrap_foveai.ps1

    # Bootstrap to specific directory
    powershell -NoExecutionPolicy -File bootstrap_foveai.ps1 -RepoDir "D:\Projects\FoveAI"

.NOTES
    Author: Papillon / Roux Code
    Version: 1.0.0
    This is the ONLY file you need to keep safe.
#>

param(
    [string] $RepoDir = "",
    [switch] $SkipClone
)

$ErrorActionPreference = "Stop"

# ─── Configuration ─────────────────────────────────────────────────────
$GitHubRepo = "https://github.com/Lumba77/foveai.git"
$RequiredNodeVersion = "18.0.0"

# ─── Banner ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                              ║" -ForegroundColor Cyan
Write-Host "║     🔥 FoveAI PHOENIX PROTOCOL — BOOTSTRAP FROM ASHES        ║" -ForegroundColor Cyan
Write-Host "║                                                              ║" -ForegroundColor Cyan
Write-Host "║     This script rebuilds the entire FoveAI environment        ║" -ForegroundColor Cyan
Write-Host "║     after total disk loss. You only need this one file.      ║" -ForegroundColor Cyan
Write-Host "║                                                              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ─── Step 1: Check prerequisites ───────────────────────────────────────
Write-Host "─── Step 1/5: Checking prerequisites ───" -ForegroundColor Yellow
Write-Host ""

# Check Node.js
try {
    $nodeVersion = node --version
    Write-Host "  ✓ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Node.js is NOT installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Install it first:" -ForegroundColor White
    Write-Host "    winget install OpenJS.NodeJS" -ForegroundColor Gray
    Write-Host "  Or download from: https://nodejs.org/" -ForegroundColor Gray
    Write-Host ""
    $choice = Read-Host "  Press Enter after installing Node.js, or type 'exit' to abort"
    if ($choice -eq "exit") { exit 1 }
    
    # Retry
    try {
        $nodeVersion = node --version
        Write-Host "  ✓ Node.js: $nodeVersion" -ForegroundColor Green
    } catch {
        Write-Error "Node.js still not found. Please install it manually."
    }
}

# Check Git
try {
    $gitVersion = git --version
    Write-Host "  ✓ Git: $gitVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Git is NOT installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Install it first:" -ForegroundColor White
    Write-Host "    winget install Git.Git" -ForegroundColor Gray
    Write-Host ""
    $choice = Read-Host "  Press Enter after installing Git, or type 'exit' to abort"
    if ($choice -eq "exit") { exit 1 }
    
    try {
        $gitVersion = git --version
        Write-Host "  ✓ Git: $gitVersion" -ForegroundColor Green
    } catch {
        Write-Error "Git still not found. Please install it manually."
    }
}

# ─── Step 2: Clone repo ────────────────────────────────────────────────
Write-Host ""
Write-Host "─── Step 2/5: Cloning repository ───" -ForegroundColor Yellow
Write-Host ""

if (-not $RepoDir) {
    $RepoDir = Join-Path (Get-Location) "FoveAI"
}

if ($SkipClone) {
    Write-Host "  → Skipping clone (--SkipClone specified)" -ForegroundColor Yellow
    if (-not (Test-Path $RepoDir)) {
        Write-Error "Repo directory does not exist: $RepoDir"
    }
    Write-Host "  ✓ Using existing: $RepoDir" -ForegroundColor Green
} else {
    if (Test-Path $RepoDir) {
        Write-Host "  ⚠ Directory already exists: $RepoDir" -ForegroundColor Yellow
        $choice = Read-Host "  Overwrite? (y/N)"
        if ($choice -ne "y") {
            Write-Host "  → Using existing directory" -ForegroundColor Yellow
        } else {
            Remove-Item -Recurse -Force $RepoDir
        }
    }
    
    if (-not (Test-Path $RepoDir)) {
        Write-Host "  → Cloning from $GitHubRepo ..." -ForegroundColor Yellow
        git clone $GitHubRepo $RepoDir 2>&1 | ForEach-Object { Write-Host "    $_" }
        Write-Host "  ✓ Repository cloned" -ForegroundColor Green
    }
}

Set-Location $RepoDir
Write-Host "  ✓ Working directory: $RepoDir" -ForegroundColor Green

# ─── Step 3: Verify critical files ──────────────────────────────────────
Write-Host ""
Write-Host "─── Step 3/5: Verifying critical files ───" -ForegroundColor Yellow
Write-Host ""

$criticalFiles = @(
    @{ Path = "Forge/xrs/xrs.cjs"; Name = "XRS CLI Wrapper" },
    @{ Path = "Forge/xrs/xrs-tokens.cjs"; Name = "XRS Token Counter" },
    @{ Path = "Forge/xrs/xrl-prompt.md"; Name = "XRL Prompt Template" },
    @{ Path = "Forge/xrs/xrl-benchmark.cjs"; Name = "XRL Benchmark" },
    @{ Path = "Forge/xrs/xrl-poc-results.md"; Name = "XRL PoC Results" },
    @{ Path = "Forge/scratch/TokenSlayer/standalone/tokenslayer.js"; Name = "TokenSlayer" },
    @{ Path = "Plans/xrl-language-design.md"; Name = "XRL Language Design" },
    @{ Path = "Plans/xrl-proof-of-concept.md"; Name = "XRL PoC Plan" },
    @{ Path = "Scripts/disaster_backup.ps1"; Name = "Disaster Backup" },
    @{ Path = "Scripts/bootstrap_foveai.ps1"; Name = "Bootstrap (this file)" }
)

$allFilesOk = $true
foreach ($file in $criticalFiles) {
    $fullPath = Join-Path $RepoDir $file.Path
    if (Test-Path $fullPath) {
        $size = (Get-Item $fullPath).Length
        Write-Host "  ✓ $($file.Name): $($file.Path) ($size bytes)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $($file.Name): MISSING — $($file.Path)" -ForegroundColor Red
        $allFilesOk = $false
    }
}

# ─── Step 4: Test critical tools ──────────────────────────────────────
Write-Host ""
Write-Host "─── Step 4/5: Testing critical tools ───" -ForegroundColor Yellow
Write-Host ""

# Test xrs.cjs
try {
    $xrsResult = node "Forge/xrs/xrs.cjs" "Forge/xrs/xrs.cjs" --depth 2 --stats 2>&1
    $xrsStats = $xrsResult | ConvertFrom-Json
    Write-Host "  ✓ XRS CLI: $($xrsStats.reduction) reduction on itself" -ForegroundColor Green
} catch {
    Write-Host "  ✗ XRS CLI test failed: $_" -ForegroundColor Red
    $allFilesOk = $false
}

# Test xrs-tokens.cjs
try {
    $tokensResult = node "Forge/xrs/xrs-tokens.cjs" "Forge/xrs/xrs.cjs" --depth 2 --json 2>&1
    $tokensStats = $tokensResult | ConvertFrom-Json
    Write-Host "  ✓ XRS Token Counter: $($tokensStats.summary.totalReduction) across $($tokensStats.summary.totalFiles) files" -ForegroundColor Green
} catch {
    Write-Host "  ✗ XRS Token Counter test failed: $_" -ForegroundColor Red
    $allFilesOk = $false
}

# Test xrl-benchmark.cjs
try {
    $benchResult = node "Forge/xrs/xrl-benchmark.cjs" "Forge/xrs/xrs.cjs" --depth 2 --json 2>&1
    $benchStats = $benchResult | ConvertFrom-Json
    Write-Host "  ✓ XRL Benchmark: $($benchStats.summary.totalTests) test cases generated" -ForegroundColor Green
} catch {
    Write-Host "  ✗ XRL Benchmark test failed: $_" -ForegroundColor Red
    $allFilesOk = $false
}

# Test TokenSlayer
try {
    $tsResult = node "Forge/scratch/TokenSlayer/standalone/tokenslayer.js" "Forge/scratch/TokenSlayer/standalone/tokenslayer.js" --level 2 2>&1
    if ($tsResult -match "TokenSlayer Saved") {
        Write-Host "  ✓ TokenSlayer: skeletonization works" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ TokenSlayer test failed: $_" -ForegroundColor Red
    $allFilesOk = $false
}

# ─── Step 5: Recovery report ───────────────────────────────────────────
Write-Host ""
Write-Host "─── Step 5/5: Recovery report ───" -ForegroundColor Yellow
Write-Host ""

$totalSize = 0
$totalFiles = 0
Get-ChildItem -Recurse -File $RepoDir | ForEach-Object { 
    $totalSize += $_.Length
    $totalFiles++
}

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                              ║" -ForegroundColor Cyan
Write-Host "║     🔥 FoveAI PHOENIX PROTOCOL — RECOVERY COMPLETE            ║" -ForegroundColor Cyan
Write-Host "║                                                              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Repository: $RepoDir" -ForegroundColor White
Write-Host "  Total files: $totalFiles" -ForegroundColor White
Write-Host "  Total size:  $('{0:N2}' -f ($totalSize / 1MB)) MB" -ForegroundColor White
Write-Host ""

if ($allFilesOk) {
    Write-Host "  ✅ ALL SYSTEMS NOMINAL" -ForegroundColor Green
    Write-Host "  All critical files verified and tools tested." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Quick start commands:" -ForegroundColor White
    Write-Host "    # Measure token reduction on any file" -ForegroundColor Gray
    Write-Host "    node Forge/xrs/xrs.cjs <filepath> --depth 2" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    # Scan multiple files" -ForegroundColor Gray
    Write-Host "    node Forge/xrs/xrs-tokens.cjs <file1> <file2> --depth 2" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    # Generate benchmark prompts" -ForegroundColor Gray
    Write-Host "    node Forge/xrs/xrl-benchmark.cjs <filepath> --depth 2" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    # Run daily backup" -ForegroundColor Gray
    Write-Host "    powershell -NoProfile -ExecutionPolicy Bypass -File Scripts/disaster_backup.ps1" -ForegroundColor Gray
} else {
    Write-Host "  ⚠ SOME CHECKS FAILED" -ForegroundColor Yellow
    Write-Host "  Review the errors above and fix them manually." -ForegroundColor Yellow
    Write-Host "  Then run this script again to verify." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  📌 Store this bootstrap script on:" -ForegroundColor White
Write-Host "     • A USB drive" -ForegroundColor Gray
Write-Host "     • Cloud storage (Google Drive, Dropbox)" -ForegroundColor Gray
Write-Host "     • Printed as QR code (for extreme cases)" -ForegroundColor Gray
Write-Host ""
Write-Host "  🔗 GitHub: https://github.com/Lumba77/foveai.git" -ForegroundColor Cyan
Write-Host ""