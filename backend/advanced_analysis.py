"""
Master Integration File - Ties Everything Together
Entry and Exit Timing for Indian Options Trading
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

# Import our modules
from backend.order_flow import OrderFlowAnalyzer
from backend.exit_system import DynamicExitSystem
from backend.nifty_timing import IndianMarketTiming
from backend.options_indicators import OptionsGreeksAnalyzer  # You'll create this

class AdvancedTradingSystem:
    def __init__(self, ticker="^NSEI"):
        self.ticker = ticker
        self.order_flow = OrderFlowAnalyzer(ticker)
        self.market_timing = IndianMarketTiming()
        self.active_trades = {}
        
    def get_complete_analysis(self, interval="5m"):
        """Get comprehensive analysis for entry/exit decisions"""
        
        # 1. Fetch data
        df = self._fetch_market_data(interval)
        
        if df.empty:
            return {"error": "No data available"}
        
        # 2. Market timing analysis
        timing_signals = self.market_timing.get_timing_signals()
        should_enter, enter_reason = self.market_timing.should_enter_trade()
        
        # 3. Order flow analysis (Entry signals)
        order_flow_analysis = self.order_flow.get_entry_recommendation(df)
        
        # 4. Opening range analysis
        opening_range = self.market_timing.calculate_opening_range(df)
        
        # 5. Combine all entry signals
        entry_decision = self._combine_entry_signals(
            timing_signals,
            should_enter,
            order_flow_analysis,
            opening_range,
            df
        )
        
        # 6. Check active trades for exits
        exit_decisions = self._check_active_trades(df)
        
        return {
            "timestamp": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            "ticker": self.ticker,
            "current_price": float(df['Close'].iloc[-1]),
            "market_session": self.market_timing.get_current_session(),
            "timing_signals": timing_signals,
            "entry_allowed": should_enter,
            "entry_reason": enter_reason,
            "order_flow_signals": order_flow_analysis,
            "opening_range": opening_range,
            "combined_entry_decision": entry_decision,
            "exit_decisions": exit_decisions,
            "active_trades_count": len(self.active_trades)
        }
    
    def _fetch_market_data(self, interval):
        """Fetch and prepare market data"""
        try:
            # For intraday, get 5 days of data to ensure we have enough
            df = yf.download(self.ticker, period="5d", interval=interval, progress=False)
            
            if df.empty:
                return pd.DataFrame()
            
            # Handle multi-index columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            return df
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            return pd.DataFrame()
    
    def _combine_entry_signals(self, timing_signals, should_enter, 
                              order_flow, opening_range, df):
        """Combine multiple entry signals with confidence scoring"""
        
        if not should_enter:
            return {
                "action": "WAIT",
                "reason": "Market timing not favorable",
                "confidence": 0.0
            }
        
        signals = []
        confidence_score = 0.0
        
        # 1. Order flow signals (weight: 40%)
        if order_flow["action"] == "ENTRY":
            signals.extend(order_flow["signals"])
            confidence_score += 0.4
        
        # 2. Opening range signals (weight: 30%)
        if opening_range and opening_range["signal"] in ["BULLISH_BREAKOUT", "BEARISH_BREAKOUT"]:
            signals.append((f"ORB_{opening_range['signal']}", 
                          f"Opening range breakout detected"))
            confidence_score += 0.3
        
        # 3. Market timing signals (weight: 30%)
        urgent_timing = any(s.get("urgency") == "HIGH" and 
                           s.get("action") in ["CONSIDER", "MOMENTUM"] 
                           for s in timing_signals)
        if urgent_timing:
            signals.append(("TIMING_URGENT", "Favorable market timing"))
            confidence_score += 0.3
        
        # Check for confluence
        if len(signals) >= 2 and confidence_score > 0.6:
            return {
                "action": "ENTRY",
                "signals": signals,
                "confidence": min(confidence_score, 0.95),
                "recommended_price": float(df['Close'].iloc[-1]),
                "stop_loss": order_flow.get("stop_loss") if order_flow["action"] == "ENTRY" 
                            else float(df['Close'].iloc[-1] * 0.99),
                "target": order_flow.get("target") if order_flow["action"] == "ENTRY" 
                         else float(df['Close'].iloc[-1] * 1.02)
            }
        
        return {
            "action": "WAIT",
            "reason": f"Insufficient confluence ({len(signals)} signals, confidence: {confidence_score:.2f})",
            "signals": signals,
            "confidence": confidence_score
        }
    
    def _check_active_trades(self, df):
        """Check all active trades for exit conditions"""
        exit_decisions = {}
        
        for trade_id, trade in self.active_trades.items():
            # Prepare market data for exit system
            market_data = {
                'current_price': float(df['Close'].iloc[-1]),
                'current_time': datetime.now(pytz.timezone('Asia/Kolkata')),
                'spot_price': trade.get('spot_price', float(df['Close'].iloc[-1])),
                'atr': self._calculate_atr(df),
                'iv_current': trade.get('current_iv', 0.2),  # Default IV
                'volume': float(df['Volume'].iloc[-1]),
                'time_to_expiry_hours': trade.get('time_to_expiry_hours', 6)
            }
            
            # Get exit decision
            exit_system = DynamicExitSystem(trade)
            decision = exit_system.evaluate_exit(market_data)
            
            exit_decisions[trade_id] = decision
            
            # If exit recommended, mark trade for closure
            if decision["decision"]["action"] == "EXIT":
                trade["exit_recommended"] = True
                trade["exit_reason"] = decision["decision"]["reason"]
        
        return exit_decisions
    
    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        return float(atr.iloc[-1]) if not atr.empty else float(df['Close'].iloc[-1] * 0.01)
    
    def enter_trade(self, trade_params):
        """Enter a new trade"""
        trade_id = f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Add additional parameters
        trade_params['entry_time'] = datetime.now(pytz.timezone('Asia/Kolkata'))
        trade_params['trade_id'] = trade_id
        
        self.active_trades[trade_id] = trade_params
        
        return {
            "status": "ENTERED",
            "trade_id": trade_id,
            "details": trade_params
        }
    
    def exit_trade(self, trade_id, exit_price):
        """Exit a trade"""
        if trade_id not in self.active_trades:
            return {"status": "ERROR", "message": "Trade not found"}
        
        trade = self.active_trades[trade_id]
        entry_price = trade['entry_price']
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * trade.get('lot_size', 50)
        
        # Remove trade
        del self.active_trades[trade_id]
        
        return {
            "status": "EXITED",
            "trade_id": trade_id,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_percent": (exit_price - entry_price) / entry_price * 100
        }
