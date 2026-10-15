@echo off
REM LUMAX Voice Chat + XRLF Engine Launcher
REM Start this first, then open http://127.0.0.1:8080

echo ========================================
echo  LUMAX Voice Chat + XRLF Plumax Engine
echo ========================================
echo.

set VOICECHAT_DIR=%~dp0Frontend\VoiceChat
set PLUMAX_DIR=%~dp0FoveAI
set VENV_PYTHON=%PLUMAX_DIR%\.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo ERROR: Python venv not found at %VENV_PYTHON%
    pause
    exit /b 1
)

echo [1/2] Starting XRLF Plumax engine on port 8400...
start "XRLF Engine" /B "%VENV_PYTHON%" "%PLUMAX_DIR%\api\server.py" --model "%PLUMAX_DIR%\lumax-plumax-omni-router.xrlf" --port 8406

echo Waiting for engine to start (30s)...
timeout /t 30 /nobreak >nul

echo [2/2] Starting Voice Chat on port 8080...
start "LUMAX Voice Chat" /B "%VENV_PYTHON%" "%VOICECHAT_DIR%\server.py" --port 8080

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo  Ready! Open http://127.0.0.1:8080
echo  Press and hold the mic button to talk.
echo ========================================
echo.
echo  Close this window to stop all services.
echo.

pause
