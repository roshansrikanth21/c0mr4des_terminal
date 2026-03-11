@echo off
echo ===================================================
echo     AI MARKET ANALYZER - SYSTEM SHUTDOWN
echo ===================================================
echo.

echo [1/1] Cleaning up system processes...
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM uvicorn.exe >nul 2>&1

echo.
echo ===================================================
echo     CLEANUP COMPLETE: ALL PROCESSES STOPPED
echo ===================================================
echo.
pause
