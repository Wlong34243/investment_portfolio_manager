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
::           rolling log at logs\morning_auto.log, logs\last_run.json
:: Depends : python venv (.venv|venv|env), manager.py
:: Note    : NO pause statements - safe for unattended Windows Task Scheduler.
:: ============================================================
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=logs\morning_auto.log"
set "LAST_RUN=logs\last_run.json"
set "EXIT_CODE=0"

:: Record start time (ISO8601) for cockpit last-run panel
for /f "delims=" %%I in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('o')"') do set "STARTED_AT=%%I"

:: Rotate log at ~1 MB: keep one prior generation as morning_auto.log.1
for %%A in ("%LOG%") do if exist "%LOG%" if %%~zA GTR 1048576 (
  if exist "%LOG%.1" del "%LOG%.1"
  ren "%LOG%" morning_auto.log.1
)

if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) else (
if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) else (
if exist env\Scripts\activate.bat call env\Scripts\activate.bat))

echo [%date% %time%] ===== morning_auto start ===== >> "%LOG%"

:: Lock contention → exit 3 (distinct from pipeline failure exit 1).
:: Mirrors manager.py _STALE_LOCK_HOURS = 3.
if exist logs\pipeline.lock (
  powershell -NoProfile -Command "$p='logs\pipeline.lock'; if (Test-Path $p) { $h=(New-TimeSpan -Start (Get-Item $p).LastWriteTime -End (Get-Date)).TotalHours; if ($h -lt 3) { exit 1 } else { exit 0 } } else { exit 0 }"
  if errorlevel 1 (
    echo [%date% %time%] SKIP: pipeline lock held by another run. >> "%LOG%"
    set "EXIT_CODE=3"
    goto :write_last_run
  )
)

python manager.py morning --live >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] FAIL: morning pipeline returned an error. >> "%LOG%"
  set "EXIT_CODE=1"
  goto :write_last_run
)

echo [%date% %time%] ===== morning_auto done ===== >> "%LOG%"
set "EXIT_CODE=0"
goto :write_last_run

:write_last_run
for /f "delims=" %%I in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('o')"') do set "FINISHED_AT=%%I"
powershell -NoProfile -Command "$j=@{routine='morning';started_at=$env:STARTED_AT;finished_at=$env:FINISHED_AT;exit_code=[int]$env:EXIT_CODE}|ConvertTo-Json -Compress; Set-Content -Path 'logs\last_run.json' -Value $j -Encoding UTF8"
if "%EXIT_CODE%"=="0" start "" "http://127.0.0.1:8765/"
exit /b %EXIT_CODE%
