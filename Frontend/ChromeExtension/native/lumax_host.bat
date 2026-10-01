@echo off
REM LUMAX Native Messaging Host ? bridges Chrome Extension to local system
REM Uses the unified venv Python (has fastapi, httpx, etc.)

set "LUMAX_ROOT=%~dp0..\..\.."

REM Prefer unified venv Python, fall back to system Python
if exist "%LUMAX_ROOT%\.venv\Scripts\python.exe" (
"%LUMAX_ROOT%\.venv\Scripts\python.exe" "%~dp0nm_host.py" "%LUMAX_ROOT%"
) else if exist "%LUMAX_ROOT%\.venv\unified\Scripts\python.exe" (
    "%LUMAX_ROOT%\.venv\unified\Scripts\python.exe" "%~dp0nm_host.py" "%LUMAX_ROOT%"
) else (
    python "%~dp0nm_host.py" "%LUMAX_ROOT%"
)
