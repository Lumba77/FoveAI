# LUMAX Sovereign Backup — Git-substitute version control via zip snapshots
# Called by backup.cmd — all logic lives here to avoid CMD/PowerShell escaping issues.
#
# Usage:
#   .\backup.cmd                          Create snapshot (auto-message)
#   .\backup.cmd commit "message"         Create snapshot with message
#   .\backup.cmd log                       List all snapshots
#   .\backup.cmd status                    Show changed files since last snapshot
#   .\backup.cmd diff [path_filter]        Show content diff of changed files
#   .\backup.cmd restore <snapshot_id>     Restore files from a specific snapshot
#   .\backup.cmd init                      Initialize the backup repository
#   .\backup.cmd help                      Show this help text

param(
    [Parameter(Position=0)]
    [string]$Command = 'commit',
    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArgs = @()
)

$BackupDir = 'backups'
$ManifestFile = Join-Path $BackupDir 'manifest.json'
$FileIndex = Join-Path $BackupDir '.file_index.txt'

$ExcludePatterns = @(
    '.git', '.venv', '.aider-venv', 'node_modules', '__pycache__',
    '.logs', 'Build', 'backups', 'archive', '.cache', '*.pyc', '.env',
    'webvm_source\node_modules', 'webvm_source\build', 'Library', 'Temp', 'Logs',
    # Windows reserved device names that cause open errors
    'nul', 'nulcmd',
    # External clones / caches with thousands of non-project files
    '.github', 'unsloth_compiled_cache', 'webvm_source',
    # Massive binary assets and datasets
    'Animations\BVH', 'Bandai-Namco', '*.gguf', '*.pak', '*.bin', '*.safetensors'
)

$BinaryExtensions = @(
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.wav', '.mp3', '.ogg',
    '.webm', '.mp4', '.zip', '.gz', '.tar', '.exe', '.dll', '.pdb', '.obj',
    '.bin', '.wasm', '.db', '.sqlite', '.glb', '.vrm'
)

# Core patterns for --core flag (essential files only, ~1 min backup)
# Includes all crucial source code file types that could be corrupted/overwritten.
$CoreIncludePatterns = @(
    # Documentation & config
    '*.md', '*.yml', '*.yaml', '*.json', '*.cmd', '*.ps1', '*.txt',
    '*.xml', '*.toml', '*.cfg', '*.ini', '*.sh', '*.bat',
    # Source code (all languages used in LUMAX)
    '*.py', '*.ts', '*.js', '*.gd', '*.cs', '*.html', '*.css',
    # Key directories (ensure full coverage of critical code)
    'backend\*', 'Forge\*', 'Frontend\XR_Vessel\xr_app.py', 'Frontend\XR_Vessel\src\*',
    'Frontend\Unity\lumax\Assets\Scripts\*', 'Frontend\Mouth\*', 'Frontend\Physical_Interface\*',
    'Frontend\Agency\*', 'Frontend\ConsentBridge\*', 'Frontend\ChromeExtension\*',
    'Scripts\*', 'Service\*', 'Tools\lumax_top_bar\*', 'requirements\*',
    'Frontend\*', 'Dev\*'
)

function Get-Files-Recurse {
    param([string]$Path)

    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    $dirsToScan = [System.Collections.Generic.Queue[string]]::new()
    $dirsToScan.Enqueue($Path)

    while ($dirsToScan.Count -gt 0) {
        $current = $dirsToScan.Dequeue()
        try {
            $dirInfo = [System.IO.DirectoryInfo]::new($current)
            
            # Get files in current directory
            foreach ($file in $dirInfo.GetFiles()) {
                $skip = $false
                foreach ($e in $ExcludePatterns) {
                    if ($file.FullName -like "*$e*") { $skip = $true; break }
                }
                if (-not $skip) {
                    $files.Add($file)
                }
            }

            # Get subdirectories
            foreach ($subDir in $dirInfo.GetDirectories()) {
                $skip = $false
                foreach ($e in $ExcludePatterns) {
                    if ($subDir.FullName -like "*$e*") { $skip = $true; break }
                }
                if (-not $skip) {
                    $dirsToScan.Enqueue($subDir.FullName)
                }
            }
        } catch {
            # Skip errors
        }
    }
    return $files
}

