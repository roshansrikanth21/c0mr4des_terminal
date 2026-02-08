
import json
import os
import itertools
import pandas as pd
from backend.backtest import Backtester
from backend.market_data import calculate_sma

class StrategyOptimizer:
    def __init__(self, ticker="^NSEI"):
        self.ticker = ticker
        self.best_params = {
            "rsi_entry": 45,
            "sma_period": 21,
            "stop_loss_atr": 1.5,
            "risk_reward": 2.0
        }
        self.results_cache = []

    def optimize(self):
        """
        Run simulations with varying parameters to find the 'Edge'.
        This represents the 'Learning' phase.
        """
        print(f"Starting parameter optimization for {self.ticker}...")
        
        # Hyperparameter Grid
        # Hyperparameter Grid - Expanded for wider learning
        rsi_range = [30, 35, 40, 45, 50, 55, 60]
        sma_range = [9, 14, 21, 50]
        
        best_pnl = -float('inf')
        
        logs = []
        logs.append(f"Starting Grid Search on {self.ticker} over last 59 days...")
        logs.append(f"Testing {len(rsi_range) * len(sma_range)} combinations...")
        
        # Iterate (Grid Search)
        # Note: In a real ML system, we'd use genetic algorithms or optuna
        for rsi in rsi_range:
            for sma in sma_range:
                # Initialize Backtester with specific params
                # We need to modify Backtester to accept these overrides, 
                # or we just subclass it. For now, we will hack it by setting attrs after init
                tester = Backtester(ticker=self.ticker, period="59d", interval="15m")
                
                # Mocking the parameter injection by extending the Backtester class or 
                # modifying the backtest loop. 
                # Ideally, Backtester should accept a 'strategy_config' dict.
                # Let's pivot: We will create a `custom_run` method here that duplicates the logic 
                # BUT uses our dynamic variables.
                
                tester.fetch_data()
                self._run_custom_simulation(tester, rsi, sma)
                
                res = tester.get_results()
                pnl = res['total_pnl']
                
                self.results_cache.append({
                    "rsi": rsi,
                    "sma": sma,
                    "pnl": pnl,
                    "win_rate": res['win_rate']
                })
                
                log_entry = f"Tested [RSI {rsi} | SMA {sma}] -> P&L: {pnl:.2f} | Win Rate: {res['win_rate']}%"
                print(log_entry)
                logs.append(log_entry)
                
                if pnl > best_pnl:
                    best_pnl = pnl
                    self.best_params = {
                        "rsi_entry": rsi,
                        "sma_period": sma,
                        "stop_loss_atr": 1.5,
                        "risk_reward": 2.0,
                        "pnl": pnl # Store expected PnL
                    }
        
        logs.append(f"Optimization Complete. Winner: RSI {self.best_params['rsi_entry']} (P&L: {best_pnl:.2f})")
        self.save_weights()
        return {"best_params": self.best_params, "logs": logs}

    def _run_custom_simulation(self, tester, rsi_threshold, sma_period):
        """
        A copy of the Backtester.run logic but using dynamic parameters
        """
        # Reset trades
        tester.trades = []
        tester.balance = tester.initial_capital
        
        # Calculate the specific SMA required for this test
        col_name = f'SMA{sma_period}'
        tester.data[col_name] = calculate_sma(tester.data['Close'], sma_period)
        
        data = tester.data
        if data is None or data.empty:
            return

        in_position = False
        entry_price = 0
        stop_loss = 0
        take_profit = 0
        entry_time = None
        
        for i in range(len(data)):
            candle = data.iloc[i]
            price = candle['Close']
            time = data.index[i]
            
            # Dynamic SMA check
            if pd.isna(candle[col_name]) or pd.isna(candle['VWAP']):
                continue
            
            sma_val = candle[col_name]
            
            if not in_position:
                # USER THE DYNAMIC RSI THRESHOLD AND SMA
                if price > sma_val and price < candle['VWAP'] and candle['RSI'] < rsi_threshold:
                    entry_price = price
                    entry_time = time
                    stop_loss = price - (1.5 * candle['ATR'])
                    take_profit = price + (2 * (price - stop_loss))
                    in_position = True
            
            elif in_position:
                exit_price = 0
                reason = ""
                
                if candle['Low'] <= stop_loss:
                    exit_price = stop_loss
                    reason = "Stop Loss"
                elif candle['High'] >= take_profit:
                    exit_price = take_profit
                    reason = "Take Profit"
                elif price < candle['SMA9'] and price < candle['VWAP']:
                    exit_price = price
                    reason = "Trend Broken"
                elif time.hour == 15 and time.minute >= 15:
                     exit_price = price
                     reason = "Market Close"
                
                if exit_price > 0:
                    points = exit_price - entry_price
                    # BankNifty/Nifty logic
                    lot_size = 25 if "NSEI" in self.ticker else 15
                    pnl = points * 0.5 * lot_size
                    tester.balance += pnl
                    tester.trades.append({
                        "entry_time": entry_time,
                        "exit_time": time,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "reason": reason
                    })
                    in_position = False

    def save_weights(self):
        """Save the 'Learned' parameters to a JSON file"""
        path = os.path.join(os.path.dirname(__file__), 'model_weights.json')
        with open(path, 'w') as f:
            json.dump(self.best_params, f, indent=4)
        print(f"Model trained. Best parameters saved: {self.best_params}")

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.optimize()
