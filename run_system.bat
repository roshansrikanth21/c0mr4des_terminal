@echo off
setlocal EnableDelayedExpansion
echo ===================================================
echo     AI MARKET ANALYZER - SYSTEM STARTUP
echo ===================================================
echo.

:: Check for .venv folder using a safer jump pattern
if exist .venv\Scripts\activate.bat goto :has_venv
echo [ERROR] Virtual environment (.venv) not found!
echo Please create it first using: python -m venv .venv
pause
exit /b

:has_venv
echo [1/4] Syncing Latest Code...
git pull origin main --quiet

echo [1.5/4] Force-closing existing terminal windows...
:: Close specific windows by title to ensure a clean slate
taskkill /F /FI "WINDOWTITLE eq AI Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq AI Frontend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq AI Live Assistant*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Lucent Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Lucent Dashboard*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Lucent Assistant*" >nul 2>&1

echo [1.6/4] Freeing system ports (8000, 5173)...
:: Find pids on ports and kill them directly
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r /c:":8000 *LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r /c:":5173 *LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo [1.7/4] Cleaning up orphaned processes...
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM uvicorn.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
:: Check if --update flag was passed
set "update=n"
if "%1"=="--update" set "update=y"

if /i "%update%"=="y" (
    echo [Setup] Updating Backend...
    call .venv\Scripts\activate && pip install -r backend/requirements.txt
    echo [Setup] Updating Frontend...
    call npm install
) else (
    echo [Setup] Skipping update (Use --update to update dependencies)
)

echo [2/4] Starting Lucent Backend (Port 8000)...
start "Lucent Backend" cmd /k "call .venv\Scripts\activate && uvicorn backend.main:app --host 0.0.0.0 --port 8000"

echo.
echo [WAIT] Waiting for Lucent Backend to start and ML models to initialize...
:wait_loop
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/system/status | findstr "200" >nul
if errorlevel 1 (
    goto wait_loop
)
echo [OK] Backend is Live!

echo [3/4] Starting Lucent Dashboard (Port 5173)...
start "Lucent Dashboard" cmd /k "npm run dev"

echo [4/4] Starting Lucent Assistant (CLI)...
start "Lucent Assistant" cmd /k "call .venv\Scripts\activate && python backend/run_live_assistant.py"

echo.
echo ===================================================
echo     LUCENT TERMINAL IS LAUNCHING
echo ===================================================
echo.
echo Dashboard: http://localhost:5173
echo Backend API: http://localhost:8000
echo.
pause
