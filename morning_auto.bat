@echo off
:: ============================================================
:: morning_auto.bat - unattended morning pipeline (Task Scheduler)
:: Purpose : run the full morning pipeline unattended.
::           manager.py morning --live internally covers:
::           health -> Schwab sync -> snapshot -> podcasts -> dashboard
::           -> vault sync -> composite bundle (STEP 8)
::           -> AI briefing export with --no-open (STEP 9)
:: Inputs  : none (repo venv + config.py)
:: Outputs : refreshed Portfolio Sheet, exports\ai_briefing_<ts>\ bundle,
::           rolling log at logs\morning_auto.log
:: Depends : python venv (.venv|venv|env), manager.py
:: Note    : NO pause statements - safe for unattended Windows Task Scheduler.
:: ============================================================
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=logs\morning_auto.log"

:: Rotate log at ~1 MB: keep one prior generation as morning_auto.log.1
for %%A in ("%LOG%") do if exist "%LOG%" if %%~zA GTR 1048576 (
  if exist "%LOG%.1" del "%LOG%.1"
  ren "%LOG%" morning_auto.log.1
)

if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) else (
if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) else (
if exist env\Scripts\activate.bat call env\Scripts\activate.bat))

echo [%date% %time%] ===== morning_auto start ===== >> "%LOG%"

python manager.py morning --live >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] FAIL: morning pipeline returned an error. >> "%LOG%"
  exit /b 1
)

echo [%date% %time%] ===== morning_auto done ===== >> "%LOG%"
exit /b 0
