import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

sys.path.append(os.getcwd())

def test_timing_systems():
    print("\n=== TESTING PHASE 11: SPECIFIC TIMING & EXIT SYSTEMS ===")
    
    # Mock Data Creation
    print("\n[Mock Data] Creating Intraday Data...")
    dates = pd.date_range(start="2025-02-07 09:15", periods=75, freq="5min", tz="Asia/Kolkata")
    # Sine wave price to simulate swings
    prices = 25000 + 100 * np.sin(np.linspace(0, 10, 75))
    df = pd.DataFrame({
        "Open": prices - 5,
        "High": prices + 10,
        "Low": prices - 10,
        "Close": prices,
        "Volume": np.random.randint(1000, 5000, 75)
    }, index=dates)
    
    # 1. Order Flow (Volume Profile)
    print("\n[1] Order Flow (Volume Profile)...")
    try:
        from backend.order_flow import OrderFlowAnalyzer
        ofa = OrderFlowAnalyzer()
        vpoc = ofa.calculate_vpoc(df)
        print(f"SUCCESS: VPOC: {vpoc.get('vpoc')}")
        print(f"SUCCESS: Value Area: {vpoc.get('value_area')}")
        liq = ofa.detect_liquidity_zones(df)
        print(f"SUCCESS: Support Levels: {len(liq.get('support', []))}")
    except Exception as e:
        print(f"FAILED: Order Flow - {e}")

    # 2. Nifty Timing
    print("\n[2] Nifty Timing (ORB & Schedule)...")
    try:
        from backend.nifty_timing import NiftyTimingSystem
        nts = NiftyTimingSystem()
        signals = nts.get_intraday_schedule_signals()
        print(f"SUCCESS: Schedule Signals: {len(signals)}")
        orb = nts.calculate_opening_range_breakout(df)
        print(f"SUCCESS: ORB Status: {orb.get('status')}")
    except Exception as e:
        print(f"FAILED: Nifty Timing - {e}")

    # 3. Market Profile
    print("\n[3] Market Profile (Intraday Utils)...")
    try:
        from backend.intraday_utils import get_market_profile_signals
        mp = get_market_profile_signals(df)
        print(f"SUCCESS: Current Session: {mp.get('current_session')}")
    except Exception as e:
        print(f"FAILED: Market Profile - {e}")

    # 4. Options Greeks
    print("\n[4] Options Greeks (Black-Scholes)...")
    try:
        from backend.options_indicators import OptionsExitIndicators
        oei = OptionsExitIndicators()
        greeks = oei.calculate_greeks(spot_price=25000, strike=25000, days_to_expiry=3/365, iv=0.20)
        print(f"SUCCESS: Delta: {greeks.get('delta')}")
        print(f"SUCCESS: Gamma: {greeks.get('gamma')}")
    except Exception as e:
        print(f"FAILED: Greeks - {e}")

    # 5. Dynamic Exit System
    print("\n[5] Dynamic Exit Logic...")
    try:
        from backend.exit_system import DynamicExitSystem
        des = DynamicExitSystem(entry_price=100, entry_time=datetime.now(), option_type="CE")
        
        # Simulate price drop
        decision = des.calculate_exits(
            current_price=95, current_time=datetime.now(), 
            atr=5, iv=0.20, time_to_expiry_hours=0.5
        )
        print(f"SUCCESS: Exit Action (Low/Theta): {decision.get('action')}")
        print(f"SUCCESS: Reason: {decision.get('reason')}")
        
    except Exception as e:
        print(f"FAILED: Exit System - {e}")

if __name__ == "__main__":
    test_timing_systems()
