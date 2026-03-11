
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from backend.self_learning_backtest import SelfLearningBacktester

def main():
    print("--- STARTING SELF-LEARNING OPTIMIZATION ---")
    
    # Initialize
    # We use a 60-day period for learning as yfinance 15m data limit is ~60 days
    optimizer = SelfLearningBacktester(ticker="^NSEI")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=59)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    print(f"Goal: Find optimal ICT parameters for NIFTY 50 ({start_str} to {end_str})")
    
    # Run Learning
    # This will:
    # 1. Fetch data
    # 2. Train ML model (Random Forest)
    # 3. Run Bayesian Optimization on Strategy Parameters (RSI thresholds, etc.)
    result = optimizer.learn_from_history(
        start_date=start_str, 
        end_date=end_str, 
        interval="15m"
    )
    
    if result:
        print("\n--- OPTIMIZATION RESULTS ---")
        best_params = result['optimized_params']
        print(f"Best Parameters Found:\n{best_params}")
        
        test_results = result['test_results']
        if test_results:
            print("\nPerformance on Hold-out Data:")
            for strategy, res in test_results.items():
                print(f"\nStrategy: {strategy}")
                print(f"  Win Rate: {res['win_rate']:.1f}%")
                print(f"  Profit Factor: {res['profit_factor']:.2f}")
                print(f"  Total Trades: {res['total_trades']}")
                print(f"  Total P/L: {res['total_pnl']:.2f}")
    else:
        print("\nOptimization Failed or No Data.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nCRASHED: {e}")
        import traceback
        traceback.print_exc()
