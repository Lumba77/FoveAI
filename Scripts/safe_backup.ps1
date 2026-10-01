<#
.SYNOPSIS
    FoveAI Safe Backup — saves source code to F: drive, skipping heavy build artifacts.
    If C: drive dies, your work is safe on F:.

.DESCRIPTION
    This script copies the FoveAI project to F:\FoveAI_backup, excluding:
    - .venv/ (Python virtual envs — can be recreated)
    - node_modules/ (can be reinstalled)
    - unsloth_compiled_cache/ (ML cache)
    - .git/ (repository metadata)
    - __pycache__/ (Python bytecode)
    - .pytest_cache/
    - backups/ (nested backups)
    - .SafeSave/ (editor crash recovery — saved separately)
    - .SafeSaves/
    - large binary/model files (*.bin, *.gguf, *.safetensors, *.pt, *.pth)
    
    HOW TO USE:
    1. Double-click this file (or right-click → Run with PowerShell)
    2. Wait for "BACKUP COMPLETE" message
    3. That's it. Your work is now on F: drive.

    TO RESTORE AFTER DISASTER:
    1. Open F:\FoveAI_backup
    2. Double-click RESTORE_ME.ps1
    3. Everything comes back

    Author: Papillon
    Version: 2.0 (smart exclusions)
#>

$ErrorActionPreference = "Stop"

# ─── Where things are ──────────────────────────────────────────────────
$SourceDir = "C:\Users\danie\program\LUMAX"
$BackupDir = "F:\FoveAI_backup"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# ─── Banner ────────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "║           🔒 FoveAI SAFE BACKUP — TO F: DRIVE            ║" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  This will copy your source code to F: drive."
Write-Host "  Heavy directories (.venv, node_modules, ML caches) are SKIPPED."
Write-Host "  If C: drive ever dies, everything is safe on F:."
Write-Host ""

