@echo off
cd /d "K:\ai-market-analyser-main\ai-market-analyser-main"
echo.
echo AI Trading System Launcher
echo ========================
echo.
echo 1. Start Original System (Working)
echo 2. Start Improved System (New Features)
echo 3. Start Web App (Frontend + Backend)
echo.
set /p choice=Select option:
if %choice%==1 goto original
if %choice%==2 goto improved  
if %choice%==3 goto webapp
goto end

:original
echo Starting Original System...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto end

:improved
echo Starting Improved System...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
goto end

:webapp
echo Starting Complete Web App...
python run_web_app.py
goto end

:end
pause
