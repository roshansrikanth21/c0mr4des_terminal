from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime

class BaseBroker(ABC):
    """
    Abstract Base Class for all broker implementations.
    Ensures consistent interface for both Paper and Live trading.
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """Authenticate and connect to the broker."""
        pass
        
    @abstractmethod
    def get_quote(self, symbol: str) -> float:
        """Get the latest price (LTP) for a symbol."""
        pass
        
    @abstractmethod
    def place_order(self, 
                   symbol: str, 
                   quantity: int, 
                   side: str,  # "BUY" or "SELL"
                   order_type: str = "MARKET", 
                   price: float = 0.0,
                   stop_loss: float = 0.0,
                   take_profit: float = 0.0) -> Dict:
        """Place an order."""
        pass
        
    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """Get current open positions."""
        pass
        
    @abstractmethod
    def get_orders(self) -> List[Dict]:
        """Get order history."""
        pass
        
    @abstractmethod
    def get_pnl(self) -> float:
        """Get total Realized + Unrealized P&L."""
        pass
