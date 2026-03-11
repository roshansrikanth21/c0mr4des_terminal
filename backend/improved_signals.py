import pandas as pd
import numpy as np
from backend.market_data import calculate_sma, calculate_rsi, calculate_atr
from backend.intraday_utils import calculate_vwap, load_params

class EnhancedTradeSignals:
    def __init__(self, ticker="^NSEI"):
        self.ticker = ticker
        self.params = load_params()

    def get_precise_entry_levels(self, df, interval="5m"):
        """
        Generate precise entry levels based on enhanced signal logic.
        Returns a list of potential trade setups.
        """
        # Handle MultiIndex columns (common with yfinance)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = df.columns.get_level_values(0)

        signals = []
        
        # Ensure indicators are calculated
        if 'SMA21' not in df.columns:
            df['SMA21'] = calculate_sma(df['Close'], 21)
        if 'SMA9' not in df.columns:
            df['SMA9'] = calculate_sma(df['Close'], 9)
        if 'RSI' not in df.columns:
            df['RSI'] = calculate_rsi(df['Close'], 9)
        if 'VWAP' not in df.columns or df['VWAP'].isnull().all():
             # Basic VWAP calculation if missing
             df['VWAP'] = calculate_vwap(df['High'], df['Low'], df['Close'], df['Volume'])
        if 'ATR' not in df.columns:
            df['ATR'] = calculate_atr(df['High'], df['Low'], df['Close'], 14)
            
        # Iterate over the last few candles to find active signals
        # For simplicity, we check the latest candle logic
        # In a real scenario, this might scan historical data too
        
        i = -1 # Latest candle
        
        try:
            price = df['Close'].iloc[i]
            high = df['High'].iloc[i]
            low = df['Low'].iloc[i]
            
            s21 = df['SMA21'].iloc[i]
            r_val = df['RSI'].iloc[i]
            vwap_val = df['VWAP'].iloc[i]
            atr_val = df['ATR'].iloc[i]
            
            # --- STRATEGY 1: VWAP Pullback ---
            # Logic: Uptrend (Price > SMA21), Pullback (Price < VWAP), Oversold (RSI < Threshold)
            if price > s21 and price < vwap_val and r_val < self.params.get('rsi_entry', 45):
                 signals.append({
                    "type": "vwap_pullback",
                    "entry_price": price,
                    "stop_loss": price - (1.5 * atr_val),
                    "target": price + (2.0 * 1.5 * atr_val),
                    "confidence": 0.75,
                    "risk_reward": 2.0,
                    "timestamp": df.index[i].isoformat()
                 })

            # --- STRATEGY 2: Breakout ---
            # Logic: Price closed above recent high (e.g. last 20 candles) with volume spike
            # Simplified here
            recent_high = df['High'].iloc[-20:-1].max()
            if price > recent_high:
                 signals.append({
                    "type": "breakout",
                    "entry_price": price,
                    "stop_loss": price - (1.0 * atr_val),
                    "target": price + (2.5 * atr_val),
                    "confidence": 0.80,
                    "risk_reward": 2.5,
                    "timestamp": df.index[i].isoformat()
                 })
                 
            # --- STRATEGY 3: Support Bounce (Oversold) ---
            # Logic: RSI < 30 and Price > SMA9 (recovering)
            if r_val < 30 and price > df['SMA9'].iloc[i]:
                 signals.append({
                    "type": "sr_bounce",
                    "entry_price": price,
                    "stop_loss": price - (1.2 * atr_val),
                    "target": price + (2.2 * 1.2 * atr_val),
                    "confidence": 0.65,
                    "risk_reward": 2.2,
                    "timestamp": df.index[i].isoformat()
                 })

        except Exception as e:
            print(f"Error generating signals: {e}")
            
        return signals
