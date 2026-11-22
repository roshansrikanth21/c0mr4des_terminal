@echo off
title c0mr4des terminal launcher
REM ============================================================
REM  c0mr4des terminal - full local start
REM    [api]  uvicorn backend.app:app  ->  http://127.0.0.1:8100
REM    [ui]   vite dev server          ->  http://localhost:5173 (proxies /api to the api)
REM    then opens the terminal in your default browser.
REM
REM  Notes:
REM  - Local feed is Yahoo. This machine NEVER logs in to Angel.
REM  - The paper-trading bot itself runs on the Azure VM
REM    (systemd service "c0mr4des"); the launcher starts the desk
REM    locally, the bot is separate and already running there.
REM ============================================================
set REPO=D:\c0mr4des_terminal

netstat -ano | findstr /r ":8100.*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [api] uvicorn already running on :8100 - leaving it alone
    goto api_done
)
echo [api] starting uvicorn on :8100 ...
start "c0mr4des api :8100" /min cmd /c "cd /d %REPO% && .venv\Scripts\python.exe -m uvicorn backend.app:app --port 8100"
:api_done

netstat -ano | findstr /r ":5173.*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [ui] vite already running on :5173 - leaving it alone
    goto ui_done
)
echo [ui] starting vite on :5173 ...
start "c0mr4des ui :5173" /min cmd /c "cd /d %REPO% && npm run dev"
:ui_done

echo [wait] giving the servers a few seconds...
timeout /t 6 /nobreak >nul
start "" "http://localhost:5173"
echo.
echo [ok] Terminal opening at http://localhost:5173
echo      If it is blank or refuses, vite is still warming up - wait 5-10s, refresh.
echo      To stop a piece: close its black window (api / ui).
echo      The bot on the Azure VM keeps paper-trading; this launcher only starts the desk locally.
pause