function Get-CoreFiles {
    param([string]$SourcePath)

    $all = Get-Files-Recurse -Path $SourcePath
    $all | Where-Object {
        $rel = $_.FullName.Substring($SourcePath.Length + 1)
        foreach ($p in $CoreIncludePatterns) {
            if ($rel -like $p) { return $true }
        }
        $false
    }
}

function Get-ExcludedFiles {
    param([string]$SourcePath)

    Get-Files-Recurse -Path $SourcePath
}


# ============================================================
#  INIT
# ============================================================
function Do-Init {
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }

    if (-not (Test-Path $ManifestFile)) {
        '[]' | Set-Content $ManifestFile -Encoding UTF8
        Write-Host "[OK] Backup repository initialized — $ManifestFile created"
    } else {
        Write-Host "[OK] Backup repository already exists"
    }

    Write-Host ""
    Write-Host 'Next: Run .\backup.cmd commit "initial snapshot" to create your first snapshot.'
}

# ============================================================
#  COMMIT
# ============================================================
function Do-Commit {
    param([string]$Msg, [switch]$CoreOnly)

    if (-not (Test-Path $BackupDir)) {
        Write-Host "[WARN] Backup repository not found — initializing..."
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
        '[]' | Set-Content $ManifestFile -Encoding UTF8
    }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $zipName = "lumax_backup_$timestamp.zip"

    if (-not $Msg) {
        $Msg = "snapshot $timestamp"
    }

    Write-Host "============================================"
    Write-Host "  LUMAX Sovereign Backup — Commit"
    Write-Host "============================================"
    Write-Host ""
    Write-Host "Snapshot: $timestamp"
    Write-Host "Message:  $Msg"
    if ($CoreOnly) { Write-Host "Mode:     CORE (essential files only)" -ForegroundColor Yellow }
    Write-Host ""

    $src = (Get-Location).Path
    $dst = Join-Path $src "$BackupDir\$zipName"

    $files = if ($CoreOnly) { @(Get-CoreFiles -SourcePath $src) } else { @(Get-ExcludedFiles -SourcePath $src) }

    if ($files.Count -eq 0) {
        Write-Host '[ERROR] No files to backup!'
        return
    }

    if (Test-Path $dst) { Remove-Item $dst -Force }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::Open($dst, [System.IO.Compression.ZipArchiveMode]::Create)

    foreach ($f in $files) {
        $w = $null
        $r = $null
        try {
            $rel = $f.FullName.Substring($src.Length + 1).Replace('\', '/')
            $entry = $zip.CreateEntry($rel, [System.IO.Compression.CompressionLevel]::Optimal)
            if ($null -eq $entry) {
                Write-Host "[WARN] Could not create zip entry for: $rel" -ForegroundColor Yellow
                continue
            }
            $w = $entry.Open()
            if ($null -eq $w) {
                Write-Host "[WARN] Could not open zip entry for: $rel" -ForegroundColor Yellow
                continue
            }
            try {
                $r = [System.IO.File]::OpenRead($f.FullName)
            } catch {
                Write-Host "[WARN] Could not open file: $rel — $($_.Exception.Message)" -ForegroundColor Yellow
                continue
            }
            if ($null -eq $r) {
                Write-Host "[WARN] Could not read file: $rel" -ForegroundColor Yellow
                continue
            }
            $r.CopyTo($w)
        } catch {
            Write-Host "[WARN] Skipped file due to error: $rel — $($_.Exception.Message)" -ForegroundColor Yellow
        } finally {
            if ($r) { try { $r.Close() } catch {} }
            if ($w) { try { $w.Close() } catch {} }
        }
    }

    $zip.Dispose()

    $size = 0
    if (Test-Path $dst) {
        $dstItem = Get-Item $dst -ErrorAction SilentlyContinue
        if ($dstItem -and $dstItem.Length) {
            $size = [math]::Round($dstItem.Length / 1MB, 1)
        }
    }
    $fileCount = $files.Count

    Write-Host "[OK] Snapshot: $zipName ($size MB, $fileCount files)"

    # Update manifest
    $m = @()
    if (Test-Path $ManifestFile) {
        try {
            $m = @(Get-Content $ManifestFile -Raw | ConvertFrom-Json)
        } catch {
            $m = @()
        }
    }

    $entry = @{
        id        = $timestamp
        zip       = $zipName
        message   = $Msg
        timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
        file_count = $fileCount
        size_mb   = $size
    }

    $m += $entry
    $m | ConvertTo-Json -Depth 10 | Set-Content $ManifestFile -Encoding UTF8

    # Update file index
    $indexLines = $files | ForEach-Object {
        $rl = $_.FullName.Substring($src.Length + 1)
        $sz = $_.Length
        $md = $_.LastWriteTime.ToString('o')
        "$rl`t$sz`t$md"
    }
    $indexLines | Set-Content $FileIndex -Encoding UTF8

    Write-Host '[OK] Manifest and file index updated'
    Write-Host ""
    Write-Host "Snapshot committed successfully."
}

# ============================================================
#  LOG
# ============================================================
function Do-Log {
    if (-not (Test-Path $ManifestFile)) {
        Write-Host '[WARN] No snapshots found. Run: .\backup.cmd commit "initial"'
        return
    }

    Write-Host "============================================"
    Write-Host "  LUMAX Backup Log"
    Write-Host "============================================"
    Write-Host ""

    $m = @(Get-Content $ManifestFile -Raw | ConvertFrom-Json)
    $t = $m.Count
    [Array]::Reverse($m)

    foreach ($e in $m) {
        Write-Host ('{0,-20} {1,6} files  {2,7} MB  {3}' -f $e.id, $e.file_count, $e.size_mb, $e.message)
    }

    Write-Host ""
    Write-Host "Total: $t snapshots"
}

# ============================================================
#  STATUS
# ============================================================
function Do-Status {
    if (-not (Test-Path $FileIndex)) {
        Write-Host '[WARN] No file index found. Run: .\backup.cmd commit "initial" first.'
        return
    }

    Write-Host "============================================"
    Write-Host "  LUMAX Backup Status"
    Write-Host "============================================"
    Write-Host ""

    $src = (Get-Location).Path

    # Build index from file_index.txt
    $idx = @{}
    Get-Content $FileIndex -Encoding UTF8 | ForEach-Object {
        $p = $_ -split "`t"
        if ($p.Count -ge 3) {
            $idx[$p[0]] = @{ s = [long]$p[1]; m = $p[2] }
        }
    }

    # Get current files
    $cf = @(Get-ExcludedFiles -SourcePath $src)

    $added = [System.Collections.ArrayList]::new()
    $modified = [System.Collections.ArrayList]::new()
    $unchanged = 0

    foreach ($f in $cf) {
        $rel = $f.FullName.Substring($src.Length + 1)
        if ($idx.ContainsKey($rel)) {
            $iv = $idx[$rel]
            if ($f.Length -ne $iv.s -or $f.LastWriteTime.ToString('o') -ne $iv.m) {
                $modified.Add($rel) | Out-Null
            } else {
                $unchanged++
            }
        } else {
            $added.Add($rel) | Out-Null
        }
    }

    $deleted = [System.Collections.ArrayList]::new()
    foreach ($k in $idx.Keys) {
        if (-not (Test-Path (Join-Path $src $k))) {
            $deleted.Add($k) | Out-Null
        }
    }

    $changes = $added.Count + $modified.Count + $deleted.Count

    if ($changes -eq 0) {
        Write-Host 'Nothing to snapshot — working tree clean.' -ForegroundColor Green
    } else {
        if ($added.Count -gt 0) {
            Write-Host ""
            Write-Host "NEW ($($added.Count)):" -ForegroundColor Cyan
            $added | Sort-Object | ForEach-Object { Write-Host "  + $_" -ForegroundColor Green }
        }
        if ($modified.Count -gt 0) {
            Write-Host ""
            Write-Host "MODIFIED ($($modified.Count)):" -ForegroundColor Cyan
            $modified | Sort-Object | ForEach-Object { Write-Host "  ~ $_" -ForegroundColor Yellow }
        }
        if ($deleted.Count -gt 0) {
            Write-Host ""
            Write-Host "DELETED ($($deleted.Count)):" -ForegroundColor Cyan
            $deleted | Sort-Object | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
        }
        Write-Host ""
        Write-Host "Summary: $unchanged unchanged, $($added.Count) new, $($modified.Count) modified, $($deleted.Count) deleted"
    }
}

# ============================================================
#  DIFF
# ============================================================
function Do-Diff {
    param([string]$PathFilter = '')

    if (-not (Test-Path $FileIndex)) {
        Write-Host '[WARN] No file index found. Run: .\backup.cmd commit "initial" first.'
        return
    }

    Write-Host "============================================"
    Write-Host "  LUMAX Backup Diff"
    Write-Host "============================================"
    Write-Host ""

    $src = (Get-Location).Path

    # Get latest snapshot
    $m = @(Get-Content $ManifestFile -Raw | ConvertFrom-Json)
    $lt = $m[-1]
    $zp = Join-Path $src "$BackupDir\$($lt.zip)"

    if (-not (Test-Path $zp)) {
        Write-Host '[ERROR] Zip not found'
        return
    }

    Write-Host "Against: $($lt.id) ($($lt.message))" -ForegroundColor Cyan

    # Extract to temp
    $td = Join-Path $env:TEMP "lumax_diff_$($lt.id)"
    if (Test-Path $td) { Remove-Item $td -Recurse -Force }
    Expand-Archive -Path $zp -DestinationPath $td -Force

    # Build index
    $idx = @{}
    Get-Content $FileIndex -Encoding UTF8 | ForEach-Object {
        $p = $_ -split "`t"
        if ($p.Count -ge 3) {
            $idx[$p[0]] = @{ s = [long]$p[1]; m = $p[2] }
        }
    }

    # Get current files
    $cf = @(Get-ExcludedFiles -SourcePath $src)

    $diffCount = 0

    foreach ($f in $cf) {
        $rel = $f.FullName.Substring($src.Length + 1)

        if ($PathFilter -and $rel -notlike "*$PathFilter*") { continue }

        $isModified = $false
        if ($idx.ContainsKey($rel)) {
            $iv = $idx[$rel]
            if ($f.Length -ne $iv.s -or $f.LastWriteTime.ToString('o') -ne $iv.m) {
                $isModified = $true
            }
        } else {
            $isModified = $true
        }

        if ($isModified) {
            $ext = [System.IO.Path]::GetExtension($rel).ToLower()
            $isBinary = $BinaryExtensions -contains $ext

            Write-Host ""
            Write-Host "--- a/$rel" -ForegroundColor Red
            Write-Host "+++ b/$rel" -ForegroundColor Green

            if ($isBinary) {
                Write-Host '  [BINARY — content diff not available]' -ForegroundColor Yellow
            } else {
                $sf = Join-Path $td ($rel.Replace('\', '/'))
                if (Test-Path $sf) {
                    try {
                        $oc = @(Get-Content $sf -Encoding UTF8 -ErrorAction Stop)
                        $nc = @(Get-Content $f.FullName -Encoding UTF8 -ErrorAction Stop)
                        Write-Host "@@ -($($oc.Count)) +($($nc.Count)) @@" -ForegroundColor Cyan
                        $mx = [math]::Max($oc.Count, $nc.Count)
                        for ($i = 0; $i -lt $mx; $i++) {
                            $ol = if ($i -lt $oc.Count) { $oc[$i] } else { $null }
                            $nl = if ($i -lt $nc.Count) { $nc[$i] } else { $null }
                            if ($ol -ne $nl) {
                                if ($null -ne $ol) { Write-Host "- $ol" -ForegroundColor Red }
                                if ($null -ne $nl) { Write-Host "+ $nl" -ForegroundColor Green }
                            }
                        }
                    } catch {
                        Write-Host '  [BINARY or unreadable]' -ForegroundColor Yellow
                    }
                } else {
                    Write-Host '  [NEW FILE]' -ForegroundColor Green
                    try {
                        $nc = @(Get-Content $f.FullName -Encoding UTF8 -ErrorAction Stop)
                        $nc | Select-Object -First 20 | ForEach-Object { Write-Host "+ $_" -ForegroundColor Green }
                        if ($nc.Count -gt 20) {
                            Write-Host "  ... ($($nc.Count - 20) more lines)" -ForegroundColor Yellow
                        }
                    } catch {
                        Write-Host '  [BINARY]' -ForegroundColor Yellow
                    }
                }
            }

            $diffCount++
        }
    }

    Remove-Item $td -Recurse -Force -ErrorAction SilentlyContinue

    if ($diffCount -eq 0) {
        Write-Host 'No differences found.' -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "$diffCount file(s) differ." -ForegroundColor Yellow
    }
}

# ============================================================
#  RESTORE
# ============================================================
function Do-Restore {
    param([string]$SnapshotId)

    if (-not $SnapshotId) {
        Write-Host '[ERROR] Specify snapshot ID. Usage: .\backup.cmd restore 20260528_143022'
        Write-Host 'Run: .\backup.cmd log  to see available snapshots.'
        return
    }

    Write-Host "============================================"
    Write-Host "  LUMAX Backup Restore"
    Write-Host "============================================"
    Write-Host ""

    $src = (Get-Location).Path

    $m = @(Get-Content $ManifestFile -Raw | ConvertFrom-Json)
    $e = $m | Where-Object { $_.id -eq $SnapshotId } | Select-Object -First 1

    if (-not $e) {
        Write-Host '[ERROR] Snapshot not found: ' -ForegroundColor Red -NoNewline
        Write-Host $SnapshotId
        return
    }

    $zp = Join-Path $src "$BackupDir\$($e.zip)"
    if (-not (Test-Path $zp)) {
        Write-Host '[ERROR] Zip not found' -ForegroundColor Red
        return
    }

    Write-Host 'Snapshot: ' -NoNewline
    Write-Host $e.id -ForegroundColor Cyan
    Write-Host 'Message:  ' -NoNewline
    Write-Host $e.message
    Write-Host 'Files:    ' -NoNewline
    Write-Host $e.file_count
    Write-Host 'Size:     ' -NoNewline
    Write-Host "$($e.size_mb) MB"
    Write-Host ""
    Write-Host 'WARNING: This will overwrite current files with snapshot contents.' -ForegroundColor Red
    Write-Host '         Files not in the snapshot will NOT be deleted.' -ForegroundColor Yellow
    Write-Host ""

    $c = Read-Host 'Type RESTORE to proceed'
    if ($c -ne 'RESTORE') {
        Write-Host 'Cancelled.'
        return
    }

    Write-Host ""
    Write-Host 'Extracting...' -ForegroundColor Cyan
    Expand-Archive -Path $zp -DestinationPath $src -Force
    Write-Host '[OK] Restored from snapshot ' -ForegroundColor Green -NoNewline
    Write-Host $SnapshotId -ForegroundColor Cyan
}

# ============================================================
#  HELP
# ============================================================
function Do-Help {
    Write-Host "============================================"
    Write-Host "  LUMAX Sovereign Backup — Git Substitute"
    Write-Host "============================================"
    Write-Host ""
    Write-Host "  .\backup.cmd                          Create snapshot (auto-message)"
    Write-Host "  .\backup.cmd commit `"message`"         Create snapshot with message"
    Write-Host "  .\backup.cmd log                       List all snapshots"
    Write-Host "  .\backup.cmd status                    Show changed files since last snapshot"
    Write-Host "  .\backup.cmd diff [path_filter]        Show content diff of changed files"
    Write-Host "  .\backup.cmd restore <snapshot_id>     Restore files from a specific snapshot"
    Write-Host "  .\backup.cmd init                      Initialize the backup repository"
    Write-Host "  .\backup.cmd help                      Show this help text"
    Write-Host ""
    Write-Host "Snapshots are timestamped zip archives stored in backups\"
    Write-Host "Metadata: backups\manifest.json  backups\.file_index.txt"
    Write-Host ""
    Write-Host "Excluded: .git .venv .aider-venv node_modules __pycache__"
    Write-Host "          .logs Build backups .cache *.pyc .env"
}

# ============================================================
#  MAIN DISPATCH
# ============================================================
$Command = if ($Command) { $Command.Trim() } else { '' }
$RemainingArgs = if ($RemainingArgs) { $RemainingArgs } else { @() }
switch ($Command.ToLower()) {
    'commit'  {
        $coreOnly = $false
        $cleanedArgs = @()
        foreach ($arg in $RemainingArgs) {
            if ($arg -eq '--core') {
                $coreOnly = $true
            } else {
                $cleanedArgs += $arg
            }
        }
        Do-Commit -Msg ($cleanedArgs -join ' ') -CoreOnly:$coreOnly
    }
    'log'     { Do-Log }
    'status'  { Do-Status }
    'diff'    { Do-Diff -PathFilter ($RemainingArgs -join ' ') }
    'restore' { Do-Restore -SnapshotId ($RemainingArgs -join ' ') }
    'init'    { Do-Init }
    'help'    { Do-Help }
    default   {
        Write-Host "[ERROR] Unknown command: $Command"
        Write-Host "Run: .\backup.cmd help"
    }
}
