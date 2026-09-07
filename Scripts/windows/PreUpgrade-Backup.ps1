# FoveAI Full Project Safety Sweep
# Run this before the Windows Registry / Upgrade hack!

$BackupDir = "C:\FoveAI_Safety_Backup_$(Get-Date -Format 'yyyyMMdd')"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

Write-Host "--- FoveAI FULL SAFETY BACKUP ---" -ForegroundColor Cyan
Write-Host "Target: $BackupDir"

# 1. Critical Configs & Keys
Write-Host "Backing up configs..." -ForegroundColor Yellow
$FilesToBackUp = @(".env", ".env.wsl2", "foveai_network_config.json", "chatterbox_api.json")
foreach ($f in $FilesToBackUp) {
    if (Test-Path $f) { Copy-Item $f -Destination $BackupDir -Force }
}

# 2. Cognee Knowledge Graph (The Memory)
if (Test-Path ".cognee_data") {
    Write-Host "Backing up Cognee Knowledge Graph..." -ForegroundColor Yellow
    Copy-Item ".cognee_data" -Destination $BackupDir -Recurse -Force
}

# 3. Source Code Sweep
# Grabs all scripts and project logic, excludes large binaries/venvs
Write-Host "Backing up source code (py, js, ts, gd, md, ps1, sh)..." -ForegroundColor Yellow
$IncludeList = @("*.py", "*.js", "*.ts", "*.tsx", "*.html", "*.css", "*.gd", "*.md", "*.ps1", "*.sh", "*.json", "*.txt")
$ExcludeList = @(".venv", ".logs", ".git", "models", "Build", "trash", "user_data")

Get-ChildItem -Path "." -Recurse -Include $IncludeList | Where-Object { 
    $path = $_.FullName
    $shouldExclude = $false
    foreach ($ex in $ExcludeList) {
        if ($path -like "*\$ex\*") { $shouldExclude = $true; break }
    }
    -not $shouldExclude
} | ForEach-Object {
    $relative = $_.FullName.Replace((Get-Location).Path + "\", "")
    $dest = Join-Path $BackupDir $relative
    $destDir = Split-Path $dest
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Copy-Item $_.FullName -Destination $dest -Force
}

Write-Host "`n=== BACKUP COMPLETE ===" -ForegroundColor Green
Write-Host "1. Move the folder '$BackupDir' to a USB DRIVE or SECONDARY DISK now."
Write-Host "2. Once it is safely OFF your C: drive, you can start the Windows install."
Write-Host "3. If the drive is wiped, you can restore everything from this backup."
