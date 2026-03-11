#!/usr/bin/env python3
"""
Universal AI Trading System Launcher
Compiles and starts everything automatically with all fixes applied
"""

import os
import sys
import subprocess
import importlib.util
from pathlib import Path

def compile_python_file(file_path):
    """Compile a Python file to check for syntax errors"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        compile(code, str(file_path), 'exec')
        return True, None
    except Exception as e:
        return False, str(e)

def fix_imports_in_file(file_path):
    """Fix common import issues in Python files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Fix common import issues
        fixes = [
            ('from backend.', 'from .'),
            ('import backend.', 'import .'),
            ('from backend.', 'from .'),
            ('import backend.market_data', 'from .market_data'),
            ('import backend.main_integration', 'from .main_integration'),
            ('import backend.dashboard_integration', 'from .dashboard_integration'),
            ('import backend.learning_tracker', 'from .learning_tracker'),
            ('import backend.execution_engine', 'from .execution_engine'),
            ('import backend.quant_engine', 'from .quant_engine'),
            ('import backend.backtest', 'from .backtest'),
            ('import backend.optimizer', 'from .optimizer'),
            ('import backend.ict_smart_money', 'from .ict_smart_money'),
            ('import backend.intraday_utils', 'from .intraday_utils'),
            ('import backend.market_intelligence', 'from .market_intelligence'),
            ('import backend.integrated_quant_system', 'from .integrated_quant_system'),
            ('import backend.broker.base_broker', 'from .broker.base_broker'),
            ('import backend.broker.paper_broker', 'from .broker.paper_broker'),
            ('import backend.broker.angel_one_broker', 'from .broker.angel_one_broker'),
            ('import backend.ornstein_uhlenbeck', 'from .ornstein_uhlenbeck'),
            ('import backend.mst_analysis', 'from .mst_analysis'),
            ('import backend.config', 'from .config'),
        ]
        
        original_content = content
        for old_import, new_import in fixes:
            content = content.replace(old_import, new_import)
        
        # Only write if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    except Exception:
        return False

def main():
    """Main compilation and launcher"""
    print("🔧 AI Trading System - Universal Launcher & Compiler")
    print("=" * 60)
    
    base_path = Path("K:/ai-market-analyser-main/ai-market-analyser-main")
    
    if not base_path.exists():
        print(f"❌ Base path not found: {base_path}")
        return
    
    backend_path = base_path / "backend"
    print(f"📁 Working directory: {backend_path}")
    
    # Change to backend directory
    os.chdir(backend_path)
    
    # List of Python files to fix and compile
    python_files = [
        "main.py",
        "market_data.py",
        "quant_engine.py",
        "backtest.py",
        "ict_smart_money.py",
        "intraday_utils.py",
        "execution_engine.py",
        "integrated_quant_system.py",
        "learning_tracker.py",
        "market_intelligence.py",
        "broker/base_broker.py",
        "broker/paper_broker.py",
        "broker/angel_one_broker.py",
        "ornstein_uhlenbeck.py",
        "mst_analysis.py"
    ]
    
    print("\n🔍 Step 1: Fixing imports in all Python files...")
    fixed_count = 0
    for py_file in python_files:
        file_path = backend_path / py_file
        if file_path.exists():
            if fix_imports_in_file(file_path):
                fixed_count += 1
                print(f"  ✅ Fixed imports in {py_file}")
    
    print(f"  📝 Fixed imports in {fixed_count} files")
    
    print("\n🧪 Step 2: Compiling all Python files...")
    compiled_files = 0
    error_files = []
    
    for py_file in python_files:
        file_path = backend_path / py_file
        if file_path.exists():
            success, error = compile_python_file(file_path)
            if success:
                compiled_files += 1
                print(f"  ✅ Compiled {py_file}")
            else:
                error_files.append((py_file, error))
                print(f"  ❌ Compilation error in {py_file}: {error}")
    
    print(f"\n  📊 Summary: {compiled_files} compiled, {len(error_files)} errors")
    
    if error_files:
        print("\n🚨 Compilation Errors Found:")
        for file_name, error in error_files:
            print(f"  📄 {file_name}: {error}")
        print("\n⚠️  Please fix these errors before running the system")
        return
    
    print("\n⚙️ Step 3: Installing missing dependencies...")
    dependencies = [
        "aiohttp", "scipy", "pydantic", "keyring", 
        "cryptography", "redis", "yfinance", "pandas",
        "numpy", "uvicorn", "fastapi", "python-dotenv"
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"  ✅ {dep} - Available")
        except ImportError:
            print(f"  📦 Installing {dep}...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", dep], 
                           capture_output=True, text=True, check=True)
                print(f"  ✅ {dep} - Installed")
            except Exception as e:
                print(f"  ❌ {dep} - Failed: {e}")
    
    print("\n🚀 Step 4: Starting AI Trading System...")
    
    # Start FastAPI app via uvicorn
    print("  🎯 Attempting to start backend API...")
    try:
        result = subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"], 
                           capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0 and "Uvicorn running on" in result.stdout:
            print("  ✅ Backend started successfully!")
            print(f"  🌐 Access at: http://localhost:8000")
            print(f"  📚 API docs: http://localhost:8000/docs")
            return
        else:
            print(f"  ⚠️  Backend had issues, trying direct run...")
            
    except subprocess.TimeoutExpired:
        print("  ⏱️  System starting up (timeout after 5s)")
        return
    except Exception as e:
        print(f"  ⚠️  Backend start failed: {e}")
    
    # Fallback to original system
    print("  🔄 Starting backend directly...")
    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"])
    except KeyboardInterrupt:
        print("\n  👋 System stopped by user")
    except Exception as e:
        print(f"  ❌ System failed to start: {e}")
        print("\n  💡 Try running manually:")
        print(f"     cd {backend_path}")
        print("     python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")

if __name__ == "__main__":
    main()
