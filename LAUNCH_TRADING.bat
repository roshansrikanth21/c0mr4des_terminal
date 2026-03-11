@echo off
title AI Trading System Launcher
color 0A

echo.
echo  ========================================
echo      AI TRADING SYSTEM LAUNCHER
echo  ========================================
echo.

echo Current Directory:
cd /d "K:\ai-market-analyser-main\ai-market-analyser-main"
echo %cd%
echo.

echo Choose Launch Option:
echo 1. Original System (Known Working)
echo 2. Improved System (New Features + Black-Scholes)
echo 3. Web App Only (Frontend + Backend)
echo 4. Backend API Only
echo 5. Exit
echo.

set /p choice=Select option (1-5): 

if %choice%==1 goto original
if %choice%==2 goto improved
if %choice%==3 goto webapp
if %choice%==4 goto backend_only
if %choice%==5 goto exit

:original
echo.
echo Starting Original System...
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto end

:improved
echo.
echo Starting Improved System...
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto end

:webapp
echo.
echo Starting Complete Web App...
echo.
python run_web_app.py
goto end

:backend_only
echo.
echo Starting Backend API Only...
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto end

:exit
echo Goodbye!
timeout /t 2 >nul
exit

:end
echo.
echo Press any key to exit...
pause >nul
