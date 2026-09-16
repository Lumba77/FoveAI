@echo off
REM Start the Smart Repo Librarian Daemon
REM Uses the unified Python virtual environment

set "FoveAI_ROOT=%~dp0"
set "VENV_PYTHON=%FoveAI_ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment python not found at %VENV_PYTHON%
    pause
    exit /b 1
)

echo ==============================================
echo   FoveAI Lazy Smart Librarian Daemon
echo ==============================================
echo Running Dormant Egg Backup Protocol...
"%VENV_PYTHON%" "%FoveAI_ROOT%Tools\dormant_egg.py"

echo Starting librarian_daemon.py...
"%VENV_PYTHON%" "%FoveAI_ROOT%Backend\Cognition\librarian_daemon.py"
pause
