@echo off
REM Start the Smart Repo Librarian Daemon
REM Uses the unified Python virtual environment

set "LUMAX_ROOT=%~dp0"
set "VENV_PYTHON=%LUMAX_ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment python not found at %VENV_PYTHON%
    pause
    exit /b 1
)

echo ==============================================
echo   LUMAX Lazy Smart Librarian Daemon
echo ==============================================
echo Running Dormant Egg Backup Protocol...
"%VENV_PYTHON%" "%LUMAX_ROOT%Tools\dormant_egg.py"

echo Starting librarian_daemon.py...
"%VENV_PYTHON%" "%LUMAX_ROOT%Backend\Cognition\librarian_daemon.py"
pause
