@echo off
cd /d C:\Users\WLong\Investment_Portfolio
echo Refreshing composite bundle...
python manager.py bundle composite
if errorlevel 1 echo WARNING: bundle refresh failed, using newest existing bundle.
python tasks\export_ai_briefing.py
if errorlevel 1 (
  echo Export FAILED. See errors above.
  pause
  exit /b 1
)
