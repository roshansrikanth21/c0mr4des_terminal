
import sys
import importlib
import os
import pkgutil

def check_module(module_name):
    try:
        importlib.import_module(module_name)
        print(f"[OK] {module_name} imported successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Error importing {module_name}: {e}")
        return False

def main():
    print("="*50)
    print("STARTING BACKEND HEALTH CHECK")
    print("="*50)
    
    # Add current directory to path
    sys.path.append(os.getcwd())
    
    modules_to_check = [
        "backend.main",
        "backend.market_data",
        "backend.intraday_utils",
        "backend.ict_smart_money",
        "backend.ornstein_uhlenbeck",
        "backend.mst_analysis",
        "backend.integrated_quant_system",
        "backend.advanced_analysis",
        "backend.backtest",
        "backend.self_learning_backtest",
        "backend.optimizer",
        "backend.quant_engine",
        "backend.sentiment_engine",
        "backend.options_indicators",
        "backend.nifty_timing",
        "backend.order_flow"
        # Add any other critical modules here
    ]
    
    failed = []
    
    for module in modules_to_check:
        if not check_module(module):
            failed.append(module)
            
    print("\n" + "="*50)
    if failed:
        print(f"HEALTH CHECK FAILED. {len(failed)} modules broken.")
        sys.exit(1)
    else:
        print("ALL BACKEND MODULES HEALTHY")
        sys.exit(0)

if __name__ == "__main__":
    main()
