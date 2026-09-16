# fix_home_permissions.ps1
# Script to repair file ownership and permission issues in the user's home directory.
# Targets standard folders to resolve access issues while protecting critical system/app files.

param (
    [Parameter(Position = 0, ValueFromPipeline = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Paths
)

$homePath = "C:\Users\danie"
$user = "danie"

# Identify the currently executing script to prevent permission changes on it during run
$scriptPath = $PSCommandPath
if (-not $scriptPath) {
    $scriptPath = $MyInvocation.MyCommand.Path
}

Write-Host "Reclaiming ownership and resetting permissions in your home folders..." -ForegroundColor Cyan
Write-Host "This targets standard directories like Desktop, Documents, Downloads, program (dev), and .gemini." -ForegroundColor Yellow
if ($scriptPath) {
    Write-Host "Active script location identified: $scriptPath" -ForegroundColor Gray
}

# Helper to determine if a path is a parent directory of the script or the script itself
function Is-Parent-Or-Self {
    param (
        [string]$Path,
        [string]$ScriptPath
    )
    if (-not $ScriptPath) { return $false }
    
    # Normalize paths
    $normPath = [System.IO.Path]::GetFullPath($Path).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
    $normScript = [System.IO.Path]::GetFullPath($ScriptPath)
    
    # Check if equal (self)
    if ($normPath -eq $normScript) {
        return $true
    }
    
    # Check if parent (script is located inside this path)
    $normPathWithSlash = $normPath + [System.IO.Path]::DirectorySeparatorChar
    if ($normScript.StartsWith($normPathWithSlash, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    
    return $false
}

# Recursive helper to process directories safely without modifying the running script's permissions
function Repair-Path-Permissions {
    param (
        [string]$Path,
        [string]$ScriptPath,
        [string]$User
    )
    
    if (Is-Parent-Or-Self -Path $Path -ScriptPath $ScriptPath) {
        # This path contains the executing script. Process it non-recursively.
        if (Test-Path -Path $Path -PathType Container) {
            Write-Host "Processing parent folder (non-recursive to avoid locking active script): $Path" -ForegroundColor Gray
            takeown /f $Path | Out-Null
            icacls $Path /grant "${User}:(OI)(CI)F" /q | Out-Null
            
            # Recurse on children individually
            $children = Get-ChildItem -Path $Path -Force -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                Repair-Path-Permissions -Path $child.FullName -ScriptPath $ScriptPath -User $User
            }
        } else {
            # Skip the script file itself to avoid losing execution handle/access
            Write-Host "Skipping active script file to preserve execution handle: $Path" -ForegroundColor Yellow
        }
    } else {
        # Safe path. Run recursively for maximum speed.
        if (Test-Path -Path $Path -PathType Container) {
            Write-Host "Processing folder recursively: $Path" -ForegroundColor Green
            
            # 1. Take ownership recursively
            takeown /f $Path /r /d y | Out-Null
            
            # 2. Grant Full Control recursively to the user
            icacls $Path /grant "${User}:(OI)(CI)F" /t /c /q | Out-Null
            
            # 3. Clear the Read-Only flag from files recursively
            Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                if ($_.IsReadOnly) {
                    $_.IsReadOnly = $false
                }
            }
        } else {
            # Single file process
            takeown /f $Path | Out-Null
            icacls $Path /grant "${User}:F" /q | Out-Null
            $fileItem = Get-Item -Path $Path -Force -ErrorAction SilentlyContinue
            if ($fileItem -and $fileItem.IsReadOnly) {
                $fileItem.IsReadOnly = $false
            }
        }
    }
}

# Folders to process recursively
$foldersToFix = @(
    "Desktop",
    "Documents",
    "Downloads",
    "Music",
    "Pictures",
    "Videos",
    "program",
    ".gemini",
    ".unsloth"
)

# If the user passed paths via command line, use those. Otherwise, use the defaults.
$targetPaths = @()
if ($Paths -and $Paths.Count -gt 0) {
    foreach ($p in $Paths) {
        # Resolve to absolute path
        $targetPaths += [System.IO.Path]::GetFullPath($p)
    }
} else {
    foreach ($folderName in $foldersToFix) {
        $targetPaths += Join-Path $homePath $folderName
    }
}

foreach ($folderPath in $targetPaths) {
    if (Test-Path $folderPath) {
        Repair-Path-Permissions -Path $folderPath -ScriptPath $scriptPath -User $user
    } else {
        Write-Host "Folder not found, skipping: $folderPath" -ForegroundColor DarkGray
    }
}

Write-Host "Permissions repair complete!" -ForegroundColor Green
