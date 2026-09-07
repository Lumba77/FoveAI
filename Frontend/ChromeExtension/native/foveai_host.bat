@echo off
REM FoveAI Native Messaging Host ? bridges Chrome Extension to local system
REM Uses the unified venv Python (has fastapi, httpx, etc.)

set "FoveAI_ROOT=%~dp0..\..\.."

REM Prefer unified venv Python, fall back to system Python
if exist "%FoveAI_ROOT%\.venv\Scripts\python.exe" (
"%FoveAI_ROOT%\.venv\Scripts\python.exe" "%~dp0nm_host.py" "%FoveAI_ROOT%"
) else if exist "%FoveAI_ROOT%\.venv\unified\Scripts\python.exe" (
    "%FoveAI_ROOT%\.venv\unified\Scripts\python.exe" "%~dp0nm_host.py" "%FoveAI_ROOT%"
) else (
    python "%~dp0nm_host.py" "%FoveAI_ROOT%"
)
