@echo off
setlocal enabledelayedexpansion

echo [Lumax] Starting Subconscious Daemon...
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment python not found at %VENV_PYTHON%
    pause
    exit /b 1
)

"%VENV_PYTHON%" "%~dp0Backend\Cognition\subconscious_daemon.py"

endlocal
