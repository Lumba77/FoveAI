@echo off
echo ===================================================
echo FoveAI Backend Setup - Firewall Configuration
echo ===================================================
echo.
echo This script will configure Windows Defender Firewall
echo to allow the Quest headset to communicate with the
echo local FoveAI Python backend.
echo.
echo Checking for Administrator privileges...

:: Check for Admin rights and Auto-Elevate if needed
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Administrator privileges confirmed.
    echo.
) else (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

echo Adding TCP Rule for ports 8000, 8400-8404...
powershell -Command "New-NetFirewallRule -DisplayName 'FoveAI Backend (TCP)' -Direction Inbound -LocalPort 8000,8400,8401,8402,8403,8404 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue"
if %errorLevel% == 0 (
    echo [OK] TCP Rule added successfully.
) else (
    echo [WARNING] Failed to add TCP Rule. It may already exist.
)

echo.
echo Adding UDP Rule for Wake port 9999...
powershell -Command "New-NetFirewallRule -DisplayName 'FoveAI Backend Wake (UDP)' -Direction Inbound -LocalPort 9999 -Protocol UDP -Action Allow -ErrorAction SilentlyContinue"
if %errorLevel% == 0 (
    echo [OK] UDP Rule added successfully.
) else (
    echo [WARNING] Failed to add UDP Rule. It may already exist.
)

echo.
echo ===================================================
echo Firewall Configuration Complete!
echo You can now connect to this PC from the Quest App.
echo ===================================================
pause
