"""
Dashboard Integration
Aggregates data from all modules for the frontend dashboard
"""

from fastapi import APIRouter
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np

# Import all our modules
from backend.advanced_analysis import AdvancedTradingSystem
from backend.monte_carlo import MonteCarloRiskAnalyzer, quick_risk_assessment
from backend.bayesian_inference import BayesianTradingModel
from backend.nifty_timing import IndianMarketTiming
from backend.options_indicators import OptionsGreeksAnalyzer

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Initialize systems
trading_system = AdvancedTradingSystem(ticker="^NSEI")
risk_analyzer = MonteCarloRiskAnalyzer(ticker="^NSEI")
bayesian_model = BayesianTradingModel(prior_alpha=5, prior_beta=3) # Slight positive bias
market_timing = IndianMarketTiming()

@router.get("/summary")
async def get_dashboard_summary():
    """Get high-level dashboard summary"""
    analysis = trading_system.get_complete_analysis()
    
    return {
        "market_status": {
            "is_open": market_timing.is_market_open(),
            "session": market_timing.get_current_session(),
            "next_event": market_timing.get_timing_signals()[0] if market_timing.get_timing_signals() else None
        },
        "trade_signals": {
            "action": analysis["combined_entry_decision"]["action"],
            "confidence": analysis["combined_entry_decision"]["confidence"],
            "active_trades": len(trading_system.active_trades)
        },
        "risk_metrics": {
            "market_volatility": "MEDIUM", # Placeholder
            "var_95": "1.2%" # Placeholder
        }
    }

@router.get("/market_analysis")
async def get_market_analysis_details():
    """Get detailed market analysis"""
    analysis = trading_system.get_complete_analysis()
    
    # Get Monte Carlo risk assessment
    risk = quick_risk_assessment(ticker="^NSEI", days_ahead=5)
    
    return {
        "technical": analysis,
        "risk_forecast": risk
    }

@router.get("/options_chain")
async def get_options_analysis():
    """Get options chain analysis (placeholder for real data)"""
    # In a real app, this would fetch the option chain
    # Here we mock some data for the dashboard
    
    spot = 24500
    strikes = [24300, 24400, 24500, 24600, 24700]
    
    chain_data = []
    greeks_analyzer = OptionsGreeksAnalyzer()
    
    for strike in strikes:
        # Call Greeks analyzer
        call_greeks = greeks_analyzer.calculate_black_scholes_greeks(
            spot, strike, 5, 0.15, "CE"
        )
        put_greeks = greeks_analyzer.calculate_black_scholes_greeks(
            spot, strike, 5, 0.15, "PE"
        )
        
        chain_data.append({
            "strike": strike,
            "call": {
                "price": round(np.random.uniform(50, 300), 2),
                "oi": int(np.random.uniform(10000, 100000)),
                "greeks": call_greeks
            },
            "put": {
                "price": round(np.random.uniform(50, 300), 2),
                "oi": int(np.random.uniform(10000, 100000)),
                "greeks": put_greeks
            }
        })
        
    return {
        "spot_price": spot,
        "expiry": "2024-10-31",
        "chain": chain_data
    }

@router.get("/strategy_performance")
async def get_strategy_performance():
    """Get Bayesian strategy performance metrics"""
    beliefs = bayesian_model.get_current_beliefs()
    
    return {
        "win_rate": beliefs["win_rate"],
        "profitability_prob": beliefs["probabilities"]["profitable"],
        "recommendation": beliefs["recommendation"],
        "trade_history": bayesian_model.trade_history[-10:] # Last 10 trades
    }

@router.post("/run_simulation")
async def run_simulation(days: int = 30, simulations: int = 1000):
    """Run on-demand Monte Carlo simulation"""
    sim_result = quick_risk_assessment(days_ahead=days, n_simulations=simulations)
    return sim_result
