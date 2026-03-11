import logging
from typing import Dict, List
from datetime import datetime
import json
import os
from .base_broker import BaseBroker
import yfinance as yf

class PaperBroker(BaseBroker):
    """
    Paper Trading Simulation Broker.
    Keeps track of positions, orders, and P&L in a local JSON file.
    """
    
    def __init__(self, initial_capital: float = 1000000.0, data_file: str = "paper_trading_data.json"):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.data_file = os.path.join("data", data_file)
        self.positions = {} # {symbol: {quantity, avg_price}}
        self.orders = []
        self._load_state()
        
    def _load_state(self):
        """Load state from disk"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.balance = data.get('balance', self.initial_capital)
                    self.positions = data.get('positions', {})
                    self.orders = data.get('orders', [])
            except Exception as e:
                logging.error(f"Failed to load paper trading data: {e}")
                
    def _save_state(self):
        """Save state to disk"""
        os.makedirs("data", exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump({
                'balance': self.balance,
                'positions': self.positions,
                'orders': self.orders
            }, f, indent=2)

    def connect(self) -> bool:
        """Mock connection"""
        logging.info("Connected to Paper Broker")
        return True
        
    def get_quote(self, symbol: str) -> float:
        """Get mock quote using yfinance or random movement"""
        # For simplicity, fetch live or use last known
        # In simulation loop, this might be passed in
        try:
            # Need to handle Nifty symbols for yf
            yf_symbol = symbol
            if not symbol.endswith('.NS') and not symbol.startswith('^'):
                yf_symbol = f"{symbol}.NS"
                
            ticker = yf.Ticker(yf_symbol)
            todats_data = ticker.history(period='1d')
            if not todats_data.empty:
                return float(todats_data['Close'].iloc[-1])
            return 0.0
        except:
            return 0.0
            
    def place_order(self, symbol: str, quantity: int, side: str, 
                   order_type: str = "MARKET", price: float = 0.0,
                   stop_loss: float = 0.0, take_profit: float = 0.0) -> Dict:
        
        # Determine execution price
        exec_price = price
        if order_type == "MARKET":
            exec_price = self.get_quote(symbol)
            if exec_price == 0:
                return {"status": "REJECTED", "reason": "Could not fetch price"}
        
        cost = exec_price * quantity
        
        if side == "BUY":
            if cost > self.balance:
                return {"status": "REJECTED", "reason": "Insufficient funds"}
            
            self.balance -= cost
            
            # Update position
            if symbol in self.positions:
                curr_qty = self.positions[symbol]['quantity']
                curr_avg = self.positions[symbol]['avg_price']
                new_qty = curr_qty + quantity
                new_avg = ((curr_qty * curr_avg) + cost) / new_qty
                self.positions[symbol] = {'quantity': new_qty, 'avg_price': new_avg}
            else:
                self.positions[symbol] = {'quantity': quantity, 'avg_price': exec_price}
                
        elif side == "SELL":
            if symbol not in self.positions or self.positions[symbol]['quantity'] < quantity:
                 return {"status": "REJECTED", "reason": "Insufficient position"}
            
            self.balance += cost
            
            # Update position
            curr_qty = self.positions[symbol]['quantity']
            new_qty = curr_qty - quantity
            if new_qty == 0:
                del self.positions[symbol]
            else:
                self.positions[symbol]['quantity'] = new_qty
        
        order = {
            "id": f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.orders)}",
            "symbol": symbol,
            "quantity": quantity,
            "side": side,
            "price": exec_price,
            "type": order_type,
            "time": datetime.now().isoformat(),
            "status": "FILLED"
        }
        
        self.orders.append(order)
        self._save_state()
        
        logging.info(f"Paper Order: {side} {quantity} {symbol} @ {exec_price}")
        return order

    def get_positions(self) -> List[Dict]:
        pos_list = []
        for sym, data in self.positions.items():
            current_price = self.get_quote(sym)
            pnl = (current_price - data['avg_price']) * data['quantity']
            pos_list.append({
                "symbol": sym,
                "quantity": data['quantity'],
                "avg_price": data['avg_price'],
                "ltp": current_price,
                "pnl": pnl
            })
        return pos_list
        
    def get_orders(self) -> List[Dict]:
        return self.orders
        
    def get_pnl(self) -> float:
        # Realized P&L is implicitly tracked in balance changes vs initial capital
        # Unrealized P&L is calculated from open positions
        realized_pnl = self.balance - self.initial_capital
        unrealized_pnl = sum([p['pnl'] for p in self.get_positions()])
        return realized_pnl + unrealized_pnl
