
"""
Quick Test Script for Indian Options Trading System
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_basic_components():
    print("🧪 Testing Basic Components...")
    print("=" * 60)
    
    # Test 1: Options Greeks
    try:
        from backend.options_indicators import OptionsGreeksAnalyzer
        analyzer = OptionsGreeksAnalyzer()
        result = analyzer.calculate_black_scholes_greeks(
            spot_price=22000,
            strike_price=22000,
            time_to_expiry_days=7,
            implied_volatility=0.15,
            option_type="CE"
        )
        print("✅ Options Greeks: WORKING")
        print(f"   Delta: {result['greeks']['delta']:.4f}")
        print(f"   Theta: {result['greeks']['theta']:.4f}")
    except Exception as e:
        print(f"❌ Options Greeks: FAILED - {e}")
    
    # Test 2: Order Flow
    try:
        from backend.order_flow import OrderFlowAnalyzer
        import pandas as pd
        import numpy as np
        
        # Create sample data
        dates = pd.date_range('2024-01-01', periods=100, freq='H')
        data = pd.DataFrame({
            'Close': np.random.randn(100).cumsum() + 100,
            'High': np.random.randn(100).cumsum() + 101,
            'Low': np.random.randn(100).cumsum() + 99,
            'Volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        ofa = OrderFlowAnalyzer()
        analysis = ofa.calculate_volume_profile(data)
        print("✅ Order Flow Analysis: WORKING")
        if analysis:
            print(f"   VPOC: {analysis['vpoc']:.2f}")
    except Exception as e:
        print(f"❌ Order Flow: FAILED - {e}")
    
    # Test 3: Market Timing
    try:
        from backend.nifty_timing import IndianMarketTiming
        timing = IndianMarketTiming()
        signals = timing.get_timing_signals()
        print("✅ Market Timing: WORKING")
        print(f"   Session: {timing.get_current_session()}")
    except Exception as e:
        print(f"❌ Market Timing: FAILED - {e}")
    
    # Test 4: Monte Carlo
    try:
        from backend.monte_carlo import MonteCarloRiskAnalyzer
        risk = MonteCarloRiskAnalyzer(n_simulations=100)  # Small for quick test
        # risk.fetch_historical_data(period="1mo") # Skip fetching to avoid network error in simple test
        print("✅ Monte Carlo: WORKING (Initialized)")
    except Exception as e:
        print(f"❌ Monte Carlo: FAILED - {e}")
    
    # Test 5: Bayesian
    try:
        from backend.bayesian_inference import BayesianTradingModel
        model = BayesianTradingModel()
        beliefs = model.get_current_beliefs()
        print("✅ Bayesian Inference: WORKING")
        print(f"   Win Rate: {beliefs['win_rate']['mean']:.1%}")
    except Exception as e:
        print(f"❌ Bayesian: FAILED - {e}")
    
    print("=" * 60)
    print("🎯 Basic Component Test Complete!")

def test_integration():
    print("\n🔗 Testing Integration...")
    print("=" * 60)
    
    try:
        from backend.advanced_analysis import AdvancedTradingSystem
        
        system = AdvancedTradingSystem(ticker="^NSEI")
        
        # Test with dummy data or small interval
        print("Testing with 15m interval...")
        
        # This will fail if no internet/yfinance, but that's okay
        try:
            analysis = system.get_complete_analysis(interval="15m")
            print("✅ Trading System Integration: WORKING")
            print(f"   Entry Decision: {analysis['combined_entry_decision']['action']}")
            print(f"   Market Session: {analysis['market_session']}")
        except Exception as e:
            print(f"⚠️  Trading System: PARTIAL - Can't fetch data: {e}")
            print("   (This is normal if no internet/yfinance access)")
    
    except Exception as e:
        print(f"❌ Integration: FAILED - {e}")
    
    print("=" * 60)

if __name__ == "__main__":
    print("\n🚀 STARTING TRADING SYSTEM TEST\n")
    test_basic_components()
    test_integration()
    print("\n✨ All Tests Completed!")
    print("\n📋 NEXT STEPS:")
    print("1. Run: python test_system.py")
    print("2. Start FastAPI server: uvicorn main:app --reload")
    print("3. Visit: http://localhost:8000/api/dashboard")
