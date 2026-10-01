@echo off
REM LUMAX Sovereign Backup — Git-substitute version control via zip snapshots
REM Thin wrapper: all logic lives in backup.ps1 to avoid CMD/PowerShell escaping issues.
REM
REM Usage:
REM   .\backup.cmd                          Create snapshot (auto-message)
REM   .\backup.cmd commit "message"         Create snapshot with message
REM   .\backup.cmd log                       List all snapshots
REM   .\backup.cmd status                    Show changed files since last snapshot
REM   .\backup.cmd diff [path_filter]        Show content diff of changed files
REM   .\backup.cmd restore ^<snapshot_id^>   Restore files from a specific snapshot
REM   .\backup.cmd init                      Initialize the backup repository
REM   .\backup.cmd help                      Show this help text

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1" %*
