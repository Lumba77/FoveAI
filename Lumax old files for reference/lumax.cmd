@echo off
REM LUMAX Sovereign Orchestrator Authoritative CLI
setlocal EnableDelayedExpansion

REM Check for Help flag
if /I "%~1"=="--help" goto ShowHelp
if /I "%~1"=="-h" goto ShowHelp
if /I "%~1"=="help" goto ShowHelp
if /I "%~1"=="/?" goto ShowHelp

REM Check if "backup" argument is passed — forward all subcommand args
if /I "%~1"=="backup" (
    call "%~dp0backup.cmd" %2 %3 %4 %5 %6 %7 %8 %9
    exit /b
)

REM Check if "refresh" argument is passed
for %%a in (%*) do (
    if "%%a"=="refresh" (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\refresh_and_start_lumax.ps1" %*
        exit /b
    )
)

REM Check if --debug flag is passed; strip it from forwarded args to avoid duplicate param
set DEBUG_FLAG=
set FORWARD_ARGS=
for %%a in (%*) do (
    if /I "%%a"=="--debug" (set DEBUG_FLAG=-LumaxDebug) else (
    if /I "%%a"=="-debug" (set DEBUG_FLAG=-LumaxDebug) else (
    if /I "%%a"=="-d" (set DEBUG_FLAG=-LumaxDebug) else (
        set FORWARD_ARGS=!FORWARD_ARGS! %%a
    )))
)

REM Default behavior - run normal start script
if defined DEBUG_FLAG (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start_LUMAX.ps1" !DEBUG_FLAG! !FORWARD_ARGS!
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start_LUMAX.ps1" %*
)
exit /b

:ShowHelp
echo ==============================================================================
echo 🦋 LUMAX SUPER TERMINAL ^& ORCHESTRATOR
echo ==============================================================================
echo.
echo Usage: lumax [command] [options]
echo.
echo Core Commands:
echo   (none)       Starts the full Diamond Concordia stack (Start_LUMAX.ps1)
echo   backup       Triggers the backup script (backup.cmd)
echo   refresh      Refreshes environment and starts LUMAX (refresh_and_start_lumax.ps1)
echo   help, -h     Shows this help screen
echo.
echo Options:
echo   --debug, -d  Runs LUMAX in debug mode (-LumaxDebug)
echo.
echo Active Super Terminal Features:
echo   * Foveated Memory: Infinity context compression via Foveated Memory Proxy (Port 8200).
echo   * Smart Advice: Background Fovea AI hook injecting terminal tips.
echo   * LUMAX Solver: Autonomous agent available (read-only mode enabled for safety).
echo.
echo ------------------------------------------------------------------------------
echo "One model, many faces. The environment talks back."
exit /b
