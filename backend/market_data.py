import yfinance as yf
import pandas as pd
import numpy as np

def calculate_sma(series, period):
    return series.rolling(window=period).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_adx(high, low, close, period=14):
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr1 = pd.DataFrame(high - low)
    tr2 = pd.DataFrame(abs(high - close.shift(1)))
    tr3 = pd.DataFrame(abs(low - close.shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join='outer').max(axis=1)
    
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period).mean() / atr)
    
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(period).mean()
    return adx

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def calculate_bollinger_bands(series, period=20, std=2):
    sma = series.rolling(window=period).mean()
    rstd = series.rolling(window=period).std()
    upper = sma + (std * rstd)
    lower = sma - (std * rstd)
    return upper, lower

def calculate_atr(high, low, close, period=14):
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr

def get_market_history(ticker: str, period: str = "1y", interval: str = "1d"):
    try:
        # Determine Interval based on Period to optimize data density
        interval = "1d"
        if period in ["1mo", "3mo"]:
            interval = "1h" # Higher resolution for short term
        elif period == "5y" or period == "max":
            interval = "1wk" # Lower resolution for long term
        
        # Fetch data
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        
        if df.empty:
            return []

        # Handle multi-index columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        
        # Calculate Indicators
        sma_50 = calculate_sma(close, 50)
        sma_200 = calculate_sma(close, 200)
        rsi = calculate_rsi(close, 14)
        adx = calculate_adx(high, low, close, 14)
        atr = calculate_atr(high, low, close, 14)
        macd, macd_signal = calculate_macd(close)
        upper_bb, lower_bb = calculate_bollinger_bands(close)
        vol_sma = volume.rolling(window=20).mean()

        history = []
        
        in_position = False
        entry_price = 0
        
        for i in range(len(df)):
            date_obj = df.index[i]
            # Format date based on resolution
            date_str = date_obj.strftime('%Y-%m-%d %H:%M') if interval == "1h" else date_obj.strftime('%Y-%m-%d')
            
            price = float(close.iloc[i])
            s50 = float(sma_50.iloc[i]) if not np.isnan(sma_50.iloc[i]) else None
            s200 = float(sma_200.iloc[i]) if not np.isnan(sma_200.iloc[i]) else None
            r_val = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50
            u_bb = float(upper_bb.iloc[i]) if not np.isnan(upper_bb.iloc[i]) else None
            l_bb = float(lower_bb.iloc[i]) if not np.isnan(lower_bb.iloc[i]) else None
            m_val = float(macd.iloc[i]) if not np.isnan(macd.iloc[i]) else 0
            ms_val = float(macd_signal.iloc[i]) if not np.isnan(macd_signal.iloc[i]) else 0
            adx_val = float(adx.iloc[i]) if not np.isnan(adx.iloc[i]) else 0
            atr_val = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else 0
            vol_val = float(volume.iloc[i]) if not np.isnan(volume.iloc[i]) else 0
            v_sma = float(vol_sma.iloc[i]) if not np.isnan(vol_sma.iloc[i]) else 0
            
            signal = None
            confidence = 0.0
            stop_loss = None
            reason = ""
            
            # Advanced Signal Logic (The "Model")
            if s50 and s200 and atr_val > 0: 
                # ENTRY CONDITIONS:
                # 1. Trend: Above SMA 200 (Long term) OR Above SMA 50 (Med term)
                # 2. Momentum: MACD Bullish Crossover OR RSI Recovery from oversold
                # 3. Strength: ADX > 20 (Trend exists)
                # 4. Volume: Volume > Average Volume (Confirmation) - Optional but boosts confidence
                
                is_uptrend = price > s50
                macd_cross = (m_val > ms_val) and (m_val < 0) # Early entry
                pullback = (price > s200) and (price < s50) and (r_val < 40) # Dip buy
                
                trend_strength = adx_val > 20
                vol_confirmed = vol_val > v_sma
                
                if not in_position:
                    entry_signal = False
                    
                    # Scenario A: Trend Following Breakout
                    if is_uptrend and macd_cross and trend_strength:
                         entry_signal = True
                         reason = "Trend Breakout"
                         confidence = 0.8
                    
                    # Scenario B: Mean Reversion (Dip Buy)
                    elif pullback and r_val < 35:
                         entry_signal = True
                         reason = "Oversold Bounce"
                         confidence = 0.6
                         
                    # Volume Boost
                    if entry_signal and vol_confirmed:
                        confidence += 0.1
                        reason += " + Vol"

                    if entry_signal and confidence > 0.6:
                        signal = "ENTRY"
                        in_position = True
                        entry_price = price
                        # Dynamic Stop Loss: 2 ATR below
                        stop_loss = price - (2 * atr_val)
                        # Take Profit: 2:1 Reward to Risk
                        take_profit = price + (2 * (price - stop_loss))

                # EXIT CONDITIONS:
                # 1. Trend Reversal: Close below SMA 50 (if was trend trade)
                # 2. RSI Overbought: > 75
                # 3. Trailing Stop Breach (Simulated logic here implies standard stop)
                elif in_position:
                    # Calculate current dynamic stop (trailing theoretically) or fixed
                    # For now, let's keep the initial stop to be clear in the UI, or trail it?
                    # Let's trail it: Stop never goes down.
                    current_stop = price - (2 * atr_val)
                    if stop_loss and current_stop > stop_loss:
                         stop_loss = current_stop
                    
                    stop_hit = price < stop_loss if stop_loss else False
                    trend_break = price < s50 and r_val < 50
                    take_profit_hit = price > take_profit if take_profit else False
                    
                    if stop_hit:
                        signal = "EXIT"
                        reason = "Stop Loss Hit"
                        in_position = False
                    elif take_profit_hit:
                        signal = "EXIT"
                        reason = "Take Profit Hit"
                        in_position = False
                    elif trend_break:
                         signal = "EXIT"
                         reason = "Trend Broken"
                         in_position = False

            # Determine explicit "Action" state
            action = "WAIT"
            if signal == "ENTRY":
                action = "ENTER NOW"
            elif signal == "EXIT":
                action = "EXIT NOW"
            elif in_position:
                action = "HOLD"

            history.append({
                "date": date_str,
                "price": price,
                "sma50": s50,
                "sma200": s200,
                "rsi": r_val,
                "upper_bb": u_bb,
                "lower_bb": l_bb,
                "stop_loss": stop_loss if in_position or signal == "ENTRY" else None,
                "take_profit": take_profit if in_position or signal == "ENTRY" else None,
                "confidence": confidence if signal == "ENTRY" else None,
                "reason": reason if signal else None,
                "signal": signal,
                "action": action
            })
            
        return history

    except Exception as e:
        print(f"Error fetching history: {e}")
        return []

