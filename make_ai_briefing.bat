@echo off
cd /d "%~dp0"

:: Detect virtual environment
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else if exist env\Scripts\activate.bat (
    call env\Scripts\activate.bat
) else (
    echo [WARNING] No virtual environment detected in .venv, venv, or env. Using system Python.
)

echo Refreshing composite bundle...
python manager.py bundle composite
if errorlevel 1 echo WARNING: bundle refresh failed, using newest existing bundle.
python tasks\export_ai_briefing.py --lookthrough refresh
if errorlevel 1 (
  echo.
  echo Export FAILED - see the preflight list above.
  echo Blocking issues stop the export on purpose. Fix them, or re-run with:
  echo   python tasks\export_ai_briefing.py --lookthrough refresh --force
  pause
  exit /b 1
)
