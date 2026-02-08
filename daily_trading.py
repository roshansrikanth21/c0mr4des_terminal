
#!/usr/bin/env python3
"""
Daily Trading Assistant for Indian Options
"""

import sys
import os
from datetime import datetime
import pytz

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def daily_routine():
    from backend.advanced_analysis import AdvancedTradingSystem
    from backend.nifty_timing import IndianMarketTiming
    from paper_trading_log import PaperTradeLogger
    
    print("\n" + "="*70)
    print("🎯 INDIAN OPTIONS TRADING ASSISTANT")
    print(f"📅 {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M IST')}")
    print("="*70)
    
    # Initialize
    system = AdvancedTradingSystem(ticker="^NSEI")
    timing = IndianMarketTiming()
    logger = PaperTradeLogger()
    
    # 1. Market Status
    session = timing.get_current_session()
    print(f"\n📍 MARKET STATUS: {session}")
    
    # Check if market is open
    if session == "CLOSED" or session == "WEEKEND":
        print("   ⚠️  Market is closed. Exiting.")
        # Continue for testing purposes even if closed
        # return
    
    # 2. Get Analysis
    print("\n📊 ANALYZING MARKET...")
    # Use 1d if market closed to avoid errors, or catch error
    try:
        analysis = system.get_complete_analysis(interval="15m")
    except Exception as e:
        print(f"   Error fetching live data: {e}")
        return
    
    # 3. Display Entry Decision
    entry_decision = analysis['combined_entry_decision']
    print(f"\n🎯 ENTRY DECISION: {entry_decision['action']}")
    
    if entry_decision['action'] == 'ENTRY':
        print(f"   Confidence: {entry_decision['confidence']:.2f}")
        print(f"   Price: ₹{entry_decision['recommended_price']:.2f}")
        print(f"   Stop Loss: ₹{entry_decision['stop_loss']:.2f}")
        print(f"   Target: ₹{entry_decision['target']:.2f}")
        
        print("\n   📍 SIGNALS:")
        for signal in entry_decision['signals']:
            print(f"     • {signal[0]}: {signal[1]}")
        
        # Ask user if they want to paper trade
        response = input("\n   🤔 PAPER TRADE THIS? (y/n): ")
        if response.lower() == 'y':
            # Get option details
            option_type = input("     Option Type (CE/PE): ").upper()
            strike = float(input("     Strike Price: "))
            premium = float(input("     Premium: "))
            quantity = int(input("     Quantity (lots): "))
            
            # Log paper trade
            trade = logger.log_trade({
                "symbol": "NIFTY",
                "type": option_type,
                "strike": strike,
                "entry_price": premium,
                "stop_loss": entry_decision['stop_loss'],
                "take_profit": entry_decision['target'],
                "quantity": quantity * 50,  # Nifty lot size
                "reason": " | ".join([s[1] for s in entry_decision['signals']]),
                "signal_confidence": entry_decision['confidence'],
                "analysis_timestamp": analysis['timestamp']
            })
            
            print(f"\n   📝 Trade {trade['id']} logged for review.")
    
    else:
        print(f"   Reason: {entry_decision['reason']}")
    
    # 4. Timing Signals
    print("\n⏰ TIMING SIGNALS:")
    if 'timing_signals' in analysis:
        for signal in analysis['timing_signals'][:5]:
            urgency = "🔴" if signal['urgency'] == 'HIGH' else "🟡" if signal['urgency'] == 'MEDIUM' else "🟢"
            print(f"   {urgency} {signal['time']} - {signal['event']}: {signal['message']}")
    
    # 5. Risk Metrics
    if 'risk_analysis' in analysis and analysis['risk_analysis']:
        print(f"\n⚠️  RISK METRICS:")
        print(f"   95% VaR: {analysis['risk_analysis'].get('var_95', 'N/A')}%")
    
    # 6. Performance Summary
    perf = logger.get_performance()
    if perf['total_trades'] > 0:
        print(f"\n📈 PAPER TRADING PERFORMANCE:")
        print(f"   Trades: {perf['total_trades']} | Win Rate: {perf['win_rate']:.1f}%")
        print(f"   Total P&L: ₹{perf['total_pnl']:.2f}")
    
    print("\n" + "="*70)
    print("✅ Daily analysis complete. Trade safely! 🎯")
    print("="*70)

if __name__ == "__main__":
    try:
        daily_routine()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure all backend files are properly installed.")
