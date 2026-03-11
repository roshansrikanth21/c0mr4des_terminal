"""
Global Forex Market Timing System
Handles 24/5 market hours and major trading sessions (Sydney, Tokyo, London, New York)
"""

from datetime import datetime, time, timedelta
import pytz
import pandas as pd
import numpy as np

class GlobalForexTiming:
    def __init__(self):
        self.utc = pytz.UTC
        self.ny_tz = pytz.timezone('America/New_York')
        self.london_tz = pytz.timezone('Europe/London')
        self.tokyo_tz = pytz.timezone('Asia/Tokyo')
        self.sydney_tz = pytz.timezone('Australia/Sydney')
        
        self.last_signal = None
        
    def get_current_session(self):
        """Determine current major forex session(s)"""
        now_utc = datetime.now(self.utc)
        
        sessions = []
        
        # Approximate UTC times for sessions (Standard times, simplified)
        # Sydney: 22:00 - 07:00 UTC
        # Tokyo: 00:00 - 09:00 UTC
        # London: 08:00 - 16:00 UTC
        # New York: 13:00 - 22:00 UTC
        
        current_hour = now_utc.hour
        
        if 22 <= current_hour or current_hour < 7:
            sessions.append("SYDNEY")
        if 0 <= current_hour < 9:
            sessions.append("TOKYO")
        if 8 <= current_hour < 16:
            sessions.append("LONDON")
        if 13 <= current_hour < 22:
            sessions.append("NEW_YORK")
            
        if not sessions:
            # Weekend or gap
            if now_utc.weekday() >= 5:
                return "WEEKEND_CLOSED"
            return "QUIET_HOURS"
            
        return " + ".join(sessions)
            
    def is_market_open(self):
        """Check if forex market is currently open (Sun 5PM NY - Fri 5PM NY)"""
        now_ny = datetime.now(self.ny_tz)
        
        # Closes Friday 17:00 NY
        if now_ny.weekday() == 4 and now_ny.hour >= 17:
            return False
            
        # Closed Saturday
        if now_ny.weekday() == 5:
            return False
            
        # Opens Sunday 17:00 NY
        if now_ny.weekday() == 6 and now_ny.hour < 17:
            return False
            
        return True
    
    def get_timing_signals(self):
        """Get signals based on global sessions and overlaps"""
        if not self.is_market_open():
            return [{
                "time": "CLOSED",
                "event": "MARKET_CLOSED",
                "action": "AVOID",
                "message": "Forex market is currently closed",
                "urgency": "HIGH"
            }]
            
        now_utc = datetime.now(self.utc)
        current_hour = now_utc.hour
        current_session = self.get_current_session()
        
        signals = []
        
        # Session Overlaps (High Volatility)
        # London + New York (13:00 - 16:00 UTC)
        if 13 <= current_hour < 16:
            signals.append({
                "time": "OVERLAP",
                "event": "LONDON_NY_OVERLAP",
                "action": "MOMENTUM",
                "message": "High liquidity and volatility overlap - Best time for trading",
                "urgency": "HIGH"
            })
            
        # Tokyo + London (08:00 - 09:00 UTC)
        elif 8 <= current_hour < 9:
             signals.append({
                "time": "OVERLAP",
                "event": "TOKYO_LONDON_OVERLAP",
                "action": "CONSIDER",
                "message": "European open meets Asian close - Potential breakouts",
                "urgency": "MEDIUM"
            })
            
        # Specific Session Characteristics
        if "LONDON" in current_session and "NEW_YORK" not in current_session:
             signals.append({
                "time": "SESSION",
                "event": "LONDON_SESSION",
                "action": "TREND",
                "message": "London session establishes the trend",
                "urgency": "MEDIUM"
            })
            
        elif "TOKYO" in current_session:
             signals.append({
                "time": "SESSION",
                "event": "ASIAN_SESSION",
                "action": "RANGE",
                "message": "Asian session often range-bound - Look for support/resistance plays",
                "urgency": "LOW"
            })
            
        self.last_signal = signals[-1] if signals else None
        return signals
    
    def should_enter_trade(self):
        """Based on timing, should we enter a new trade?"""
        if not self.is_market_open():
            return False, "Market Closed"
            
        current_session = self.get_current_session()
        
        # Avoid late Friday
        now_ny = datetime.now(self.ny_tz)
        if now_ny.weekday() == 4 and now_ny.hour >= 15:
            return False, "Late Friday - Close out positions"
            
        # Prefer Overlaps
        if "LONDON" in current_session or "NEW_YORK" in current_session:
            return True, "High liquid session"
            
        return True, "Market Open (Lower liquidity)"
    
    def calculate_asian_range(self, df):
        """
        Calculates the Asian Session High/Low (Tokyo Range: 00:00 - 09:00 UTC).
        Critical for Gold and Forex breakouts.
        """
        if df.empty: return None

        # Ensure index is datetime and UTC
        if not isinstance(df.index, pd.DatetimeIndex):
             # Try to convert if it's a column
             if 'timestamp' in df.columns:
                 df = df.set_index(pd.to_datetime(df['timestamp']))
             else:
                 return None
        
        # Localize if naive
        if df.index.tz is None:
            df.index = df.index.tz_localize(self.utc)
        else:
            df = df.tz_convert(self.utc)

        # Filter for today's Asian Session (00:00 - 09:00 UTC)
        today = datetime.now(self.utc).date()
        asian_df = df[
            (df.index.date == today) & 
            (df.index.hour >= 0) & 
            (df.index.hour < 9)
        ]

        if asian_df.empty:
            # Try yesterday if it's early morning
            yesterday = today - timedelta(days=1)
            asian_df = df[
                (df.index.date == yesterday) & 
                (df.index.hour >= 0) & 
                (df.index.hour < 9)
            ]

        if asian_df.empty: return None

        range_high = float(asian_df['high'].max())
        range_low = float(asian_df['low'].min())

        # Check for crossover (Current Price vs Range)
        current_price = float(df['close'].iloc[-1])
        status = "INSIDE"
        if current_price > range_high: status = "BULLISH_BREAKOUT"
        if current_price < range_low: status = "BEARISH_BREAKOUT"

        return {
            "high": range_high,
            "low": range_low,
            "status": status,
            "description": "Asian Session Range (00:00 - 09:00 UTC)"
        }
    
    def _add_minutes(self, t, minutes):
        """Add minutes to a time object"""
        dummy_date = datetime(2024, 1, 1, t.hour, t.minute)
        new_time = dummy_date + timedelta(minutes=minutes)
        return new_time.time()
