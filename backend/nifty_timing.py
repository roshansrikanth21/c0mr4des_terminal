"""
Indian Market Specific Timing System
Critical for Nifty/Sensex options trading
"""

from datetime import datetime, time, timedelta
import pytz
import pandas as pd
import numpy as np

class IndianMarketTiming:
    def __init__(self):
        self.ist = pytz.timezone('Asia/Kolkata')
        self.critical_times = self._get_critical_times()
        self.last_signal = None
        
    def _get_critical_times(self):
        """Indian market specific critical times"""
        return {
            time(9, 15): {"event": "MARKET_OPEN", "action": "AVOID", "duration": 15},
            time(9, 30): {"event": "INITIAL_BALANCE", "action": "WATCH", "duration": 60},
            time(10, 0): {"event": "RBI_ANNOUNCEMENT", "action": "CAUTION", "duration": 30},
            time(10, 30): {"event": "FII_DATA", "action": "HIGH_VOLATILITY", "duration": 15},
            time(11, 0): {"event": "TREND_CONFIRMATION", "action": "CONSIDER", "duration": 120},
            time(13, 0): {"event": "MID_DAY", "action": "LOW_VOLATILITY", "duration": 90},
            time(14, 30): {"event": "DII_DATA", "action": "HIGH_VOLATILITY", "duration": 15},
            time(15, 0): {"event": "LAST_HOUR", "action": "MOMENTUM", "duration": 30},
            time(15, 15): {"event": "OPTIONS_CLOSE", "action": "EXIT", "duration": 15},
            time(15, 30): {"event": "MARKET_CLOSE", "action": "CLOSE_ALL", "duration": 0}
        }
    
    def get_current_session(self):
        """Determine current market session"""
        now = datetime.now(self.ist)
        current_time = now.time()
        
        if now.weekday() >= 5:  # Saturday(5) or Sunday(6)
            return "WEEKEND"
        
        if time(9, 15) <= current_time < time(10, 30):
            return "MORNING_SESSION"
        elif time(10, 30) <= current_time < time(14, 30):
            return "MID_DAY_SESSION"
        elif time(14, 30) <= current_time < time(15, 30):
            return "EVENING_SESSION"
        else:
            return "CLOSED"
            
    def is_market_open(self):
        """Check if market is currently open"""
        session = self.get_current_session()
        return session not in ["CLOSED", "WEEKEND"]
    
    def get_timing_signals(self):
        """Get signals based on Indian market timing"""
        now = datetime.now(self.ist)
        current_time = now.time()
        current_session = self.get_current_session()
        
        signals = []
        
        # Check critical times
        for critical_time, info in self.critical_times.items():
            start_time = critical_time
            end_time = self._add_minutes(start_time, info["duration"])
            
            if start_time <= current_time <= end_time:
                signals.append({
                    "time": start_time.strftime("%H:%M"),
                    "event": info["event"],
                    "action": info["action"],
                    "message": self._get_timing_message(info["event"]),
                    "urgency": self._get_urgency(info["action"])
                })
        
        # Add session-based signals
        session_signals = self._get_session_signals(current_session)
        signals.extend(session_signals)
        
        # Add expiry day signals (Thursday for weekly options)
        if now.weekday() == 3:  # Thursday
            signals.append({
                "time": "ALL_DAY",
                "event": "EXPIRY_DAY",
                "action": "CAUTION",
                "message": "Weekly options expiry - higher volatility, time decay accelerates",
                "urgency": "HIGH"
            })
        
        self.last_signal = signals[-1] if signals else None
        return signals
    
    def _get_session_signals(self, session):
        """Signals specific to each session"""
        signals = []
        
        if session == "MORNING_SESSION":
            signals.append({
                "time": "SESSION",
                "event": "OPENING_RANGE",
                "action": "SETUP",
                "message": "Establish opening range, look for breakouts",
                "urgency": "MEDIUM"
            })
        elif session == "MID_DAY_SESSION":
            signals.append({
                "time": "SESSION",
                "event": "CONSOLIDATION",
                "action": "PATIENCE",
                "message": "Markets often consolidate - wait for clear signals",
                "urgency": "LOW"
            })
        elif session == "EVENING_SESSION":
            signals.append({
                "time": "SESSION",
                "event": "FINAL_MOVE",
                "action": "DECISIVE",
                "message": "Last hour often has decisive moves",
                "urgency": "HIGH"
            })
        
        return signals
    
    def should_enter_trade(self):
        """Based on timing, should we enter a new trade?"""
        now = datetime.now(self.ist)
        current_time = now.time()
        
        # Never enter in first 15 minutes
        if time(9, 15) <= current_time < time(9, 30):
            return False, "Avoid first 15 minutes - too volatile"
        
        # Avoid last 30 minutes for new entries
        if current_time >= time(15, 0):
            return False, "Too late for new entries - market closing soon"
        
        # Avoid around data release times
        if time(10, 25) <= current_time < time(10, 40):  # FII data
            return False, "Avoid FII data release volatility"
        
        if time(14, 25) <= current_time < time(14, 40):  # DII data
            return False, "Avoid DII data release volatility"
        
        # Expiry day: avoid after 2 PM
        if now.weekday() == 3 and current_time >= time(14, 0):
            return False, "Expiry day - avoid new entries after 2 PM"
        
        return True, "Good time for entry"
    
    def calculate_opening_range(self, df):
        """Opening Range Breakout strategy (works well in Indian markets)"""
        if len(df) < 10:
            return None
        
        # Get first 30 minutes (9:15-9:45)
        morning_mask = (df.index.time >= time(9, 15)) & (df.index.time <= time(9, 45))
        opening_data = df[morning_mask]
        
        if opening_data.empty:
            return None
        
        opening_high = opening_data['High'].max()
        opening_low = opening_data['Low'].min()
        opening_range = opening_high - opening_low
        current_price = df['Close'].iloc[-1]
        
        signals = {
            "opening_high": float(opening_high),
            "opening_low": float(opening_low),
            "range": float(opening_range),
            "range_percent": float(opening_range / opening_low * 100),
            "current_position": None,
            "signal": None
        }
        
        # Determine position relative to opening range
        if current_price > opening_high:
            signals["current_position"] = "ABOVE"
            signals["signal"] = "BULLISH_BREAKOUT"
        elif current_price < opening_low:
            signals["current_position"] = "BELOW"
            signals["signal"] = "BEARISH_BREAKOUT"
        else:
            signals["current_position"] = "INSIDE"
            signals["signal"] = "RANGE_BOUND"
        
        # Add targets if breakout
        if signals["signal"] == "BULLISH_BREAKOUT":
            signals["target"] = float(opening_high + opening_range * 0.618)  # Fibonacci extension
            signals["stop_loss"] = float(opening_low)
        elif signals["signal"] == "BEARISH_BREAKOUT":
            signals["target"] = float(opening_low - opening_range * 0.618)
            signals["stop_loss"] = float(opening_high)
        
        return signals
    
    def _add_minutes(self, t, minutes):
        """Add minutes to a time object"""
        dummy_date = datetime(2024, 1, 1, t.hour, t.minute)
        new_time = dummy_date + timedelta(minutes=minutes)
        return new_time.time()
    
    def _get_timing_message(self, event):
        """Human-readable messages for each event"""
        messages = {
            "MARKET_OPEN": "Market just opened - high volatility, avoid new entries",
            "INITIAL_BALANCE": "Initial balance period - establish range",
            "RBI_ANNOUNCEMENT": "Possible RBI announcements - be cautious",
            "FII_DATA": "FII data release - expect volatility",
            "TREND_CONFIRMATION": "Good time for trend confirmation trades",
            "MID_DAY": "Often consolidation period - patience required",
            "DII_DATA": "DII data release - expect volatility",
            "LAST_HOUR": "Last hour - often has decisive moves",
            "OPTIONS_CLOSE": "Options trading stops - exit positions",
            "MARKET_CLOSE": "Market closing - all positions should be closed"
        }
        return messages.get(event, "No specific message")
    
    def _get_urgency(self, action):
        """Determine urgency level"""
        urgency_map = {
            "AVOID": "HIGH",
            "CAUTION": "HIGH",
            "HIGH_VOLATILITY": "HIGH",
            "EXIT": "HIGH",
            "CLOSE_ALL": "HIGH",
            "MOMENTUM": "MEDIUM",
            "CONSIDER": "MEDIUM",
            "WATCH": "LOW",
            "LOW_VOLATILITY": "LOW",
            "SETUP": "LOW",
            "PATIENCE": "LOW"
        }
        return urgency_map.get(action, "MEDIUM")
