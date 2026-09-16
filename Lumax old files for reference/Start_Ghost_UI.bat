@echo off
setlocal enabledelayedexpansion

REM --- LUMAX GHOST UI LAUNCHER ---
REM Reads .env to determine if we launch the Top Bar or the System Tray

set "LUMAX_ROOT=%~dp0"
set "VENV_PYTHON=%LUMAX_ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment python not found at %VENV_PYTHON%
    pause
    exit /b 1
)

REM Read GHOST_UI_MODE from .env (Default to TRAY)
set "GHOST_UI_MODE=TRAY"
for /f "usebackq tokens=1,2 delims==" %%A in ("%LUMAX_ROOT%.env") do (
    if "%%A"=="GHOST_UI_MODE" set "GHOST_UI_MODE=%%B"
)

if "%GHOST_UI_MODE%"=="TOPBAR" (
    echo [Lumax] Launching Unified Top Bar Command Center...
    "%VENV_PYTHON%" "%LUMAX_ROOT%Tools\lumax_top_bar\lumax_top_bar.py"
) else (
    echo [Lumax] Launching System Tray Ghost Listener...
    start "" /b "%VENV_PYTHON%" "%LUMAX_ROOT%Tools\ghost_listener.py"
)

endlocal
