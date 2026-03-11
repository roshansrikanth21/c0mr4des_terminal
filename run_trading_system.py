#!/usr/bin/env python3
"""
Quick start script for the trading system
"""

import sys
import os
from backend.trading_decision_engine import IntegratedTradingDecisionEngine

def main():
    """Main execution"""
    
    print("\n" + "="*70)
    print("🚀 QUANTITATIVE TRADING SYSTEM - READY TO TRADE")
    print("="*70)
    
    # Get user input
    try:
        ticker = input("\n📈 Enter ticker symbol (default: ^NSEI): ").strip() or "^NSEI"
        capital_in = input("💰 Enter trading capital (default: 1000000): ").strip()
        capital = float(capital_in) if capital_in else 1000000
    except EOFError:
        ticker = "^NSEI"
        capital = 1000000
    except ValueError:
        print("❌ Invalid capital input. Using default ₹1,000,000.")
        capital = 1000000
    
    # Create engine
    print(f"\n⚙️  Initializing trading engine for {ticker}...")
    engine = IntegratedTradingDecisionEngine(ticker=ticker, capital=capital)
    
    # Run analysis
    print("\n🔍 Running comprehensive analysis...")
    results = engine.run_comprehensive_analysis()
    
    # Check for trade
    if results and 'decision' in results:
        decision = results['decision']
        
        if decision['action'] in ['BUY', 'SELL'] and decision['confidence'] > 0.6:
            print("\n" + "="*70)
            print("🎯 HIGH-CONFIDENCE TRADE SIGNAL GENERATED!")
            print("="*70)
            
            action = "BUY CALLS" if decision['action'] == 'BUY' else "BUY PUTS"
            print(f"\nAction: {action}")
            print(f"Confidence: {decision['confidence']:.1%}")
            
            # For non-interactive automation, we don't block here
            # But the user logic had a prompt, so we keep it for manual use
            # and provide a timeout or default if needed.
        else:
            print("\n⏸️  No high-confidence trade signal. Market conditions not favorable.")
    
    print("\n" + "="*70)
    print("✅ Analysis Complete")
    print("="*70)

if __name__ == "__main__":
    main()
