@echo off
REM LUMAX First-Time Setup — run once after extracting from backup zip
REM Creates .env from .env.example, installs Python and Node dependencies, builds WebVM.
setlocal enabledelayedexpansion

echo ============================================
echo   LUMAX Sovereign Setup
echo ============================================
echo.

REM --- 1. Create .env from .env.example if missing ---
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Created .env from .env.example
        echo [!] IMPORTANT: Edit .env and fill in your API keys and model paths before starting LUMAX.
    ) else (
        echo [WARN] No .env.example found. You will need to create .env manually.
    )
) else (
    echo [OK] .env already exists — skipping
)

REM --- 2. Python virtual environment ---
if defined LUMAX_VENV_PATH (
    set "VENV_DIR=%LUMAX_VENV_PATH%"
) else (
    set "VENV_DIR=.venv"
)
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo.
    echo [SETUP] Creating Python virtual environment...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo [ERROR] Failed to create %VENV_DIR%. Make sure Python 3.10+ is installed and on PATH.
        goto :node_setup
    )
    echo [OK] %VENV_DIR% created
) else (
    echo [OK] %VENV_DIR% already exists — skipping
)

REM --- 3. Install Python dependencies ---
echo.
echo [SETUP] Installing Python dependencies...
call %VENV_DIR%\Scripts\activate.bat

if exist "backend\requirements.txt" (
    pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [WARN] backend\requirements.txt install had errors
    ) else (
        echo [OK] Mind Python dependencies installed
    )
) else (
    echo [WARN] backend\requirements.txt not found — run: pip install fastapi uvicorn httpx python-dotenv pydantic jinja2 llama-cpp-python
)

if exist "Scripts\requirements.mouth.txt" (
    pip install -r Scripts\requirements.mouth.txt
    if errorlevel 1 (
        echo [WARN] Scripts\requirements.mouth.txt install had errors
    ) else (
        echo [OK] Mouth Python dependencies installed
    )
) else (
    echo [INFO] Scripts\requirements.mouth.txt not found — skipping
)

if exist "Scripts\requirements.soundboard.txt" (
    pip install -r Scripts\requirements.soundboard.txt
    if errorlevel 1 (
        echo [WARN] Scripts\requirements.soundboard.txt install had errors
    ) else (
        echo [OK] Soundboard Python dependencies installed
    )
) else (
    echo [INFO] Scripts\requirements.soundboard.txt not found — skipping
)

call deactivate 2>nul

:node_setup
REM --- 4. Node.js dependencies for XR Vessel ---
echo.
if exist "Frontend\XR_Vessel\package.json" (
    echo [SETUP] Installing Node.js dependencies for XR Vessel...
    cd Frontend\XR_Vessel
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Make sure Node.js 18+ is installed.
        cd ..\..
    ) else (
        echo [OK] Node.js dependencies installed
        cd ..\..
    )
) else (
    echo [WARN] Frontend\XR_Vessel\package.json not found — skipping npm install
)

REM --- 5. Build WebVM if source exists ---
echo.
if exist "Frontend\XR_Vessel\webvm_source\package.json" (
    echo [SETUP] Building WebVM from source...
    cd Frontend\XR_Vessel\webvm_source
    call npm install
    if errorlevel 1 (
        echo [ERROR] WebVM npm install failed.
        cd ..\..\..
    ) else (
        call npm run build
        if errorlevel 1 (
            echo [ERROR] WebVM build failed.
            cd ..\..\..
        ) else (
            echo [OK] WebVM built successfully
            if not exist "..\public\webvm\build" mkdir "..\public\webvm\build"
            xcopy "build\*" "..\public\webvm\build\" /E /I /Y >nul
            if errorlevel 1 (
                echo [WARN] Failed to copy WebVM build output to public/webvm/build/
            ) else (
                echo [OK] WebVM build output copied to public/webvm/build/
            )
            cd ..\..\..
        )
    )
) else (
    echo [INFO] webvm_source not found — skipping WebVM build
)

REM --- 6. Aider (optional, isolated venv to avoid dependency conflicts) ---
echo.
echo [SETUP] Setting up Aider in isolated venv...
if not exist ".aider-venv\Scripts\activate.bat" (
    python -m venv .aider-venv
    if errorlevel 1 (
        echo [WARN] Failed to create Aider venv — skipping
        goto :done
    )
    echo [OK] .aider-venv created
) else (
    echo [OK] .aider-venv already exists — skipping
)

call .\.aider-venv\Scripts\activate.bat
pip install "aider-chat[browser]"
if errorlevel 1 (
    echo [WARN] Aider install had errors
) else (
    echo [OK] Aider installed in .aider-venv
)
call deactivate 2>nul

:done
REM --- Done ---
echo.
echo ============================================
echo   Setup complete!
echo.
echo   Next steps:
echo   1. Edit .env — fill in API keys and model paths
echo   2. Run: lumax.cmd
echo.
echo   Tools:
echo   - Aider:  .aider-venv\Scripts\aider.exe
echo   - Aider (safe):  aider_safe.cmd  (prevents clipboard image paste crashes)
echo   - LUMAX:  lumax.cmd
echo ============================================
endlocal