def get_market_regime(ticker: str):
    try:
        # Fetch data (enough for 200SMA)
        df = yf.download(ticker, period="2y", interval="1d", progress=False)
        
        if df.empty:
            return {
                "regime": "Range-bound",
                "confidence": 0.0,
                "is_trade_allowed": False,
                "reason": "Data Unavailable",
                "vitals": {"vix": 0, "rsi": 0, "adx": 0}
            }

        # Calculate Indicators
        # Handle multi-index columns if yfinance returns them
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        
        # Simple Moving Averages
        sma_50 = calculate_sma(close, 50)
        sma_200 = calculate_sma(close, 200)
        
        # RSI
        rsi = calculate_rsi(close, 14)
        
        # ADX
        adx = calculate_adx(high, low, close, 14)

        # Get latest values (handle NaN at start of series)
        if len(close) < 200:
             return {
                "regime": "Insufficient Data",
                "confidence": 0.0,
                "is_trade_allowed": False,
                "reason": "Not enough history for 200 SMA",
                "vitals": {"vix": 0, "rsi": 0, "adx": 0}
            }
            
        current_close = close.iloc[-1]
        current_sma_50 = sma_50.iloc[-1]
        current_sma_200 = sma_200.iloc[-1]
        current_rsi = rsi.iloc[-1]
        # Use simple fillna(0) for safety if calculation resulted in NaNs
        current_adx = adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0
        current_rsi = current_rsi if not np.isnan(current_rsi) else 50
        
        # Helper to safely get VIX (India VIX for NSE, regular VIX for others)
        vix_val = 0
        try:
            vix_ticker = "^INDIAVIX" if ticker == "^NSEI" else "^VIX"
            vix_df = yf.download(vix_ticker, period="5d", progress=False)
            if not vix_df.empty:
                 if isinstance(vix_df.columns, pd.MultiIndex):
                    vix_df.columns = vix_df.columns.get_level_values(0)
                 vix_val = vix_df['Close'].iloc[-1]
        except:
            vix_val = 0

        # Regime Logic
        regime = "Range-bound"
        confidence = 0.5
        is_trade_allowed = True
        reason = "Normal market conditions"

        # Definition: Strong Uptrend
        if current_close > current_sma_50 > current_sma_200:
            regime = "Strong Uptrend"
            confidence = 0.8
            if current_adx > 25:
                confidence += 0.1
        
        # Definition: Strong Downtrend
        elif current_close < current_sma_50 < current_sma_200:
            regime = "Strong Downtrend"
            confidence = 0.8
            if current_adx > 25:
                confidence += 0.1

        # Definition: Volatility Expansion (High VIX or high ADX)
        if vix_val > 24 or current_adx > 40:
             regime = "Volatility Expansion"
             confidence = 0.9
             is_trade_allowed = False # Example rule
             reason = "Extreme Volatility"

        # Trade filters
        if current_rsi > 70 and "Uptrend" in regime:
             is_trade_allowed = False
             reason = "Overbought - Wait for pullback"
        
        if current_rsi < 30 and "Downtrend" in regime:
             is_trade_allowed = False
             reason = "Oversold - Wait for bounce"

        return {
            "regime": regime,
            "confidence": min(confidence, 1.0),
            "is_trade_allowed": is_trade_allowed,
            "reason": reason,
            "vitals": {
                "vix": float(round(vix_val, 2)),
                "rsi": float(round(current_rsi, 2)),
                "adx": float(round(current_adx, 2))
            }
        }

    except Exception as e:
        print(f"Error processing data: {e}")
        return {
            "regime": "Range-bound",
            "confidence": 0.0,
            "is_trade_allowed": False,
            "reason": f"Error: {str(e)}",
            "vitals": {"vix": 0, "rsi": 0, "adx": 0}
        }
