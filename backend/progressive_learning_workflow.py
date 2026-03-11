"""
Progressive Learning Workflow
Orchestrates the self-learning and continuous improvement process
"""

import sys
import os
import time
from datetime import datetime, timedelta
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.self_learning_backtest import SelfLearningBacktester
from backend.learning_tracker import LearningTracker, ContinuousLearningManager
from backend.improved_signals import EnhancedTradeSignals

def initial_learning_phase():
    """
    Phase 1: Initial Learning from Historical Data
    
    1. Fetch extensive historical data
    2. Run Bayesian Optimization to find best parameters
    3. Train ML model to filter false signals
    4. Save initial "smart" model
    """
    print("\n" + "="*80)
    print("🚀 PHASE 1: INITIAL LEARNING FROM HISTORICAL DATA")
    print("="*80)
    
    learner = SelfLearningBacktester(ticker="^NSEI")
    
    # Check if model already exists
    if learner.load_model():
        print("✅ Existing model found. Skipping extensive initial training.")
        print(f"   Current Win Rate: {learner.performance_metrics.get('win_rate', 0):.1f}%")
        
        choice = input("   Do you want to retrain anyway? (y/n): ")
        if choice.lower() != 'y':
            return learner
    
    print("\n📚 Starting rigorous historical learning...")
    
    # Learn from last 6 months
    # Note: 60d+ via yfinance needs 1h interval, <60d can be 15m
    # User requested 15m. So let's stick to last 59 days to be safe with yfinance limits for 15m
    # or implement chunking. For simplicity here: 59 days.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=59) 
    
    print(f"   Period: {start_date.date()} to {end_date.date()}")
    
    result = learner.learn_from_history(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
        interval="15m"
    )
    
    if result:
        print("\n🏆 OPTIMIZATION RESULTS:")
        for strategy, params in result['optimized_params'].items():
            print(f"\n   Strategy: {strategy.upper()}")
            for param, value in params.items():
                print(f"     - {param}: {value:.4f}")
        
    return learner

def continuous_learning_phase(learner):
    """
    Phase 2: Continuous Learning Simulation
    
    1. Simulate live trading day by day
    2. Track performance of each trade
    3. Retrain model periodically
    4. Adapt parameters based on recent market regime
    """
    print("\n" + "="*80)
    print("🔄 PHASE 2: CONTINUOUS LEARNING SIMULATION")
    print("="*80)
    
    manager = ContinuousLearningManager()
    manager.initialize("^NSEI")
    
    # We'll simulate the last 7 days as "live" trading
    print("\n🧪 Simulating last 7 days as live trading...")
    
    try:
        import yfinance as yf
        data = yf.download("^NSEI", period="7d", interval="15m", progress=False)
        if hasattr(data.columns, 'droplevel'):
             data.columns = data.columns.get_level_values(0)
             
        if data.empty:
            print("❌ No data available for simulation")
            return
            
        print(f"   Loaded {len(data)} candles for simulation")
        
        # Get signals based on learned model
        signals = learner.get_optimized_signals(data)
        
        print(f"   Found {len(signals)} optimized signals")
        
        trades_processed = 0
        total_pnl = 0
        
        for signal in signals:
            # Simulate trade outcome (simplified)
            # In real system, this would be actual trade result
            
            # Check price movement after signal time
            signal_time = pd.Timestamp(signal['timestamp'])
            try:
                # Find index of signal
                if signal_time in data.index:
                    idx = data.index.get_loc(signal_time)
                else: 
                    # Approximate
                    idx = data.index.get_indexer([signal_time], method='nearest')[0]
                
                if idx + 10 < len(data):
                    future_prices = data['Close'].iloc[idx+1:idx+11]
                    max_price = future_prices.max()
                    min_price = future_prices.min()
                    
                    entry = signal['entry_price']
                    target = signal['target']
                    stop = signal['stop_loss']
                    
                    pnl = 0
                    outcome = "NEUTRAL"
                    
                    # Determine outcome
                    if max_price >= target:
                        pnl = (target - entry) * 50  # 1 lot Nifty
                        outcome = "WIN"
                    elif min_price <= stop:
                        pnl = (stop - entry) * 50
                        outcome = "LOSS"
                    else:
                        close_price = future_prices.iloc[-1]
                        pnl = (close_price - entry) * 50
                        outcome = "OPEN"
                    
                    # Create trade record
                    trade_record = {
                        'timestamp': signal['timestamp'],
                        'strategy': signal['type'],
                        'entry_price': entry,
                        'exit_price': target if outcome == "WIN" else (stop if outcome == "LOSS" else future_prices.iloc[-1]),
                        'pnl': pnl,
                        'confidence': signal['combined_confidence'],
                        'parameters': {k: v for k, v in signal.items() 
                                     if k not in ['type', 'timestamp', 'combined_confidence', 'optimized', 'ml_confidence', 'entry_price', 'exit_price', 'pnl']},
                        # Fix: Add features for retraining if available
                        'features': learner._extract_features(data, idx).tolist() if hasattr(learner, '_extract_features') else []
                    }
                    
                    # Process via manager
                    result = manager.process_trade(trade_record)
                    trades_processed += 1
                    total_pnl += pnl
                    
                    print(f"   Trade {trades_processed}: {outcome} | P&L: {pnl:.2f} | Conf: {signal['combined_confidence']:.2f} | Learner Updated: {result.get('should_retrain', False)}")
                    
            except Exception as e:
                # print(f"   Error simulating trade: {e}")
                pass
                
        print("\n📈 CONTINUOUS LEARNING RESULTS:")
        report = manager.get_performance_report()
        
        if 'error' not in report:
            summary = report['summary']
            print(f"   Total Simulated Trades: {summary['total_trades']}")
            print(f"   Win Rate: {summary['win_rate']:.1f}%")
            print(f"   Total P&L: {summary['total_pnl']:.2f}")
            print(f"   Profit Factor: {summary['profit_factor']:.2f}")
            
            suggestions = manager.get_improvement_suggestions()
            if 'suggestions' in suggestions:
                print("\n💡 AI SUGGESTIONS REVEALED:")
                for s in suggestions['suggestions']:
                    print(f"   • {s}")
                    
    except Exception as e:
        print(f"Error in simulation: {e}")
        import traceback
        traceback.print_exc()

def daily_learning_routine():
    """
    Routine to be called daily by scheduler
    1. Updates learning from yesterday's trades
    2. Learns from overnight data/global cues (placeholder)
    3. Prepares optimized parameters for today
    """
    manager = ContinuousLearningManager()
    manager.initialize()
    
    # Run scheduled learning
    manager._run_scheduled_learning()
    
    # Generate dashboard
    dashboard = manager.get_dashboard()
    # Save dashboard html? 
    # Not implemented in manager.get_dashboard logic (it returns figure)
    # But checking user code requirements... nothing specific.

if __name__ == "__main__":
    # Run the full workflow
    learner = initial_learning_phase()
    continuous_learning_phase(learner)
