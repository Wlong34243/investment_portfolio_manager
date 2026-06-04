@echo off
title Portfolio Manager - Idea Generator
cd /d "%~dp0"
echo ===================================================
echo 💡 RUNNING AI IDEA GENERATOR AGENT
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

echo Executing Idea Generator agent...
python manager.py agent ideas

echo.
echo ===================================================
echo 🔍 LOCATING AND OPENING LATEST REPORT
echo ===================================================

set "LATEST_REPORT="
for /f "tokens=*" %%a in ('dir /b /od /a-d "agent_outputs\ideas\ideas_*.md" 2^>nul') do (
    set "LATEST_REPORT=agent_outputs\ideas\%%a"
)

if defined LATEST_REPORT (
    echo Opening report: %LATEST_REPORT%
    start "" "%LATEST_REPORT%"
) else (
    echo [WARNING] No new report found in agent_outputs\ideas\
)

echo.
echo ===================================================
echo Done. Press any key to close this window.
echo ===================================================
pause > nul
