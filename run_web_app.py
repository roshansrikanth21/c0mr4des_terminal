#!/usr/bin/env python3
"""
Run backend (FastAPI) and frontend (Vite) together for local development.
"""

import os
import sys
import subprocess
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()


def start_backend():
    """Start FastAPI backend on port 8000."""
    print("Starting backend on http://127.0.0.1:8000 ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=PROJECT_ROOT
        )
    except Exception as e:
        print(f"Backend failed: {e}")


def start_frontend():
    """Start Vite frontend on port 5173."""
    print("Starting frontend on http://127.0.0.1:5173 ...")
    try:
        if not (PROJECT_ROOT / "node_modules").exists():
            subprocess.run("npm install", shell=True, check=True, cwd=PROJECT_ROOT)
        subprocess.run("npm run dev", shell=True, cwd=PROJECT_ROOT)
    except Exception as e:
        print(f"Frontend failed: {e}")


def main():
    print("AI Market Analyzer - Web Runner")
    print("=" * 48)

    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    time.sleep(3)

    start_frontend()


if __name__ == "__main__":
    main()
