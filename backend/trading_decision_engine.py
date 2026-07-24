"""
Integrated trading decision engine
Combines all models to generate unified trading decisions
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import json
import os

from backend.momentum_trading import MomentumTradingSystem, MomentumOptionsStrategies
from backend.volatility_position_sizing import VolatilityPositionSizer, RealTimeVolatilityMonitor
from backend.regime_detection import MarketRegimeDetector, MarkovRegimeSwitching
from backend.ornstein_uhlenbeck import RealTimeOUTrading
from backend.mst_analysis import RealTimeMSTTrader
from backend.market_timing import get_market_timing
from backend.execution_engine import ExecutionEngine

try:
    # Shared market data service with multiple providers & caching
    from backend.services.market_data_service import get_sync_market_data
except ImportError:
    get_sync_market_data = None

class IntegratedTradingDecisionEngine:
    """
    Master decision engine that integrates all modules
    """
    
    def __init__(self, ticker="^NSEI", capital=1000000, live=False):
        self.ticker = ticker
        self.capital = capital
        
        # Initialize modules
        self.momentum_system = MomentumTradingSystem(ticker)
        self.vol_sizer = VolatilityPositionSizer(capital)
        self.vol_monitor = RealTimeVolatilityMonitor([ticker])
        self.regime_detector = MarketRegimeDetector()
        self.markov_switching = MarkovRegimeSwitching()
        self.ou_trader = RealTimeOUTrading(ticker)
        # MST uses a predefined list of stocks, we don't pass ticker
        self.mst_trader = RealTimeMSTTrader()
        self.market_timing = get_market_timing(ticker)
        
        # Execution
        self.executor = ExecutionEngine()
        if live:
            self.executor.switch_broker(live=True)
        
        # History
        self.decision_history = []
        
    def run_comprehensive_analysis(self, execute=False):
        """
        Run all analyses and generate integrated trading decision
        """
        print(f"\n{'='*80}")
        print(f"[ENGINE] INTEGRATED TRADING DECISION ENGINE")
        print(f"{'='*80}")
        print(f"Ticker: {self.ticker} | Capital: INR {self.capital:,.2f}")
        
        # 1. Fetch Data
        df = self._get_market_data()
        if df is None or df.empty:
            return {"error": "Data fetch failed"}
            
        # 2. Run Modules
        print("\n[QUANT] RUNNING QUANT ANALYSES:")
        
        print("   • Momentum analysis...")
        momentum_plan = self.momentum_system.generate_trading_plan(df)
        
        print("   • Volatility analysis...")
        vol_data = self.vol_monitor.update_volatility()
        
        print("   • Market regime analysis...")
        regime_info = self.regime_detector.determine_regime()
        
        print("   • Mean reversion analysis...")
        ou_results = self.ou_trader.update_and_get_signals("1d")
        
        print("   • Markov switching...")
        msm_results = self.markov_switching.fit(df['Close'].pct_change().dropna())
        
        # 3. Decision Logic
        action, confidence, action_scores = self._aggregate_signals(
            momentum_plan, regime_info, ou_results, vol_data
        )
        
        # 4. Trading Plan
        trading_plan = self._create_trading_plan(action, confidence, vol_data, df)
        
        decision = {
            'action': action,
            'confidence': confidence,
            'action_scores': action_scores,
            'ticker': self.ticker,
            'price': float(df['Close'].iloc[-1]),
            'timestamp': datetime.now().isoformat()
        }
        
        # 4. Execute if requested
        execution_status = None
        if execute and action != 'HOLD':
            print(f"\n[EXECUTE] AUTOMATED EXECUTION TRIGGERED: {action}")
            execution_status = self.executor.execute_decision(decision, trading_plan)
            print(f"   Status: {execution_status['status']}")
            if execution_status.get('reason'):
                print(f"   Reason: {execution_status['reason']}")
        
        self._save_decision(decision, trading_plan)
        self._print_decision_summary(decision, trading_plan)
        
        return {
            'decision': decision,
            'plan': trading_plan,
            'regime': regime_info,
            'execution': execution_status
        }

    def _get_market_data(self):
        """Robust data fetcher using shared data service when available."""
        try:
            print(f"   • Fetching {self.ticker} prices via data service...")
            
            if get_sync_market_data is not None:
                df = get_sync_market_data(self.ticker, "1y", "1d")
            else:
                # Legacy path: use yfinance directly
                ticker_obj = yf.Ticker(self.ticker)
                df = ticker_obj.history(period="1y", interval="1d")
                
                if df.empty:
                    # Fallback to download if history fails
                    print(f"   [WARN] History empty for {self.ticker}, trying download...")
                    df = yf.download(self.ticker, period="1y", interval="1d", progress=False)
            
            if df.empty:
                print(f"   [WARN] Warning: No data found for {self.ticker}")
                return None
            
            # Data service already standardizes columns; legacy path may return MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                if self.ticker in df.columns.levels[0]:
                    df = df[self.ticker]
                else:
                    df.columns = df.columns.get_level_values(-1)
            
            # Map metrics to standard names
            if 'Close' not in df.columns and 'Price' in df.columns:
                df.rename(columns={'Price': 'Close'}, inplace=True)
                
            if 'Close' not in df.columns:
                print(f"   [ERROR] Error: 'Close' column missing. Available: {df.columns.tolist()}")
                return None
                
            return df
        except Exception as e:
            print(f"   [ERROR] Critical error fetching {self.ticker}: {e}")
            return None

    def _aggregate_signals(self, momentum, regime, ou, vol):
        scores = {'BUY': 0.0, 'SELL': 0.0, 'HOLD': 0.0}
        
        # Weights
        w = {'momentum': 0.4, 'regime': 0.3, 'ou': 0.3}
        
        # Momentum score
        m_action = momentum.get('action', 'HOLD')
        m_conf = momentum.get('confidence', 0.5)
        scores[m_action] += m_conf * w['momentum']
        
        # Regime Score
        r_primary = regime.get('primary_regime', 'NEUTRAL')
        r_conf = regime.get('confidence', 0.5)
        if r_primary in ['RISK_ON', 'EXPANSIONARY']:
            scores['BUY'] += r_conf * w['regime']
        elif r_primary in ['RISK_OFF', 'RECESSIONARY']:
            scores['SELL'] += r_conf * w['regime']
        else:
            scores['HOLD'] += r_conf * w['regime']
            
        # OU Score
        ou_signals = ou.get('signals', [])
        if ou_signals:
            for s in ou_signals:
                if 'LONG' in s['type']: scores['BUY'] += s['confidence'] * w['ou']
                elif 'SHORT' in s['type']: scores['SELL'] += s['confidence'] * w['ou']
        else:
            scores['HOLD'] += 0.5 * w['ou']
            
        final_action = max(scores, key=scores.get)
        final_conf = scores[final_action]
        
        return final_action, float(final_conf), scores

    def _create_trading_plan(self, action, confidence, vol_data, df):
        if action == 'HOLD': return {'action': 'HOLD'}
        
        current_price = float(df['Close'].iloc[-1])
        vol = vol_data.get(self.ticker, {}).get('realized_vol', 0.2)
        
        # Position Sizing
        pos_info = self.vol_sizer.calculate_position_size(vol)
        
        # Stop Loss (ATR based)
        atr_val = self.momentum_system.calculate_atr(df)
        
        if action == 'BUY':
            sl = current_price - (2 * atr_val)
            tp = current_price + (3 * atr_val)
            strategy = "BULL CALL SPREAD"
        else:
            sl = current_price + (2 * atr_val)
            tp = current_price - (3 * atr_val)
            strategy = "BEAR PUT SPREAD"
            
        return {
            'action': action,
            'entry': current_price,
            'sl': float(sl),
            'tp': float(tp),
            'size': pos_info,
            'strategy': strategy
        }

    def _save_decision(self, decision, plan):
        os.makedirs('trading_decisions', exist_ok=True)
        filename = f"trading_decisions/{datetime.now().strftime('%Y%p%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump({'decision': decision, 'plan': plan}, f, indent=2)

    def _print_decision_summary(self, decision, plan):
        print(f"\n{'='*80}")
        print(f"[DECISION] FINAL DECISION: {decision['action']} (Confidence: {decision['confidence']:.1%})")
        print(f"{'='*80}")
        if plan.get('action') != 'HOLD':
            print(f"   Entry Level: INR {plan['entry']:.2f}")
            print(f"   Stop Loss:   INR {plan['sl']:.2f}")
            print(f"   Target:      INR {plan['tp']:.2f}")
            print(f"   Strategy:    {plan['strategy']}")
            print(f"   Pos Size:    INR {plan['size']['position_value']:,.2f}")
        else:
            print("   Action: No clear trade. Staying in cash.")
        print(f"{'='*80}\n")
