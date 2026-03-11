"""
Market Timing Factory
Selects the appropriate timing engine based on the asset class
"""

from backend.nifty_timing import IndianMarketTiming
from backend.forex_timing import GlobalForexTiming

def get_market_timing(ticker: str):
    """
    Factory function to get the correct timing engine
    """
    # Forex Logic
    if "USD" in ticker or "=X" in ticker:
        return GlobalForexTiming()
    
    # Default to Indian Market (Nifty/Sensex/Stocks)
    return IndianMarketTiming()
