@echo off
REM C0MR4DE Terminal - starts the API (port 8100) and the UI (port 5173)
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r backend\requirements.txt
)
if not exist node_modules call npm install
start "c0mr4des-api" cmd /k ".venv\Scripts\python -m uvicorn backend.app:app --port 8100"
start "c0mr4des-ui" cmd /k "npm run dev"
timeout /t 5 >nul
start http://localhost:5173
