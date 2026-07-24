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
from backend.ict_smart_money import ICTSmartMoney

try:
    # Shared data service improves speed/accuracy & adds provider fallbacks for backtests
    from backend.services.market_data_service import get_sync_market_data
except ImportError:
    get_sync_market_data = None

class Backtester:
    def __init__(
        self,
        ticker="^NSEI",
        interval="5m",
        period="5d",
        initial_capital=100000,
        slippage_bps: float = 3.0,
        transaction_cost_bps: float = 2.0,
        allow_synthetic: bool = False,
    ):
        self.ticker = ticker
        self.interval = interval
        self.period = period
        self.initial_capital = initial_capital
        self.slippage_bps = float(slippage_bps)
        self.transaction_cost_bps = float(transaction_cost_bps)
        self.allow_synthetic = bool(allow_synthetic)
        self.balance = initial_capital
        self.trades = []
        self.data = None
        self.is_simulation = False
        self.data_source = "unknown"
        self.total_trade_cost = 0.0

    def _prepare_indicators(self):
        """Calculate indicators on self.data and sanitize rows."""
        if self.data is None or self.data.empty:
            return

        if isinstance(self.data.columns, pd.MultiIndex):
            self.data.columns = self.data.columns.get_level_values(0)
        self.data.columns = [str(c).capitalize() for c in self.data.columns]

        # Ensure required OHLCV columns exist.
        required = ["Open", "High", "Low", "Close", "Volume"]
        for col in required:
            if col not in self.data.columns:
                raise ValueError(f"Missing required column for backtest: {col}")

        # Calculate indicators
        self.data['SMA9'] = calculate_sma(self.data['Close'], 9)
        self.data['SMA21'] = calculate_sma(self.data['Close'], 21)
        self.data['RSI'] = calculate_rsi(self.data['Close'], 9)
        self.data['VWAP'] = calculate_vwap(self.data['High'], self.data['Low'], self.data['Close'], self.data['Volume'])
        self.data['ATR'] = calculate_atr(self.data['High'], self.data['Low'], self.data['Close'], 14)

        # Clean NaN values
        self.data.dropna(inplace=True)

    def set_data(self, df: pd.DataFrame, source_label: str = "historical_store"):
        """
        Inject preloaded historical data instead of fetching from providers.
        Useful for deterministic backtests over previously stored market data.
        """
        if df is None or df.empty:
            raise ValueError("Cannot backtest with empty dataframe")
        self.data = df.copy()
        self.is_simulation = False
        self.data_source = source_label
        self._prepare_indicators()
        
    def fetch_data(self):
        """Fetch historical data via shared providers or fallback to Yahoo/Synthetic"""
        print(f"Fetching {self.period} of {self.interval} data for {self.ticker}...")
        try:
            # Use centralized market data service
            from backend.services.market_data_service import get_sync_market_data
            
            if get_sync_market_data is not None:
                self.data = get_sync_market_data(self.ticker, self.period, self.interval)
            else:
                self.data = yf.download(self.ticker, period=self.period, interval=self.interval, progress=False)
                
            if self.data is None or self.data.empty:
                raise ValueError("Empty data returned")
            
            print(f"Live data fetched: {len(self.data)} records")
            self.is_simulation = False  # Confirm real data
            self.data_source = "live_provider"

        except Exception as e:
            if not self.allow_synthetic:
                raise RuntimeError(
                    f"Live data fetch failed for backtest and synthetic fallback is disabled: {e}"
                ) from e
            print(f"Live data fetch failed: {e}. Switching to SIMULATION MODE.")
            self.data = self.generate_synthetic_data()
            self.is_simulation = True
            self.data_source = "synthetic_fallback"

        self._prepare_indicators()

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

        # --- PRE-CALCULATE ICT LEVELS ---
        # We calculate them once for the whole dataset for speed, 
        # but in a real backtest we'd strictly only look at past data.
        # Since FVG detection in our class uses (i-2, i-1, i), it is causal and safe.
        ict = ICTSmartMoney(self.data)
        fvgs = ict.detect_fair_value_gaps()
        obs = ict.detect_order_blocks()
        
        # Convert to easy lookup (e.g., list of active zones)
        # For simplicity in this loop, we will check if price is inside any KNOWN active FVG
        # generated prior to the current candle index.
        
        for i in range(len(self.data)):
            candle = self.data.iloc[i]
            price = candle['Close']
            time = self.data.index[i]
            
            # Skip if indicators aren't ready
            if pd.isna(candle[sma_col]) or pd.isna(candle['VWAP']):
                continue
                
            # --- SIGNAL LOGIC (Matches intraday_utils.py) ---
            
            # CHECK ICT CONFLUENCE
            # Is price inside a Bullish FVG?
            # Filter FVGs that started BEFORE current time
            active_bull_fvgs = [f for f in fvgs if f['type'] == 'bullish' and pd.to_datetime(f['end_time']) < time]
            in_fvg_zone = False
            for f in active_bull_fvgs:
                # If price dipped into FVG zone (Top > Low > Bottom)
                if candle['Low'] <= f['top'] and candle['Low'] >= f['bottom']:
                    in_fvg_zone = True
                    break

            # ENTRY Condition: VWAP Pullback AND (ICT Confluence OR Strong RSI)
            # Price > SMA (Uptrend), Price < VWAP (Dip), RSI < Learned Threshold
            if not in_position:
                basic_signal = price > candle[sma_col] and price < candle['VWAP'] and candle['RSI'] < rsi_entry
                
                # Boost confidence if in FVG
                # Relaxed condition: Just being close to an FVG or Order Block is good enough
                # OR if RSI is extremely oversold (< 30)
                should_enter = basic_signal and (in_fvg_zone or candle['RSI'] < 35) 
                
                # DEBUG PRINT (remove in production)
                # if basic_signal:
                #    print(f"DEBUG [{time}] Potential Signal. In FVG: {in_fvg_zone}, RSI: {candle['RSI']:.2f} -> Enter: {should_enter}")

                if should_enter:
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
                    gross_pnl = option_points * lot_size
                    option_entry_notional = entry_price * lot_size * 0.5
                    option_exit_notional = exit_price * lot_size * 0.5
                    trade_cost = (option_entry_notional + option_exit_notional) * (
                        (self.slippage_bps + self.transaction_cost_bps) / 10000.0
                    )
                    pnl = gross_pnl - trade_cost
                    
                    self.balance += pnl
                    self.total_trade_cost += trade_cost
                    self.trades.append({
                        "entry_time": entry_time,
                        "exit_time": time,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "reason": reason,
                        "gross_pnl": gross_pnl,
                        "trade_cost": trade_cost,
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
            "is_simulation": self.is_simulation,
            "data_source": self.data_source,
            "total_trade_cost": float(round(self.total_trade_cost, 2)),
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
                "gross_pnl": float(t.get("gross_pnl", t["pnl"])),
                "trade_cost": float(t.get("trade_cost", 0.0)),
                "pnl": float(t["pnl"])
            })

        # Calculate Advanced Metrics
        if not df_trades.empty:
            returns = df_trades['pnl'] / df_trades['entry_price']
            
            # Resample to daily returns for Sharpe/Sortino
            df_trades['entry_time'] = pd.to_datetime(df_trades['entry_time'])
            daily_returns = df_trades.groupby(df_trades['entry_time'].dt.date).apply(
                lambda x: sum(x['pnl']) / self.initial_capital
            )
            
            # Simple Annualization Factor (assuming 252 trading days)
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() != 0 else 0
            
            downside_returns = daily_returns[daily_returns < 0]
            sortino = (daily_returns.mean() / downside_returns.std()) * np.sqrt(252) if not downside_returns.empty and downside_returns.std() != 0 else 0
            
            cumulative = (1 + daily_returns).cumprod()
            max_dd = 0
            calmar = 0
            if not cumulative.empty:
                max_dd = (cumulative / cumulative.expanding().max() - 1).min()
                calmar = daily_returns.mean() / abs(max_dd) if max_dd != 0 else 0
            
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
            "total_trade_cost": float(round(self.total_trade_cost, 2)),
            "sharpe_ratio": float(round(sharpe, 2)),
            "sortino_ratio": float(round(sortino, 2)),
            "calmar_ratio": float(round(calmar, 2)),
            "max_drawdown": float(round(max_dd, 4)),
            "expectancy": float(round(expectancy, 4)),
            "is_simulation": self.is_simulation,
            "data_source": self.data_source,
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
