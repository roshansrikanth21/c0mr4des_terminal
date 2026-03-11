import yfinance as yf
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, period=20):
    return series.ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def get_market_intelligence(ticker: str, period: str = "1y", interval: str = "1d"):
    """
    Fetches 'Hard Data' to ground the AI's visual analysis.
    Returns a dictionary of technical facts (Trend, Momentum, Volatility).
    """
    try:
        # Fetch Data
        df = yf.download(ticker, period=period, interval=interval, progress=False, group_by='ticker')
        if df.empty:
            return {"error": f"No data found for {ticker}"}
            
        if isinstance(df.columns, pd.MultiIndex):
            if ticker in df.columns.levels[0]:
                df = df[ticker]
            else:
                df.columns = df.columns.get_level_values(0)
            
        if df.empty or len(df) < 50:
            return {"error": "Not enough data"}

        # --- 1. Trend Identification ---
        # EMA 50, 200
        df['EMA_50'] = calculate_ema(df['Close'], 50)
        df['EMA_200'] = calculate_ema(df['Close'], 200)
        
        current_price = df['Close'].iloc[-1]
        ema_200 = df['EMA_200'].iloc[-1]
        ema_50 = df['EMA_50'].iloc[-1]
        
        trend = "NEUTRAL"
        if current_price > ema_200:
            trend = "BULLISH (Above 200 EMA)"
            if ema_50 > ema_200:
                trend += " & STRONG (Golden Cross Logic)"
        else:
            trend = "BEARISH (Below 200 EMA)"
            if ema_50 < ema_200:
                trend += " & WEAK (Death Cross Logic)"

        # --- 2. Momentum (RSI) ---
        df['RSI'] = calculate_rsi(df['Close'], 14)
        rsi = df['RSI'].iloc[-1]
        rsi_state = "Neutral"
        if rsi > 70: rsi_state = "Overbought (Potential Reversal/Pullback)"
        elif rsi < 30: rsi_state = "Oversold (Potential Bounce)"
        elif rsi > 50: rsi_state = "Bullish Momentum"
        else: rsi_state = "Bearish Momentum"

        # --- 3. Volatility (ATR) ---
        df['ATR'] = calculate_atr(df, 14)
        atr = df['ATR'].iloc[-1]
        
        # --- 4. Structure (Recent Highs/Lows) ---
        recent_high = df['High'].iloc[-20:].max()
        recent_low = df['Low'].iloc[-20:].min()
        
        structure = "Consolidation"
        if current_price >= recent_high * 0.98:
            structure = "Testing Highs (Breakout Watch)"
        elif current_price <= recent_low * 1.02:
            structure = "Testing Lows (Breakdown Watch)"

        return {
            "current_price": round(current_price, 2),
            "trend": trend,
            "momentum_rsi": f"{round(rsi, 1)} ({rsi_state})",
            "volatility_atr": round(atr, 2),
            "structure": structure,
            "key_levels": {
                "200_ema": round(ema_200, 2),
                "50_ema": round(ema_50, 2),
                "recent_high": round(recent_high, 2),
                "recent_low": round(recent_low, 2)
            }
        }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Test
    print(get_market_intelligence("RELIANCE.NS"))
