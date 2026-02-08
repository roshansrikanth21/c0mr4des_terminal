"""
Backtesting Engine for Intraday Options Strategy
Simulates trades on historical data to verify strategy performance.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import uuid
from backend.market_data import calculate_sma, calculate_rsi, calculate_atr
from backend.intraday_utils import calculate_vwap, load_params

class Backtester:
    def __init__(self, ticker="^NSEI", interval="5m", period="5d", initial_capital=100000):
        self.ticker = ticker
        self.interval = interval
        self.period = period
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.trades = []
        self.data = None
        self.is_simulation = False
        
    def fetch_data(self):
        """Fetch historical data from Yahoo Finance or Fallback to Synthetic"""
        print(f"Fetching {self.period} of {self.interval} data for {self.ticker}...")
        try:
            # Use Ticker.history as it proved more reliable in testing
            ticker_obj = yf.Ticker(self.ticker)
            self.data = ticker_obj.history(period=self.period, interval=self.interval)
            
            # Additional check for empty data despite no error
            if self.data is None or self.data.empty:
                raise ValueError("Empty data returned")
                
            # History already has SingleIndex columns, no need for MultiIndex check usually
            # But just in case
            if isinstance(self.data.columns, pd.MultiIndex):
                self.data.columns = self.data.columns.get_level_values(0)
                
            print(f"Live data fetched: {len(self.data)} records")
            self.is_simulation = False # Confirm real data

        except Exception as e:
            print(f"Live data fetch failed: {e}. Switching to SIMULATION MODE.")
            self.data = self.generate_synthetic_data()
            self.is_simulation = True

        # Calculate indicators
        self.data['SMA9'] = calculate_sma(self.data['Close'], 9)
        self.data['SMA21'] = calculate_sma(self.data['Close'], 21)
        self.data['RSI'] = calculate_rsi(self.data['Close'], 9)
        self.data['VWAP'] = calculate_vwap(self.data['High'], self.data['Low'], self.data['Close'], self.data['Volume'])
        self.data['ATR'] = calculate_atr(self.data['High'], self.data['Low'], self.data['Close'], 14)
        
        # Clean NaN values
        self.data.dropna(inplace=True)

    def generate_synthetic_data(self):
        """Generate realistic synthetic 15-minute intraday data for simulation"""
        dates = pd.date_range(end=datetime.now(), periods=500, freq="15min") # Approx 1-2 months
        base_price = 24000.0 # Niftyish
        volatility = 0.002 # 0.2% per 15 min
        
        close_prices = [base_price]
        for _ in range(len(dates)-1):
            change = np.random.normal(0, volatility)
            close_prices.append(close_prices[-1] * (1 + change))
            
        df = pd.DataFrame(index=dates)
        df['Close'] = close_prices
        
        # Synthesize OHLCV
        df['Open'] = df['Close'].shift(1).fillna(base_price)
        # Add some noise for High/Low
        noise = np.random.normal(0, volatility/2, len(df))
        df['High'] = df[['Open', 'Close']].max(axis=1) * (1 + abs(noise))
        df['Low'] = df[['Open', 'Close']].min(axis=1) * (1 - abs(noise))
        df['Volume'] = np.random.randint(100000, 5000000, size=len(df))
        
        return df
        
    def run(self):
        """Run the simulation candle by candle"""
        in_position = False
        entry_price = 0
        stop_loss = 0
        take_profit = 0
        entry_time = None
        
        # Load learned parameters
        PARAMS = load_params()
        rsi_entry = PARAMS.get('rsi_entry', 45) # Default 45
        sma_period = PARAMS.get('sma_period', 21) # Default 21
        
        print(f"DEBUG: Backtest running with RSI < {rsi_entry} and SMA {sma_period}")
        
        # Ensure Dynamic SMA is calculated
        sma_col = f'SMA{sma_period}'
        if sma_col not in self.data.columns:
             self.data[sma_col] = calculate_sma(self.data['Close'], sma_period)
        
        for i in range(len(self.data)):
            candle = self.data.iloc[i]
            price = candle['Close']
            time = self.data.index[i]
            
            # Skip if indicators aren't ready
            if pd.isna(candle[sma_col]) or pd.isna(candle['VWAP']):
                continue
                
            # --- SIGNAL LOGIC (Matches intraday_utils.py) ---
            
            # ENTRY Condition: VWAP Pullback
            # Price > SMA (Uptrend), Price < VWAP (Dip), RSI < Learned Threshold
            if not in_position:
                if price > candle[sma_col] and price < candle['VWAP'] and candle['RSI'] < rsi_entry:
                    entry_price = price
                    entry_time = time
                    # Logic: Buy ATM Option
                    # Simulated Option Premium approx 0.5 * ATR (rough proxy for delta/gamma impact on short term)
                    # For simplicity, we simulate the UNDERLYING movement times Delta 0.5
                    
                    stop_loss = price - (1.5 * candle['ATR'])
                    take_profit = price + (2 * (price - stop_loss)) # 1:2 Risk Reward
                    
                    in_position = True
                    # print(f"[{time}] BUY at {price:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}")
            
            # EXIT Conditions
            elif in_position:
                exit_price = 0
                reason = ""
                
                # 1. Stop Loss Hit
                if candle['Low'] <= stop_loss:
                    exit_price = stop_loss
                    reason = "Stop Loss"
                
                # 2. Take Profit Hit
                elif candle['High'] >= take_profit:
                    exit_price = take_profit
                    reason = "Take Profit"
                
                # 3. Trend Broken (Price below SMA9 and VWAP)
                elif price < candle['SMA9'] and price < candle['VWAP']:
                    exit_price = price
                    reason = "Trend Broken"
                    
                # 4. Market Close (Simulated 3:15 PM)
                # Timestamp handling depends on pandas index type (DatetimeIndex)
                elif time.hour >= 15:
                     exit_price = price
                     reason = "Market Close"
                
                if exit_price > 0:
                    # Calculate P&L
                    # Assuming we bought 1 Lot (Nifty 25 qty, BankNifty 15 qty)
                    # Delta approx 0.5 for ATM option
                    points_gained = exit_price - entry_price
                    option_points = points_gained * 0.5
                    
                    lot_size = 25 if "NSEI" in self.ticker else 15
                    pnl = option_points * lot_size
                    
                    self.balance += pnl
                    self.trades.append({
                        "entry_time": entry_time,
                        "exit_time": time,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "reason": reason,
                        "pnl": pnl
                    })
                    
                    in_position = False
                    # print(f"[{time}] SELL at {exit_price:.2f} ({reason}) | P&L: {pnl:.2f}")

    def get_results(self):
        # Default empty structure
        results = {
            "period": self.period,
            "interval": self.interval,
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "final_balance": float(round(self.balance, 2)),
            "trades": []
        }

        if not self.trades:
            return results
            
        df_trades = pd.DataFrame(self.trades)
        wins = df_trades[df_trades['pnl'] > 0]
        losses = df_trades[df_trades['pnl'] <= 0]
        
        win_rate = (len(wins) / len(df_trades)) * 100
        total_pnl = df_trades['pnl'].sum()
        avg_win = wins['pnl'].mean() if not wins.empty else 0
        avg_loss = losses['pnl'].mean() if not losses.empty else 0
        profit_factor = abs(wins['pnl'].sum() / losses['pnl'].sum()) if not losses.empty and losses['pnl'].sum() != 0 else 0.0
        
        # Convert trades to JSON-friendly format
        json_trades = []
        for t in self.trades:
            json_trades.append({
                "entry_time": t["entry_time"].isoformat() if hasattr(t["entry_time"], 'isoformat') else str(t["entry_time"]),
                "exit_time": t["exit_time"].isoformat() if hasattr(t["exit_time"], 'isoformat') else str(t["exit_time"]),
                "entry_price": float(t["entry_price"]),
                "exit_price": float(t["exit_price"]),
                "reason": str(t["reason"]),
                "pnl": float(t["pnl"])
            })

        # Calculate Advanced Metrics
        if not df_trades.empty:
            returns = df_trades['pnl'] / df_trades['entry_price']
            
            # Simple Annualization Factor (assuming 252 trading days) - approximation
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() != 0 else 0
            
            downside_returns = returns[returns < 0]
            sortino = (returns.mean() / downside_returns.std()) * np.sqrt(252) if not downside_returns.empty and downside_returns.std() != 0 else 0
            
            cumulative = (1 + returns).cumprod()
            max_dd = 0
            calmar = 0
            if not cumulative.empty:
                max_dd = (cumulative / cumulative.expanding().max() - 1).min()
                calmar = returns.mean() / abs(max_dd) if max_dd != 0 else 0
            
            expectancy = (returns > 0).mean() * returns[returns > 0].mean() + \
                         (returns <= 0).mean() * returns[returns <= 0].mean()
            expectancy = float(expectancy) if not pd.isna(expectancy) else 0.0
            
        else:
            sharpe = sortino = calmar = max_dd = expectancy = 0.0

        return {
            "period": self.period,
            "interval": self.interval,
            "total_trades": int(len(df_trades)),
            "win_rate": float(round(win_rate, 2)),
            "total_pnl": float(round(total_pnl, 2)),
            "profit_factor": float(round(profit_factor, 2)),
            "avg_win": float(round(avg_win, 2)),
            "avg_loss": float(round(avg_loss, 2)),
            "final_balance": float(round(self.balance, 2)),
            "sharpe_ratio": float(round(sharpe, 2)),
            "sortino_ratio": float(round(sortino, 2)),
            "calmar_ratio": float(round(calmar, 2)),
            "max_drawdown": float(round(max_dd, 4)),
            "expectancy": float(round(expectancy, 4)),
            "is_simulation": self.is_simulation,
            "run_id": str(uuid.uuid4()),
            "trades": json_trades
        }

if __name__ == "__main__":
    # Test run
    tester = Backtester(ticker="^NSEI", period="59d", interval="15m") # 59d is max for 15m in yfinance
    tester.fetch_data()
    tester.run()
    results = tester.get_results()
    print("\n--- BACKTEST RESULTS (NIFTY 50 - Last 60 Days - 15m) ---")
    for k, v in results.items():
        print(f"{k}: {v}")
