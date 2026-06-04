@echo off
title Portfolio Manager - Morning Sync
cd /d "%~dp0"
echo ===================================================
echo ☀️  RUNNING PORTFOLIO MORNING SYNC & SNAPSHOT
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
    echo [WARNING] No virtual environment detected in .venv, venv, or env. Using system Python.
)

echo Running morning sync with --live...
python manager.py morning --live

echo.
echo ===================================================
echo Done. Press any key to close this window.
echo ===================================================
pause > nul
