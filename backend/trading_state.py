import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

STATE_FILE = "trading_state.json"

def load_state() -> Dict[str, Any]:
    """Load trading state from JSON file"""
    if not os.path.exists(STATE_FILE):
        return {
            "positions": {},  # ticker -> {entry_price, quantity, entry_date, stop_loss, take_profit, highest_high}
            "daily_stats": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "trades_today": 0,
                "pnl_today": 0.0,
                "consecutive_losses": 0,
                "consecutive_wins": 0
            },
            "total_capital": 100000.0  # Starting capital in INR
        }
    
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            # Reset daily stats if new day
            if state["daily_stats"]["date"] != datetime.now().strftime("%Y-%m-%d"):
                state["daily_stats"] = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "trades_today": 0,
                    "pnl_today": 0.0,
                    "consecutive_losses": state["daily_stats"].get("consecutive_losses", 0),
                    "consecutive_wins": state["daily_stats"].get("consecutive_wins", 0)
                }
            return state
    except Exception as e:
        print(f"Error loading state: {e}")
        return load_state()  # Return default

def save_state(state: Dict[str, Any]):
    """Save trading state to JSON file"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving state: {e}")

def get_position(ticker: str) -> Optional[Dict[str, Any]]:
    """Get current position for a ticker"""
    state = load_state()
    return state["positions"].get(ticker)

def open_position(ticker: str, entry_price: float, quantity: int, stop_loss: float, take_profit: float):
    """Open a new position"""
    state = load_state()
    state["positions"][ticker] = {
        "entry_price": entry_price,
        "quantity": quantity,
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "highest_high": entry_price  # For trailing stop
    }
    state["daily_stats"]["trades_today"] += 1
    save_state(state)

def close_position(ticker: str, exit_price: float, reason: str) -> float:
    """Close a position and return P&L"""
    state = load_state()
    position = state["positions"].get(ticker)
    
    if not position:
        return 0.0
    
    # Calculate P&L
    pnl = (exit_price - position["entry_price"]) * position["quantity"]
    
    # Update stats
    state["daily_stats"]["pnl_today"] += pnl
    state["total_capital"] += pnl
    
    if pnl > 0:
        state["daily_stats"]["consecutive_wins"] += 1
        state["daily_stats"]["consecutive_losses"] = 0
    else:
        state["daily_stats"]["consecutive_losses"] += 1
        state["daily_stats"]["consecutive_wins"] = 0
    
    # Remove position
    del state["positions"][ticker]
    save_state(state)
    
    return pnl

def update_trailing_stop(ticker: str, current_price: float, new_stop: float):
    """Update trailing stop for a position"""
    state = load_state()
    if ticker in state["positions"]:
        # Update highest high
        if current_price > state["positions"][ticker]["highest_high"]:
            state["positions"][ticker]["highest_high"] = current_price
        
        # Only trail stop up, never down
        if new_stop > state["positions"][ticker]["stop_loss"]:
            state["positions"][ticker]["stop_loss"] = new_stop
        
        save_state(state)

def calculate_position_size(capital: float, entry_price: float, stop_loss: float, risk_percent: float = 0.01) -> int:
    """
    Calculate position size using fixed fractional method
    
    Args:
        capital: Total capital available
        entry_price: Entry price per share
        stop_loss: Stop loss price per share
        risk_percent: % of capital to risk (default 1%)
    
    Returns:
        Number of shares to buy
    """
    risk_amount = capital * risk_percent
    risk_per_share = abs(entry_price - stop_loss)
    
    if risk_per_share == 0:
        return 0
    
    quantity = int(risk_amount / risk_per_share)
    
    # Ensure we don't exceed capital
    max_quantity = int(capital / entry_price)
    return min(quantity, max_quantity)

def can_trade() -> tuple[bool, str]:
    """
    Check if trading is allowed based on risk rules
    
    Returns:
        (allowed, reason)
    """
    state = load_state()
    stats = state["daily_stats"]
    
    # Max 3 trades per day
    if stats["trades_today"] >= 3:
        return False, "Daily trade limit reached (3)"
    
    # Max 5% daily loss
    max_daily_loss = state["total_capital"] * 0.05
    if stats["pnl_today"] < -max_daily_loss:
        return False, f"Daily loss limit exceeded ({stats['pnl_today']:.2f})"
    
    # Stop after 3 consecutive losses
    if stats["consecutive_losses"] >= 3:
        return False, "3 consecutive losses - trading halted"
    
    # Max 3 concurrent positions
    if len(state["positions"]) >= 3:
        return False, "Maximum concurrent positions (3)"
    
    return True, "Trading allowed"

def get_stats() -> Dict[str, Any]:
    """Get current trading statistics"""
    state = load_state()
    return {
        "capital": state["total_capital"],
        "positions_count": len(state["positions"]),
        "daily_pnl": state["daily_stats"]["pnl_today"],
        "trades_today": state["daily_stats"]["trades_today"],
        "consecutive_losses": state["daily_stats"]["consecutive_losses"],
        "consecutive_wins": state["daily_stats"]["consecutive_wins"]
    }
