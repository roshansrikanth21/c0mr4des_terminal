"""
Non-interactive test for the Integrated Trading Decision Engine
"""
from backend.trading_decision_engine import IntegratedTradingDecisionEngine

def test_engine():
    print("[START] Starting Automated Engine Test...")
    engine = IntegratedTradingDecisionEngine(ticker="^NSEI", capital=1000000)
    results = engine.run_comprehensive_analysis()
    
    if "error" in results:
        print(f"[FAIL] Test Failed: {results['error']}")
        exit(1)
        
    print("\n[SUCCESS] Test Passed: Comprehensive analysis completed successfully.")
    print(f"Final Action: {results['decision']['action']}")
    print(f"Confidence: {results['decision']['confidence']:.1%}")

if __name__ == "__main__":
    test_engine()
