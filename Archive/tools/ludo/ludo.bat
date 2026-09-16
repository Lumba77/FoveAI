@echo off
setlocal

REM LUDO: Smart FoveAI Doer

set "FoveAI_ROOT=%~dp0..\.."
set "VENV_PYTHON=%FoveAI_ROOT%\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [LUDO ERROR] Virtual environment not found at %VENV_PYTHON%
    exit /b 1
)

"%VENV_PYTHON%" "%~dp0ludo_core.py" %*

endlocal
