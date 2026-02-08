
from backend.advanced_analysis import AdvancedTradingSystem
from datetime import datetime

print(f"📈 MORNING MARKET CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

system = AdvancedTradingSystem(ticker="^NSEI")
try:
    analysis = system.get_complete_analysis(interval="15m")

    print(f"Market Session: {analysis['market_session']}")
    print(f"Entry Allowed: {analysis['entry_allowed']}")
    print(f"Primary Signal: {analysis['combined_entry_decision']['action']}")

    if analysis['combined_entry_decision']['action'] == 'ENTRY':
        print("\n🎯 ENTRY SIGNALS DETECTED:")
        for signal in analysis['combined_entry_decision']['signals']:
            print(f"  • {signal[0]}: {signal[1]}")
        
        print(f"\n💰 RECOMMENDATION:")
        print(f"  Price: {analysis['combined_entry_decision']['recommended_price']:.2f}")
        print(f"  Stop Loss: {analysis['combined_entry_decision']['stop_loss']:.2f}")
        print(f"  Target: {analysis['combined_entry_decision']['target']:.2f}")
    else:
        print(f"\n⏳ WAIT SIGNAL: {analysis['combined_entry_decision']['reason']}")

    print("\n⏰ TIMING SIGNALS:")
    for signal in analysis['timing_signals'][:3]:
        print(f"  {signal['time']} - {signal['event']}")

except Exception as e:
    print(f"Error fetching data: {e}")

print("=" * 60)
