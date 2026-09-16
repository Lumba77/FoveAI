@echo off
title LUMAX [DIRECTOR DAEMON]
echo =======================================================
echo    LUMAX: THE 3RD PLAYER (CLOUD DIRECTOR MANAGER)
echo =======================================================
echo.
echo Initializing the Director...
echo Connecting to Cloud API for Heavy Generative Plotting...
echo (Will gracefully sleep if quota is exhausted)
echo.

cd /d "%~dp0"
if exist "Backend\Cognition\venv\Scripts\Activate.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\Backend\Cognition\venv\Scripts\Activate.ps1'; python Backend\Cognition\director_manager.py"
) else (
    python Backend\Cognition\director_manager.py
)

pause
