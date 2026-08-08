@echo off
title Portfolio Manager Launcher
set "PROJECT_DIR=C:\Dev\Investment_Portfolio"

:menu
cls
cd /d "%PROJECT_DIR%"
echo ===================================================
echo   PORTFOLIO MANAGER
echo ===================================================
echo.
echo   1. Morning Sync           (run_morning_sync.bat)
echo   2. AI Briefing            (make_ai_briefing.bat)
echo   3. Idea Generator         (run_idea_generator.bat)
echo   4. Morning Auto (unattended, logged)
echo   5. Schwab Emergency Reauth
echo   0. Exit
echo.
set "CHOICE="
set /p "CHOICE=Select an option: "

if "%CHOICE%"=="1" call "%PROJECT_DIR%\run_morning_sync.bat" & goto end
if "%CHOICE%"=="2" call "%PROJECT_DIR%\make_ai_briefing.bat" & goto end
if "%CHOICE%"=="3" call "%PROJECT_DIR%\run_idea_generator.bat" & goto end
if "%CHOICE%"=="4" call "%PROJECT_DIR%\morning_auto.bat" & goto end
if "%CHOICE%"=="5" call "%PROJECT_DIR%\schwab_emergency_reauth.bat" & goto end
if "%CHOICE%"=="0" exit /b 0

echo.
echo Invalid choice.
pause
goto menu

:end
echo.
pause
