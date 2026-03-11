#!/usr/bin/env python3
"""
Quick start script for AI Trading System with secure configuration.
"""

import os
import sys
import subprocess
from pathlib import Path

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
        r.ping()
        print("Redis is running")
        return True
    except:
        print("Redis is not running (using memory cache fallback)")
        return False

def start_redis():
    """Try to start Redis with Docker"""
    print("Attempting to start Redis with Docker...")
    try:
        result = subprocess.run([
            'docker', 'run', '-d', '-p', '6379:6379', 'redis:alpine'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Redis started successfully")
            return True
        else:
            print("Docker Redis start failed")
            return False
    except FileNotFoundError:
        print("Docker not found")
        return False

def start_trading_system():
    """Start the AI trading system"""
    print("\nStarting AI Trading System...")
    
    project_root = Path(__file__).parent
    backend_path = project_root / "backend"
    print(f"Project root: {project_root}")
    
    if not backend_path.exists():
        print(f"Backend path does not exist: {backend_path}")
        return False
    
    # Check if main API file exists
    main_file = backend_path / "main.py"
    if not main_file.exists():
        print(f"Main file does not exist: {main_file}")
        return False
    
    try:
        os.chdir(project_root)
        print(f"Changed to: {os.getcwd()}")
    except Exception as e:
        print(f"Failed to change directory: {e}")
        return False
    
    # Run FastAPI app through uvicorn
    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"])
    except KeyboardInterrupt:
        print("\nSystem stopped by user")
    except Exception as e:
        print(f"System error: {e}")

def main():
    """Main start process"""
    print("AI Trading System - Quick Start")
    print("=" * 50)
    
    # Check Redis
    redis_running = check_redis()
    
    if not redis_running:
        print("\nRedis is recommended for better performance.")
        response = input("Start Redis? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            if start_redis():
                import time
                time.sleep(2)  # Give Redis time to start
                check_redis()
    
    print("\nStarting trading system...")
    start_trading_system()

if __name__ == "__main__":
    main()
