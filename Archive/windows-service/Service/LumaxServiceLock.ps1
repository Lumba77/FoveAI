# FoveAI Service Lock Manager
# Prevents multiple instances of service management from running simultaneously
# Used by: LumaxService.ps1, Start_FoveAI.ps1

param(
    [string]$Action = "check",  # check, acquire, release
    [string]$LockName = "foveai_services"
)

$LockDir = Join-Path $env:LOCALAPPDATA "FoveAI\locks"
if (-not (Test-Path $LockDir)) { New-Item -ItemType Directory -Path $LockDir -Force | Out-Null }
$LockFile = Join-Path $LockDir "$LockName.lock"
$CurrentPid = $PID

function Get-LockInfo {
    if (Test-Path $LockFile) {
        try {
            $content = Get-Content $LockFile -Raw | ConvertFrom-Json
            return $content
        } catch {}
    }
    return $null
}

function Test-ProcessAlive {
    param([int]$PidToCheck)
    try {
        $p = Get-Process -Id $PidToCheck -ErrorAction SilentlyContinue
        return ($null -ne $p -and -not $p.HasExited)
    } catch {
        return $false
    }
}

function Acquire-Lock {
    $existing = Get-LockInfo
    if ($existing) {
        $existingPid = $existing.pid
        if (Test-ProcessAlive $existingPid) {
            # Another instance is running - check if it's us (same PID)
            if ($existingPid -eq $CurrentPid) {
                # We already hold the lock - refresh timestamp
                @{ pid = $CurrentPid; acquired = (Get-Date).ToString("o") } | ConvertTo-Json | Set-Content $LockFile -Force
                return $true
            }
            # Another instance holds the lock
            Write-Warning "Another FoveAI service manager is running (PID $existingPid)"
            return $false
        }
        # Stale lock - orphaned process, safe to overwrite
        Write-Host "Clearing stale lock from dead process (PID $existingPid)" -ForegroundColor Yellow
    }
    
    # Acquire lock
    @{ pid = $CurrentPid; acquired = (Get-Date).ToString("o") } | ConvertTo-Json | Set-Content $LockFile -Force
    return $true
}

function Release-Lock {
    $existing = Get-LockInfo
    if ($existing -and $existing.pid -eq $CurrentPid) {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
        return $true
    }
    return $false
}

switch ($Action) {
    "check" {
        $lock = Get-LockInfo
        if ($lock) {
            if (Test-ProcessAlive $lock.pid) {
                Write-Host "Lock held by PID $($lock.pid) since $($lock.acquired)"
                exit 0
            } else {
                Write-Host "Stale lock from dead PID $($lock.pid)" -ForegroundColor Yellow
                exit 1
            }
        } else {
            Write-Host "No lock active"
            exit 1
        }
    }
    "acquire" {
        if (Acquire-Lock) {
            Write-Host "Lock acquired for PID $CurrentPid"
            exit 0
        } else {
            Write-Host "Failed to acquire lock" -ForegroundColor Red
            exit 1
        }
    }
    "release" {
        if (Release-Lock) {
            Write-Host "Lock released"
            exit 0
        } else {
            Write-Host "Lock not held by this process" -ForegroundColor Yellow
            exit 1
        }
    }
    "force" {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
        Write-Host "Lock file forcibly removed"
        exit 0
    }
}