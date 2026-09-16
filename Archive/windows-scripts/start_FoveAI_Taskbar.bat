@echo off
setlocal
cd /d "%~dp0"

:: Prefer repo .venv, then root venv, then system pythonw
set "PY_EXE=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=%~dp0venv\Scripts\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=%~dp0..\.venv\Scripts\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=pythonw.exe"

start "" "%PY_EXE%" "%~dp0FoveAI_Taskbar.pyw"