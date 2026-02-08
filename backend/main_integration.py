"""
Simple integration point with your existing FastAPI app
"""

from fastapi import APIRouter
from backend.advanced_analysis import AdvancedTradingSystem

router = APIRouter(prefix="/api/v2", tags=["advanced_trading"])

# Initialize trading system
trading_system = AdvancedTradingSystem(ticker="^NSEI")

@router.get("/analysis")
async def get_advanced_analysis(interval: str = "5m"):
    """Get complete entry/exit analysis"""
    analysis = trading_system.get_complete_analysis(interval=interval)
    return analysis

@router.post("/enter_trade")
async def enter_trade(
    option_type: str,
    strike: float,
    lot_size: int = 50,
    spot_price: float = None
):
    """Enter a new trade based on analysis"""
    # Get current analysis first
    analysis = trading_system.get_complete_analysis()
    
    if analysis["combined_entry_decision"]["action"] != "ENTRY":
        return {
            "status": "REJECTED",
            "reason": analysis["combined_entry_decision"]["reason"],
            "analysis": analysis
        }
    
    # Enter trade
    trade_params = {
        'entry_price': analysis["current_price"],
        'option_type': option_type,
        'strike': strike,
        'lot_size': lot_size,
        'spot_price': spot_price or analysis["current_price"],
        'iv_at_entry': 0.25  # You'll need to get actual IV
    }
    
    result = trading_system.enter_trade(trade_params)
    result["analysis"] = analysis
    
    return result

@router.get("/exit_recommendations")
async def get_exit_recommendations():
    """Get exit recommendations for all active trades"""
    analysis = trading_system.get_complete_analysis()
    return {
        "active_trades": len(trading_system.active_trades),
        "exit_decisions": analysis.get("exit_decisions", {})
    }
