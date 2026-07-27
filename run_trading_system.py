#!/usr/bin/env python3
"""
Quick start script for the quantitative trading system
"""

import sys
import os

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.trading_decision_engine import IntegratedTradingDecisionEngine

def main():
    """Main execution"""
    
    print("\n" + "="*70)
    print("QUANTITATIVE TRADING SYSTEM - READY TO TRADE")
    print("="*70)
    
    ticker = "^NSEI"
    capital = 1000000.0
    
    if sys.stdin.isatty():
        try:
            ticker_input = input("\nEnter ticker symbol (default: ^NSEI): ").strip()
            if ticker_input:
                ticker = ticker_input
            cap_input = input("Enter trading capital (default: 1000000): ").strip()
            if cap_input:
                capital = float(cap_input)
        except (KeyboardInterrupt, EOFError):
            print("\nUsing default configuration (^NSEI, ₹1,000,000)")

    print(f"\nInitializing trading engine for {ticker} with ₹{capital:,.2f}...")
    engine = IntegratedTradingDecisionEngine(ticker=ticker, capital=capital)
    
    print("\nRunning comprehensive analysis...")
    results = engine.run_comprehensive_analysis()
    
    if results and 'decision' in results:
        decision = results['decision']
        
        if decision['action'] in ['BUY', 'SELL']:
            print("\n" + "="*70)
            print("TRADE SIGNAL GENERATED!")
            print("="*70)
            
            action = "BUY CALLS" if decision['action'] == 'BUY' else "BUY PUTS"
            print(f"\nAction: {action}")
            print(f"Confidence: {decision['confidence']:.1%}")
            
            if sys.stdin.isatty():
                try:
                    execute = input("\nExecute this trade? (y/n): ").strip().lower()
                    if execute == 'y':
                        print("\nTrade executed! Monitor positions in your broker account.")
                    else:
                        print("\nTrade not executed. Monitoring for better opportunities.")
                except (KeyboardInterrupt, EOFError):
                    pass
        else:
            print("\nNo trade signal. Market conditions not favorable.")
    
    print("\n" + "="*70)
    print("Trading system analysis complete")
    print("="*70)

if __name__ == "__main__":
    main()
