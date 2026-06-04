@echo off
title Portfolio Manager - Schwab Emergency Reauthentication
cd /d "%~dp0"
echo ===================================================
echo 🔑 RUNNING SCHWAB REAUTHENTICATION
echo ===================================================
echo.

:: Detect virtual environment
set "VENV_ACTIVE=0"
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    set "VENV_ACTIVE=1"
) else if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    set "VENV_ACTIVE=1"
) else if exist env\Scripts\activate.bat (
    call env\Scripts\activate.bat
    set "VENV_ACTIVE=1"
)

if "%VENV_ACTIVE%"=="1" (
    echo [INFO] Activated virtual environment.
) else (
    echo [WARNING] No virtual environment detected. Using system Python.
)

echo Executing re-authentication...
python manager.py login

echo.
echo ===================================================
echo Done. Press any key to close this window.
echo ===================================================
pause > nul
