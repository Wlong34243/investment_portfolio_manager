@echo off
title Portfolio Manager Launcher
set "PROJECT_DIR=C:\Dev\Investment_Portfolio"
set "PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "PYW=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"
set "UIURL=http://127.0.0.1:8765"

:menu
cls
cd /d "%PROJECT_DIR%"
echo ===================================================
echo   PORTFOLIO MANAGER
echo ===================================================
echo.
echo   DAILY
echo     1. Morning Sync            (run_morning_sync.bat)
echo     2. Morning Auto            (unattended, logged)
echo     3. AI Briefing             (make_ai_briefing.bat)
echo.
echo   DESK
echo     4. Open Desk               (%UIURL%)
echo     5. Corpus Search
echo     6. Ask the Analyst
echo.
echo   DECIDE
echo     7. Tax Projection          (estimate, per ticker)
echo     8. Pre-commitments         (list / pending)
echo     9. Journal Reconcile       (dry run)
echo.
echo   REVIEW
echo    10. Judgment - rotations
echo    11. Judgment - lifecycle
echo    12. Judgment - calibration
echo.
echo   SYSTEM
echo    13. Evidence Status         (accrual gate)
echo    14. Store Verify + Parity
echo    15. Corpus Index            (incremental)
echo    16. Idea Generator
echo    17. Schwab Emergency Reauth
echo     0. Exit
echo.
set "CHOICE="
set /p "CHOICE=Select an option: "

if "%CHOICE%"=="1"  call "%PROJECT_DIR%\run_morning_sync.bat" & goto end
if "%CHOICE%"=="2"  call "%PROJECT_DIR%\morning_auto.bat" & goto end
if "%CHOICE%"=="3"  call "%PROJECT_DIR%\make_ai_briefing.bat" & goto end
if "%CHOICE%"=="4"  goto desk
if "%CHOICE%"=="5"  goto search
if "%CHOICE%"=="6"  goto ask
if "%CHOICE%"=="7"  goto taxproj
if "%CHOICE%"=="8"  goto precommit
if "%CHOICE%"=="9"  "%PY%" manager.py journal reconcile & goto end
if "%CHOICE%"=="10" "%PY%" manager.py judge rotations & goto end
if "%CHOICE%"=="11" goto lifecycle
if "%CHOICE%"=="12" "%PY%" manager.py judge calibration & goto end
if "%CHOICE%"=="13" "%PY%" manager.py store evidence-status & goto end
if "%CHOICE%"=="14" "%PY%" manager.py store verify & "%PY%" manager.py store bundle-parity & goto end
if "%CHOICE%"=="15" "%PY%" manager.py corpus index --live & goto end
if "%CHOICE%"=="16" call "%PROJECT_DIR%\run_idea_generator.bat" & goto end
if "%CHOICE%"=="17" call "%PROJECT_DIR%\schwab_emergency_reauth.bat" & goto end
if "%CHOICE%"=="0"  exit /b 0

echo.
echo Invalid choice.
pause
goto menu

:desk
echo Starting Desk (ignore a port-in-use message - it means it is already running)...
start "" /b "%PYW%" manager.py ui serve
timeout /t 3 >nul
start "" "%UIURL%/"
goto menu

:search
echo.
set "Q="
set /p "Q=Search the corpus for: "
if "%Q%"=="" goto menu
set "TK="
set /p "TK=Limit to ticker (blank for all): "
if "%TK%"=="" (
  "%PY%" manager.py corpus search "%Q%" --limit 15
) else (
  "%PY%" manager.py corpus search "%Q%" --ticker "%TK%" --limit 15
)
goto end

:ask
echo.
set "Q="
set /p "Q=Question: "
if "%Q%"=="" goto menu
echo.
echo [1] Dry run - show the retrieval plan only, no model call
echo [2] Full answer
set "M="
set /p "M=Choose (default 1): "
if "%M%"=="2" ( "%PY%" manager.py ask "%Q%" ) else ( "%PY%" manager.py ask "%Q%" --dry-run )
echo.
echo Artifacts land in agent_outputs\analyst\
goto end

:taxproj
echo.
set "TK="
set /p "TK=Ticker: "
if "%TK%"=="" goto menu
set "SH="
set /p "SH=Shares to model: "
if "%SH%"=="" goto menu
"%PY%" manager.py tax project --ticker "%TK%" --shares %SH%
echo.
echo Figures above are ESTIMATES of Schwab Tax Lot Optimizer relief - not a determination.
goto end

:precommit
echo.
echo [1] List all declarations
echo [2] Pending firings awaiting your response
set "M="
set /p "M=Choose (default 2): "
if "%M%"=="1" ( "%PY%" manager.py journal precommit --list ) else ( "%PY%" manager.py journal precommit --pending )
goto end

:lifecycle
echo.
set "TK="
set /p "TK=Ticker (blank for all held): "
if "%TK%"=="" (
  "%PY%" manager.py judge lifecycle --all
) else (
  "%PY%" manager.py judge lifecycle --ticker "%TK%"
)
echo.
echo Artifacts land in agent_outputs\judgment\
goto end

:end
echo.
pause
goto menu
