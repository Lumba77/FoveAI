@echo off
REM Start the Ghost Listener (Push-to-Talk OS Integration)
set "LUMAX_ROOT=%~dp0"
set "VENV_PYTHON=%LUMAX_ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment python not found at %VENV_PYTHON%
    pause
    exit /b 1
)

echo Starting Ghost Listener...
"%VENV_PYTHON%" "%LUMAX_ROOT%Tools\ghost_listener.py"
pause
