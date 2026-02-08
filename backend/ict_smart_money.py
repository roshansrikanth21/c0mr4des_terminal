import pandas as pd
import numpy as np

def detect_swings(df, window=3):
    """
    Identify Swing Highs and Lows (Fractals).
    A Swing High is a candle high higher than 'window' candles to the left and right.
    """
    df['SwingHigh'] = False
    df['SwingLow'] = False
    
    # We need to look ahead, so we can't do this purely continuously without lag in live mode.
    # For historical analysis:
    for i in range(window, len(df) - window):
        # Swing High
        if df['High'].iloc[i] > df['High'].iloc[i-window:i].max() and \
           df['High'].iloc[i] > df['High'].iloc[i+1:i+window+1].max():
            df.at[df.index[i], 'SwingHigh'] = True
            
        # Swing Low
        if df['Low'].iloc[i] < df['Low'].iloc[i-window:i].min() and \
           df['Low'].iloc[i] < df['Low'].iloc[i+1:i+window+1].min():
            df.at[df.index[i], 'SwingLow'] = True
            
    return df

def detect_fair_value_gaps(df):
    """
    Identify Bullish and Bearish Fair Value Gaps (FVG).
    Condition: 3-candle pattern with no overlap between Candle 1 and 3.
    """
    df['is_fvg_bull'] = False
    df['is_fvg_bear'] = False
    df['fvg_top'] = np.nan
    df['fvg_bottom'] = np.nan
    
    # We start from index 2 (3rd candle)
    for i in range(2, len(df)):
        # Bullish FVG: Low of Candle 3 > High of Candle 1
        low_3 = df['Low'].iloc[i]
        high_1 = df['High'].iloc[i-2]
        
        if low_3 > high_1:
            df.at[df.index[i], 'is_fvg_bull'] = True
            df.at[df.index[i], 'fvg_top'] = low_3
            df.at[df.index[i], 'fvg_bottom'] = high_1
            
        # Bearish FVG: High of Candle 3 < Low of Candle 1
        high_3 = df['High'].iloc[i]
        low_1 = df['Low'].iloc[i-2]
        
        if high_3 < low_1:
            df.at[df.index[i], 'is_fvg_bear'] = True
            df.at[df.index[i], 'fvg_top'] = low_1
            df.at[df.index[i], 'fvg_bottom'] = high_3
            
    return df

def detect_order_blocks(df):
    """
    Identify potential Order Blocks (OB).
    Bullish OB: The last down candle before a structure break (simplified here as strong move).
    """
    # Simple logic for now: Bullish OB = Down candle followed by Bullish Engulfing or FVG
    df['is_ob_bull'] = False
    df['is_ob_bear'] = False
    
    for i in range(2, len(df)):
        # Bullish OB Check
        if df['Close'].iloc[i-1] < df['Open'].iloc[i-1]: # Prev was Red
            if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i] > df['High'].iloc[i-1]: # Curr is Green and breaks high
                df.at[df.index[i-1], 'is_ob_bull'] = True # Mark the PREVIOUS candle as OB
                
    return df

def get_ict_analysis(ticker, period="60d", interval="15m"):
    import yfinance as yf
    
    # Fetch Data
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    if df.empty:
        return []

    # Run Detection
    df = detect_swings(df)
    df = detect_fair_value_gaps(df)
    df = detect_order_blocks(df)
    
    # Format output for JSON
    results = []
    
    # We only send interesting points (Swings, FVGs, OBs) to save bandwidth
    for i in range(len(df)):
        row = df.iloc[i]
        evt = {}
        
        if row['SwingHigh']: evt['type'] = 'SWING_HIGH'
        elif row['SwingLow']: evt['type'] = 'SWING_LOW'
        elif row['is_fvg_bull']: evt['type'] = 'FVG_BULL'
        elif row['is_fvg_bear']: evt['type'] = 'FVG_BEAR'
        
        if evt:
            evt['time'] = df.index[i].strftime('%Y-%m-%d %H:%M')
            evt['price'] = float(row['Close'])
            if 'fvg_top' in row and not pd.isna(row['fvg_top']):
                evt['top'] = float(row['fvg_top'])
                evt['bottom'] = float(row['fvg_bottom'])
            results.append(evt)
            
    return results
