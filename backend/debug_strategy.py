
import yfinance as yf
import pandas as pd
import numpy as np
from backend.market_data import calculate_sma, calculate_rsi, calculate_atr
from backend.intraday_utils import calculate_vwap

def debug_strategy():
    print("Fetching REAL Nifty Data...")
    ticker = yf.Ticker("^NSEI")
    data = ticker.history(period="59d", interval="15m")
    
    if data.empty:
        print("ERROR: Data is EMPTY. yfinance download failed.")
        return

    print(f"Data Row Count: {len(data)}")
    print("Columns:", data.columns)
    print("Volume stats:", data['Volume'].describe())
    
    # Calculate Indicators
    data['SMA21'] = calculate_sma(data['Close'], 21)
    data['RSI'] = calculate_rsi(data['Close'], 14) # Standard 14
    
    # VWAP might be the killer if Volume is 0
    try:
        data['VWAP'] = calculate_vwap(data['High'], data['Low'], data['Close'], data['Volume'])
    except Exception as e:
        print(f"VWAP Calc Failed: {e}")
        data['VWAP'] = np.nan
        
    print("NaN counts per column:")
    print(data.isna().sum())
    
    # Drop warmup
    data = data.dropna()
    print(f"Data after indicators: {len(data)} rows")
    
    # Check Min/Max of indicators to see if they EVER reach thresholds
    print("\n--- Market Reality Check ---")
    print(f"RSI Min: {data['RSI'].min():.2f}")
    print(f"RSI Max: {data['RSI'].max():.2f}")
    
    # Check how many times conditions are met INDIVIDUALLY
    # Entry Rule: Price > SMA21 AND Price < VWAP AND RSI < 45
    
    cond_trend = data['Close'] > data['SMA21']
    cond_pullback = data['Close'] < data['VWAP']
    cond_rsi = data['RSI'] < 45
    
    print(f"\n--- Condition Frequency (Last 60 Days) ---")
    print(f"1. Uptrend (Price > SMA21): {cond_trend.sum()} candles")
    print(f"2. Pullback (Price < VWAP): {cond_pullback.sum()} candles")
    print(f"3. Oversold (RSI < 45):     {cond_rsi.sum()} candles")
    
    combined = cond_trend & cond_pullback & cond_rsi
    print(f"ALL COMBINED (Trade Setup): {combined.sum()} POTENTIAL TRADES")
    
    if combined.sum() > 0:
        print("\nSample Trade Timestamps:")
        print(data[combined].index[:5])
    else:
        print("\nCONCLUSION: Strategy is too strict for current market phase.")

if __name__ == "__main__":
    debug_strategy()
