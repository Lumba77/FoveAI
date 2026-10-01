@echo off
REM LUMAX Sovereign Orchestrator Authoritative CLI
setlocal EnableDelayedExpansion

REM Check if "backup" argument is passed — forward all subcommand args
if "%~1"=="backup" (
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
