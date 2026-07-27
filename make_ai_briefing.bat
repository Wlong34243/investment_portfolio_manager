@echo off
cd /d C:\Users\WLong\Investment_Portfolio
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
