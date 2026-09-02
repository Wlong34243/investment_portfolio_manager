@echo off
:: ============================================================
:: ai_track_auto.bat - unattended AI-track podcast sync (Task Scheduler)
:: Purpose : walk the 9 AI-track YouTube channels in data\podcast_channels.json
::           and write research briefs to data\ai_briefs\.
::           This is DELIBERATELY NOT part of morning_auto.bat:
::             - 9 Gemini calls, no market-open deadline
::             - transcript fetches share one IP with the morning finance walk;
::               running them together doubles the burst that caused the
::               2026-08-31 IpBlocked incident
:: Inputs  : none (repo venv + data\podcast_channels.json)
:: Outputs : data\ai_briefs\*.md + .json, data\podcast_transcripts\ai\*.txt,
::           rolling log at logs\ai_track_auto.log, logs\last_run_ai_track.json
:: Exit    : 0 ok / 1 all channels failed / 3 YouTube is rate-limiting this IP
:: Note    : NO pause statements - safe for unattended Windows Task Scheduler.
:: ============================================================
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=logs\ai_track_auto.log"
set "LAST_RUN=logs\last_run_ai_track.json"
set "EXIT_CODE=0"

for /f "delims=" %%I in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('o')"') do set "STARTED_AT=%%I"

:: Rotate log at ~1 MB
for %%A in ("%LOG%") do if exist "%LOG%" if %%~zA GTR 1048576 (
  if exist "%LOG%.1" del "%LOG%.1"
  ren "%LOG%" ai_track_auto.log.1
)

if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) else (
if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) else (
if exist env\Scripts\activate.bat call env\Scripts\activate.bat))

echo [%date% %time%] ===== ai_track_auto start ===== >> "%LOG%"

:: Share the morning pipeline's lock. The AI walk and the finance walk both
:: fetch transcripts from the same IP; overlapping them is exactly the burst
:: pattern that got the IP blocked. If morning is running, skip and try tomorrow.
if exist logs\pipeline.lock (
  powershell -NoProfile -Command "$p='logs\pipeline.lock'; if (Test-Path $p) { $h=(New-TimeSpan -Start (Get-Item $p).LastWriteTime -End (Get-Date)).TotalHours; if ($h -lt 3) { exit 1 } else { exit 0 } } else { exit 0 }"
  if errorlevel 1 (
    echo [%date% %time%] SKIP: pipeline lock held by the morning run. >> "%LOG%"
    set "EXIT_CODE=3"
    goto :write_last_run
  )
)

python manager.py podcast batch --track ai --max-per-channel 1 --live >> "%LOG%" 2>&1
set "EXIT_CODE=%errorlevel%"

if "%EXIT_CODE%"=="3" (
  echo [%date% %time%] BLOCKED: YouTube is rate-limiting this IP. Walk aborted; NOT retried. >> "%LOG%"
  goto :write_last_run
)
if not "%EXIT_CODE%"=="0" (
  echo [%date% %time%] FAIL: ai-track sync returned %EXIT_CODE%. >> "%LOG%"
  goto :write_last_run
)

echo [%date% %time%] ===== ai_track_auto done ===== >> "%LOG%"
goto :write_last_run

:write_last_run
for /f "delims=" %%I in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('o')"') do set "FINISHED_AT=%%I"
powershell -NoProfile -Command "$j=@{routine='ai_track';started_at=$env:STARTED_AT;finished_at=$env:FINISHED_AT;exit_code=[int]$env:EXIT_CODE}|ConvertTo-Json -Compress; Set-Content -Path 'logs\last_run_ai_track.json' -Value $j -Encoding UTF8"
exit /b %EXIT_CODE%