# ─── Check F: drive ────────────────────────────────────────────────────
if (-not (Test-Path "F:\")) {
    Write-Host "  ❌ F: drive is not available!" -ForegroundColor Red
    Write-Host "  Please insert your backup drive and make sure it's F:"
    Write-Host ""
    pause
    exit 1
}

Write-Host "  ✅ F: drive detected" -ForegroundColor Green

# ─── Check source ──────────────────────────────────────────────────────
if (-not (Test-Path $SourceDir)) {
    Write-Host "  ❌ Source folder not found: $SourceDir" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "  ✅ Source folder found" -ForegroundColor Green
Write-Host ""

# ─── Step 1: Save SafeSave files first ──────────────────────────────────
Write-Host "─── Step 1: Saving SafeSave files (editor crash recovery) ───" -ForegroundColor Yellow

$safeSaveDir = Join-Path $SourceDir ".SafeSave"
if (Test-Path $safeSaveDir) {
    $safeFiles = Get-ChildItem -Path $safeSaveDir -Recurse -File
    Write-Host "  Found $($safeFiles.Count) SafeSave files" -ForegroundColor White
    foreach ($f in $safeFiles) {
        Write-Host "    📄 $($f.Name) ($('{0:N0}' -f ($f.Length / 1KB)) KB)" -ForegroundColor Gray
    }
} else {
    Write-Host "  No SafeSave files found" -ForegroundColor Gray
}

# ─── Step 2: Copy to F: drive (with exclusions) ──────────────────────
Write-Host ""
Write-Host "─── Step 2: Copying to F: drive (smart exclusions) ───" -ForegroundColor Yellow
Write-Host ""

# Remove old backup if exists
if (Test-Path $BackupDir) {
    Write-Host "  Removing old backup..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $BackupDir
}

Write-Host "  Copying files... (this may take a few minutes)" -ForegroundColor White

# Use robocopy with exclusion file
$excludeFile = Join-Path $env:TEMP "foveai_backup_exclude.txt"
@"
.venv\
node_modules\
unsloth_compiled_cache\
__pycache__\
.pytest_cache\
.git\
backups\
.SafeSave\
.SafeSaves\
*.bin
*.gguf
*.safetensors
*.pt
*.pth
*.ckpt
*.onnx
*.npy
*.npz
*.zip
*.tar.gz
*.tar
*.7z
*.rar
*.whl
*.exe
*.dll
*.so
*.dylib
*.pdb
*.o
*.a
*.lib
*.pyc
*.pyo
*.pyd
*.egg-info\
*.eggs\
*.ipynb_checkpoints\
"@ | Out-File -FilePath $excludeFile -Encoding utf8

$robocopyArgs = @(
    $SourceDir,
    $BackupDir,
    "/MIR",           # Mirror (copies everything, deletes what's not in source)
    "/R:2",           # Retry 2 times on failure
    "/W:2",           # Wait 2 seconds between retries
    "/NDL",           # No directory logging (cleaner output)
    "/NFL",           # No file logging
    "/NJH",           # No job header
    "/NJS",           # No job summary
    "/XF",            # Exclude these file patterns
        "*.bin", "*.gguf", "*.safetensors", "*.pt", "*.pth",
        "*.ckpt", "*.onnx", "*.npy", "*.npz",
        "*.zip", "*.tar.gz", "*.tar", "*.7z", "*.rar", "*.whl",
        "*.exe", "*.dll", "*.so", "*.dylib",
        "*.pdb", "*.o", "*.a", "*.lib",
        "*.pyc", "*.pyo", "*.pyd",
    "/XD",            # Exclude these directories
        ".venv", "node_modules", "unsloth_compiled_cache",
        "__pycache__", ".pytest_cache", ".git",
        "backups", ".SafeSave", ".SafeSaves",
        "egg-info", "eggs", ".ipynb_checkpoints"
)

$proc = Start-Process -FilePath "robocopy.exe" -ArgumentList $robocopyArgs -Wait -PassThru -NoNewWindow

# Clean up temp exclude file
Remove-Item -Force $excludeFile -ErrorAction SilentlyContinue

if ($proc.ExitCode -ge 8) {
    Write-Host "  ⚠ Some files may have failed. Check the log:" -ForegroundColor Yellow
} else {
    Write-Host "  ✅ Source files copied successfully" -ForegroundColor Green
}

# ─── Step 3: Create restore instructions ───────────────────────────────
Write-Host ""
Write-Host "─── Step 3: Creating restore instructions ───" -ForegroundColor Yellow

$restoreScript = @"
<#
.SYNOPSIS
    RESTORE FoveAI — copies everything back from F: drive.
    Run this if C: drive died or you need to recover.

    HOW TO USE:
    Double-click this file. That's it.

    Author: Papillon
#>

`$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "║        🔄 FoveAI RESTORE — FROM F: DRIVE BACKUP          ║" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

`$BackupDir = "F:\FoveAI_backup"
`$RestoreDir = "C:\Users\danie\program\LUMAX"

# Check backup exists
if (-not (Test-Path `$BackupDir)) {
    Write-Host "  ❌ Backup not found on F: drive!" -ForegroundColor Red
    Write-Host "  Expected: `$BackupDir" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "  ✅ Backup found on F: drive" -ForegroundColor Green
Write-Host ""

# Create restore directory if needed
if (-not (Test-Path `$RestoreDir)) {
    New-Item -ItemType Directory -Path `$RestoreDir -Force | Out-Null
}

Write-Host "  Restoring to: `$RestoreDir" -ForegroundColor White
Write-Host "  Copying files... (this may take a minute)" -ForegroundColor White

`$robocopyArgs = @(
    `$BackupDir,
    `$RestoreDir,
    "/MIR",
    "/R:2",
    "/W:2",
    "/NDL",
    "/NFL",
    "/NJH",
    "/NJS"
)

`$proc = Start-Process -FilePath "robocopy.exe" -ArgumentList `$robocopyArgs -Wait -PassThru -NoNewWindow

if (`$proc.ExitCode -ge 8) {
    Write-Host "  ⚠ Some files may have failed." -ForegroundColor Yellow
} else {
    Write-Host "  ✅ All files restored successfully" -ForegroundColor Green
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "║        ✅ RESTORE COMPLETE — YOUR PROJECT IS BACK        ║" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Your project is restored to: `$RestoreDir" -ForegroundColor Green
Write-Host "  You can now open it in VS Code." -ForegroundColor Green
Write-Host ""
pause
"@

$restorePath = Join-Path $BackupDir "RESTORE_ME.ps1"
$restoreScript | Out-File -FilePath $restorePath -Encoding utf8
Write-Host "  ✅ Restore script created: $restorePath" -ForegroundColor Green

# ─── Step 4: Create backup info file ───────────────────────────────────
$infoPath = Join-Path $BackupDir "backup_info.txt"
@"
FoveAI BACKUP INFORMATION
=======================
Backup date: $Timestamp
Source:      $SourceDir
Backup to:   $BackupDir

WHAT'S BACKED UP:
- All source code (Forge/, Frontend/, Backend/, etc.)
- All scripts and tools
- Documentation and plans
- Configuration files

WHAT'S EXCLUDED (recreatable):
- .venv/ (Python virtual environments)
- node_modules/ (npm packages)
- unsloth_compiled_cache/ (ML compilation cache)
- __pycache__/ (Python bytecode)
- .git/ (repository metadata)
- Large model files (*.bin, *.gguf, *.safetensors, *.pt, *.pth)
- Archives (*.zip, *.tar.gz, *.7z, *.rar)
- Compiled binaries (*.exe, *.dll, *.so)

HOW TO RESTORE:
1. Open F:\FoveAI_backup
2. Double-click RESTORE_ME.ps1
3. Everything comes back to C:\Users\danie\program\LUMAX

IF F: DRIVE ALSO DIES:
The project is also on GitHub:
  https://github.com/Lumba77/foveai.git
  
To restore from GitHub:
  git clone https://github.com/Lumba77/lumax.git C:\Users\danie\program\LUMAX

"@ | Out-File -FilePath $infoPath -Encoding utf8

# ─── Done ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "║        ✅ BACKUP COMPLETE — YOUR WORK IS SAFE           ║" -ForegroundColor Cyan
Write-Host "║                                                          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  📂 Backup location: $BackupDir" -ForegroundColor Green
Write-Host ""
Write-Host "  What to do now:" -ForegroundColor White
Write-Host "  1. Open F:\FoveAI_backup in File Explorer" -ForegroundColor Gray
Write-Host "  2. You'll see RESTORE_ME.ps1 there" -ForegroundColor Gray
Write-Host "  3. That's your emergency recovery file" -ForegroundColor Gray
Write-Host ""
Write-Host "  If C: drive ever dies:" -ForegroundColor Yellow
Write-Host "  1. Open F:\FoveAI_backup" -ForegroundColor Yellow
Write-Host "  2. Double-click RESTORE_ME.ps1" -ForegroundColor Yellow
Write-Host "  3. Everything comes back" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To run this backup again later:" -ForegroundColor White
Write-Host "  Just double-click safe_backup.ps1 again" -ForegroundColor Gray
Write-Host "  (it's in C:\Users\danie\program\LUMAX\Scripts\)" -ForegroundColor Gray
Write-Host ""
pause