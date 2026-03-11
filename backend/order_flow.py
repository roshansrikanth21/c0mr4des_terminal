"""
Order Flow Analysis for Indian Markets
Critical for entry timing in Nifty/Sensex options
Enhanced with broker-level institutional flow data
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, time
import pytz
from typing import Optional, Dict

# Import enhanced institutional order flow analyzer
try:
    from backend.institutional_order_flow import InstitutionalOrderFlowAnalyzer
    INSTITUTIONAL_FLOW_AVAILABLE = True
except ImportError:
    INSTITUTIONAL_FLOW_AVAILABLE = False

# Import broker data service for order book access
try:
    from backend.services.market_data_service import async_market_data_service
    import asyncio
    BROKER_DATA_AVAILABLE = True
except ImportError:
    BROKER_DATA_AVAILABLE = False

class OrderFlowAnalyzer:
    def __init__(self, ticker="^NSEI"):
        self.ticker = ticker
        self.vpoc_history = []
        self.support_resistance = {"support": [], "resistance": []}
        
        # Initialize institutional flow analyzer if available
        if INSTITUTIONAL_FLOW_AVAILABLE:
            self.institutional_analyzer = InstitutionalOrderFlowAnalyzer(ticker)
        else:
            self.institutional_analyzer = None
        
    def analyze_candle_structure(self, df):
        """Analyze candle patterns specific to Indian markets"""
        signals = []
        
        if len(df) < 3:
            return signals
            
        for i in range(2, len(df)):
            prev_candle = df.iloc[i-1]
            curr_candle = df.iloc[i]
            
            # Bullish Engulfing
            if (prev_candle['Close'] < prev_candle['Open'] and  # Prev red
                curr_candle['Close'] > curr_candle['Open'] and  # Curr green
                curr_candle['Open'] < prev_candle['Close'] and
                curr_candle['Close'] > prev_candle['Open']):
                signals.append({
                    "time": df.index[i],
                    "pattern": "BULLISH_ENGULFING",
                    "strength": "HIGH"
                })
            
            # Pin Bar (Hammer/Shooting Star)
            body_size = abs(curr_candle['Close'] - curr_candle['Open'])
            upper_wick = curr_candle['High'] - max(curr_candle['Open'], curr_candle['Close'])
            lower_wick = min(curr_candle['Open'], curr_candle['Close']) - curr_candle['Low']
            
            if lower_wick > 2 * body_size and upper_wick < body_size * 0.5:
                signals.append({
                    "time": df.index[i],
                    "pattern": "HAMMER",
                    "strength": "MEDIUM"
                })
            elif upper_wick > 2 * body_size and lower_wick < body_size * 0.5:
                signals.append({
                    "time": df.index[i],
                    "pattern": "SHOOTING_STAR",
                    "strength": "MEDIUM"
                })
        
        return signals[-5:]  # Return last 5 signals
    
    def calculate_volume_profile(self, df, bins=50):
        """Volume Point of Control and Value Area"""
        prices = df['Close'].values
        volumes = df['Volume'].values
        
        if len(prices) < 10:
            return None
            
        min_price = np.min(prices)
        max_price = np.max(prices)
        bin_size = (max_price - min_price) / bins
        
        volume_dict = {}
        for price, volume in zip(prices, volumes):
            bin_idx = int((price - min_price) / bin_size)
            bin_price = min_price + bin_idx * bin_size
            volume_dict[bin_price] = volume_dict.get(bin_price, 0) + volume
        
        if not volume_dict:
            return None
            
        # Find VPOC (Volume Point of Control)
        vpoc_price = max(volume_dict, key=volume_dict.get)
        self.vpoc_history.append(vpoc_price)
        
        # Calculate Value Area (70% of volume)
        sorted_volumes = sorted(volume_dict.items(), key=lambda x: x[1], reverse=True)
        total_volume = sum(volume_dict.values())
        target_volume = total_volume * 0.7
        cumulative = 0
        value_prices = []
        
        for price, vol in sorted_volumes:
            cumulative += vol
            value_prices.append(price)
            if cumulative >= target_volume:
                break
        
        # Find support/resistance clusters
        self._update_support_resistance(df)
        
        return {
            "vpoc": float(vpoc_price),
            "value_area": {
                "high": float(max(value_prices)),
                "low": float(min(value_prices)),
                "mid": float(np.mean(value_prices))
            },
            "current_price": float(prices[-1]),
            "distance_to_vpoc": float(abs(prices[-1] - vpoc_price)),
            "percent_distance": float(abs(prices[-1] - vpoc_price) / vpoc_price * 100),
            "support_levels": self.support_resistance["support"][-3:] if self.support_resistance["support"] else [],
            "resistance_levels": self.support_resistance["resistance"][-3:] if self.support_resistance["resistance"] else []
        }
    
    def _update_support_resistance(self, df):
        """Dynamic support/resistance detection"""
        if len(df) < 20:
            return
            
        # Use swing points
        highs = df['High'].values
        lows = df['Low'].values
        
        for i in range(2, len(df)-2):
            # Swing High
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                if highs[i] not in self.support_resistance["resistance"]:
                    self.support_resistance["resistance"].append(float(highs[i]))
            
            # Swing Low
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                if lows[i] not in self.support_resistance["support"]:
                    self.support_resistance["support"].append(float(lows[i]))
        
        # Keep only recent levels (last 10)
        self.support_resistance["support"] = sorted(self.support_resistance["support"][-10:])
        self.support_resistance["resistance"] = sorted(self.support_resistance["resistance"][-10:])
    
    def get_entry_recommendation(self, df):
        """Generate entry signals based on order flow"""
        volume_profile = self.calculate_volume_profile(df)
        candle_signals = self.analyze_candle_structure(df)
        
        if not volume_profile:
            return {"action": "WAIT", "reason": "Insufficient data"}
        
        current_price = volume_profile["current_price"]
        vpoc = volume_profile["vpoc"]
        
        # Entry logic
        entry_signals = []
        
        # 1. Price near VPOC with bullish candle
        if volume_profile["percent_distance"] < 0.5:  # Within 0.5% of VPOC
            recent_bullish = any(s["pattern"] in ["BULLISH_ENGULFING", "HAMMER"] 
                               for s in candle_signals[-2:])
            if recent_bullish:
                entry_signals.append(("NEAR_VPOC_BULLISH", "Price at high volume zone with bullish pattern"))
        
        # 2. Bounce from support
        if volume_profile["support_levels"]:
            nearest_support = min(volume_profile["support_levels"], 
                                key=lambda x: abs(x - current_price))
            if abs(current_price - nearest_support) / nearest_support < 0.003:  # Within 0.3%
                entry_signals.append(("SUPPORT_BOUNCE", "Bouncing from identified support"))
        
        # 3. Breakout above resistance with volume
        if volume_profile["resistance_levels"]:
            for resistance in volume_profile["resistance_levels"]:
                if current_price > resistance * 1.002:  # 0.2% above resistance
                    # Check for volume confirmation
                    recent_volume = df['Volume'].iloc[-5:].mean()
                    avg_volume = df['Volume'].iloc[-20:].mean()
                    if recent_volume > avg_volume * 1.2:
                        entry_signals.append(("BREAKOUT", f"Breakout above {resistance:.2f} with volume"))
                        break
        
        if entry_signals:
            return {
                "action": "ENTRY",
                "signals": entry_signals,
                "recommended_price": current_price,
                "stop_loss": self._calculate_stop_loss(df, current_price),
                "target": self._calculate_target(df, current_price),
                "confidence": min(len(entry_signals) * 0.3, 0.9)  # Multiple signals increase confidence
            }
        
        return {"action": "WAIT", "reason": "No strong entry signals"}
    
    def _calculate_stop_loss(self, df, entry_price):
        """Dynamic stop loss based on ATR and support"""
        if len(df) < 14:
            return entry_price * 0.99  # 1% stop as default
        
        # Calculate ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Find nearest support
        if self.support_resistance["support"]:
            relevant_supports = [s for s in self.support_resistance["support"] 
                               if s < entry_price]
            if relevant_supports:
                nearest_support = max(relevant_supports)
                return min(entry_price - atr * 1.5, nearest_support * 0.998)
        
        # Default: 1.5 ATR stop
        return entry_price - atr * 1.5
    
    def _calculate_target(self, df, entry_price):
        """Risk:Reward based target"""
        stop_loss = self._calculate_stop_loss(df, entry_price)
        risk = abs(entry_price - stop_loss)
        
        # 2:1 Reward:Risk ratio
        return entry_price + (risk * 2)
    
    async def get_enhanced_entry_recommendation(self, df: pd.DataFrame) -> Dict:
        """
        Enhanced entry recommendation using broker-level order book data
        Combines traditional volume profile with institutional flow analysis
        """
        # Get basic volume profile analysis
        basic_analysis = self.get_entry_recommendation(df)
        
        # If broker data and institutional analyzer available, enhance with order book data
        if BROKER_DATA_AVAILABLE and self.institutional_analyzer:
            try:
                # Get order book from broker
                order_book = await async_market_data_service.get_order_book(self.ticker)
                
                if order_book and (order_book.get('bid') or order_book.get('ask')):
                    # Run institutional flow analysis
                    institutional_flow = self.institutional_analyzer.analyze_comprehensive_flow(order_book, df)
                    
                    # Combine signals
                    enhanced_signals = []
                    enhanced_confidence = basic_analysis.get('confidence', 0.5)
                    
                    # Add institutional flow signals
                    flow_signal = institutional_flow.get('final_signal', {})
                    flow_action = flow_signal.get('action', 'HOLD')
                    flow_conf = flow_signal.get('confidence', 0)
                    
                    if flow_action in ['BUY', 'STRONG_BUY']:
                        enhanced_signals.append(("INSTITUTIONAL_FLOW", "Buying pressure detected"))
                        enhanced_confidence += flow_conf * 0.3
                    elif flow_action in ['SELL', 'STRONG_SELL']:
                        enhanced_signals.append(("INSTITUTIONAL_FLOW", "Selling pressure detected"))
                        enhanced_confidence -= flow_conf * 0.3
                    
                    # Check for large orders
                    large_orders = institutional_flow.get('large_orders', [])
                    if large_orders:
                        buy_orders = [o for o in large_orders if 'BUY' in o.get('type', '')]
                        sell_orders = [o for o in large_orders if 'SELL' in o.get('type', '')]
                        if len(buy_orders) > len(sell_orders):
                            enhanced_signals.append(("LARGE_BUY_ORDERS", f"{len(buy_orders)} institutional buy orders"))
                            enhanced_confidence += 0.15
                        elif len(sell_orders) > len(buy_orders):
                            enhanced_signals.append(("LARGE_SELL_ORDERS", f"{len(sell_orders)} institutional sell orders"))
                            enhanced_confidence -= 0.15
                    
                    # Check absorption
                    absorption = institutional_flow.get('absorption', {})
                    if absorption.get('ask', {}).get('absorbed'):
                        enhanced_signals.append(("ASK_ABSORPTION", "Large ask orders being absorbed (bullish)"))
                        enhanced_confidence += 0.1
                    if absorption.get('bid', {}).get('absorbed'):
                        enhanced_signals.append(("BID_ABSORPTION", "Large bid orders being absorbed (bearish)"))
                        enhanced_confidence -= 0.1
                    
                    # Update basic analysis with enhanced data
                    basic_analysis['signals'] = basic_analysis.get('signals', []) + enhanced_signals
                    basic_analysis['confidence'] = min(max(enhanced_confidence, 0), 1.0)  # Clamp to [0, 1]
                    basic_analysis['institutional_flow'] = institutional_flow
                    basic_analysis['order_book_analysis'] = {
                        'imbalance': institutional_flow.get('order_book_imbalance', {}),
                        'delta': institutional_flow.get('delta', {}),
                        'momentum_shift': institutional_flow.get('momentum_shift', {})
                    }
                    
                    # Upgrade action if institutional flow is strong
                    if flow_action == 'STRONG_BUY' and basic_analysis.get('action') == 'WAIT':
                        basic_analysis['action'] = 'ENTRY'
                        basic_analysis['reason'] = "Strong institutional buying pressure detected"
                    elif flow_action == 'STRONG_SELL' and basic_analysis.get('action') == 'ENTRY':
                        basic_analysis['action'] = 'WAIT'
                        basic_analysis['reason'] = "Strong institutional selling pressure - avoid entry"
                
            except Exception as e:
                print(f"⚠ Enhanced order flow analysis failed: {e}. Using basic analysis.")
        
        return basic_analysis
