@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "Q_SCRIPT=%SCRIPT_DIR%q.ps1"

if "%~1"=="" (
  echo Usage: q ^<question text^>
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%Q_SCRIPT%" -Words %*

endlocal

