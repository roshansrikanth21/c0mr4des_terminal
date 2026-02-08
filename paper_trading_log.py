
import json
import os
from datetime import datetime
import pytz

class PaperTradeLogger:
    def __init__(self):
        self.trades = []
        self.file_path = "paper_trades.json"
        
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    self.trades = json.load(f)
            except:
                self.trades = []
    
    def log_trade(self, trade_data):
        """Log a paper trade"""
        trade = {
            "id": f"PT{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            **trade_data
        }
        
        self.trades.append(trade)
        self._save_to_file()
        
        print(f"📝 Trade Logged: {trade['id']}")
        print(f"   Type: {trade.get('type', 'N/A')}")
        print(f"   Entry: {trade.get('entry_price', 'N/A')}")
        print(f"   Stop: {trade.get('stop_loss', 'N/A')}")
        print(f"   Target: {trade.get('take_profit', 'N/A')}")
        
        return trade
    
    def _save_to_file(self):
        """Save trades to JSON file"""
        with open(self.file_path, 'w') as f:
            json.dump(self.trades, f, indent=2, default=str)
    
    def get_performance(self):
        """Calculate paper trading performance"""
        if not self.trades:
            return {"total_trades": 0, "win_rate": 0, "total_pnl": 0}
        
        # Only count closed trades (with P&L)
        closed_trades = [t for t in self.trades if 'pnl' in t]
        if not closed_trades:
             return {"total_trades": len(self.trades), "win_rate": 0, "total_pnl": 0}

        wins = sum(1 for t in closed_trades if t.get('pnl', 0) > 0)
        total_pnl = sum(t.get('pnl', 0) for t in closed_trades)
        
        return {
            "total_trades": len(closed_trades),
            "wins": wins,
            "losses": len(closed_trades) - wins,
            "win_rate": wins / len(closed_trades) * 100 if closed_trades else 0,
            "total_pnl": total_pnl,
            "avg_win": sum(t.get('pnl', 0) for t in closed_trades if t.get('pnl', 0) > 0) / max(wins, 1),
            "avg_loss": sum(t.get('pnl', 0) for t in closed_trades if t.get('pnl', 0) <= 0) / max(len(closed_trades) - wins, 1)
        }

# Quick usage
if __name__ == "__main__":
    logger = PaperTradeLogger()
    
    # Example trade
    trade = logger.log_trade({
        "symbol": "NIFTY",
        "type": "CE",
        "strike": 22000,
        "entry_price": 120.50,
        "stop_loss": 90.00,
        "take_profit": 180.00,
        "quantity": 50,
        "reason": "Order flow + VWAP pullback",
        "signal_confidence": 0.75
    })
    
    # Later, update with exit
    # In real usage you'd find the trade by ID and update it
    # For this test we just print performance
    
    perf = logger.get_performance()
    print(f"\n📊 Performance: {perf['win_rate']:.1f}% win rate, P&L: {perf['total_pnl']:.2f}")
