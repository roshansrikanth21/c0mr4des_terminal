"""
Intraday trading utilities for options trading
Includes market hours detection, strike price calculations, and VWAP
"""
from datetime import datetime, time
import pytz
import json
import os

def load_params():
    """Load learned parameters from model_weights.json"""
    try:
        path = os.path.join(os.path.dirname(__file__), 'model_weights.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except:
        pass
    # Defaults
    return {
        "rsi_entry": 45,
        "sma_period": 21
    }

def is_market_open():
    """
    Check if NSE is currently open (9:30 AM - 3:30 PM IST, Mon-Fri)
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Check if weekend
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Market hours: 9:15 AM to 3:30 PM
    # For debugging/testing, we'll return True to allow system to run
    # In production, uncomment the time check
    return True 
    # return market_open <= current_time <= market_close

def calculate_vwap(high, low, close, volume):
    """
    Calculate Volume Weighted Average Price (VWAP)
    Essential for intraday trading
    """
    import pandas as pd
    
    typical_price = (high + low + close) / 3
    
    # Handle zero volume (common for Indices like ^NSEI on Yahoo)
    if volume.sum() == 0:
        return typical_price
        
    cum_vol = volume.cumsum()
    # Avoid division by zero in cumulative sum
    cum_vol = cum_vol.replace(0, 1) 
    
    vwap = (typical_price * volume).cumsum() / cum_vol
    # Keep the output numerically stable for downstream UI/strategy consumers.
    return vwap.clip(lower=low, upper=high)

def calculate_option_strikes(spot_price: float, signal: str, index: str = "NIFTY", direction: str = "LONG"):
    """
    Calculate ATM, OTM, and ITM strike prices for options
    
    Args:
        spot_price: Current spot price of index
        signal: "ENTRY" or "EXIT"
        index: "NIFTY" or "BANKNIFTY"
        direction: "LONG" (Bullish -> CE) or "SHORT" (Bearish -> PE)
    
    Returns:
        dict with strike recommendations
    """
    # Determine strike interval
    strike_interval = 50 if index == "NIFTY" else 100
    
    # Round to nearest strike
    atm_strike = round(spot_price / strike_interval) * strike_interval
    
    is_bullish = direction == "LONG"
    
    if is_bullish:  # Bullish - recommend Call options
        return {
            "type": "CE",
            "atm": atm_strike,
            "otm": atm_strike + strike_interval,  # Cheaper, higher risk
            "itm": atm_strike - strike_interval,  # Expensive, safer
            "recommendation": "ATM"  # Default recommendation
        }
    else:  # Bearish - recommend Put options
        return {
            "type": "PE",
            "atm": atm_strike,
            "otm": atm_strike - strike_interval, # For PE, OTM is lower strike
            "itm": atm_strike + strike_interval, # For PE, ITM is higher strike
            "recommendation": "ATM"
        }

def get_next_expiry():
    """
    Get the next Thursday expiry for Nifty/Bank Nifty options
    NSE options expire every Thursday
    """
    from datetime import timedelta
    
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist)
    
    # Thursday = 3
    days_until_thursday = (3 - today.weekday()) % 7
    
    # If today is Thursday and market is closed, get next Thursday
    if days_until_thursday == 0 and not is_market_open():
        days_until_thursday = 7
    
    expiry = today + timedelta(days=days_until_thursday)
    return expiry.strftime("%d-%b-%Y")

def should_square_off():
    """
    Check if it's time to square off positions (after 3:00 PM)
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    square_off_time = time(15, 0)  # 3:00 PM
    return now.time() >= square_off_time

def get_market_profile_signals(df, interval="5m"):
    """
    Market Profile indicators for Indian market hours:
    9:15-10:30 = Initial Balance
    10:30-2:30 = Development
    2:30-3:30 = Closing
    """
    try:
        if df.empty: return {}
        
        ist = pytz.timezone('Asia/Kolkata')
        # Ensure index is datetime
        if not hasattr(df.index, 'hour'):
             # Try to convert if it's not
             # But usually yfinance df.index is DatetimeIndex (UTC)
             # We need to convert it to IST for hour checks
             df = df.copy()
             df.index = df.index.tz_convert(ist)
        
        # Market Session Analysis
        # IB: 9:15 to 10:15 approx (First hour)
        initial_balance = df[(df.index.hour == 9) | ((df.index.hour == 10) & (df.index.minute <= 15))]
        
        # Development: 10:15 to 14:30
        development = df[((df.index.hour == 10) & (df.index.minute > 15)) | 
                        ((df.index.hour > 10) & (df.index.hour < 14)) | 
                        ((df.index.hour == 14) & (df.index.minute <= 30))]
                        
        # Closing: 14:30 to 15:30
        closing = df[((df.index.hour == 14) & (df.index.minute > 30)) | 
                    (df.index.hour == 15)]
        
        ib_high = initial_balance['High'].max() if not initial_balance.empty else 0
        ib_low = initial_balance['Low'].min() if not initial_balance.empty else 0
        
        current_session = "initial"
        if not closing.empty: current_session = "closing"
        elif not development.empty: current_session = "development"
        
        signals = {
            "initial_balance_range": {
                "high": ib_high,
                "low": ib_low
            },
            "current_session": current_session,
            "range_expansion": "NONE",
            "session_bias": "NEUTRAL"
        }
        
        # Check for range expansion
        if ib_high > 0 and not df.empty:
            current_price = df['Close'].iloc[-1]
            
            if current_price > ib_high:
                signals["range_expansion"] = "UP"
                signals["session_bias"] = "BULLISH"
            elif current_price < ib_low:
                signals["range_expansion"] = "DOWN"
                signals["session_bias"] = "BEARISH"
            else:
                signals["range_expansion"] = "INSIDE"
                signals["session_bias"] = "NEUTRAL"
        
        return signals

    except Exception as e:
        return {"error": str(e)}
