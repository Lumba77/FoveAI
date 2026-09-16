@echo off
REM Start the Ghost Listener (Push-to-Talk OS Integration)
set "FoveAI_ROOT=%~dp0"
set "VENV_PYTHON=%FoveAI_ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment python not found at %VENV_PYTHON%
    pause
    exit /b 1
)

echo Starting Ghost Listener...
"%VENV_PYTHON%" "%FoveAI_ROOT%Tools\ghost_listener.py"
pause
