
import sys
import os
import time
import json
from datetime import datetime
import pandas as pd
from typing import Dict, Any

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from backend.advanced_analysis import AdvancedTradingSystem
from backend.bayesian_inference import BayesianTradingModel

class LiveTradingAssistant:
    def __init__(self):
        self.system = AdvancedTradingSystem()
        self.bayesian = self.system.bayesian_model
        self.active_trades = []
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.history_file = os.path.join(self.data_dir, 'live_trade_history.json')
        self.load_history()

    def load_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                history = json.load(f)
                # Re-hydrate Bayesian model
                for trade in history:
                    self.bayesian.update_with_trade(trade)
                print(f"Loaded {len(history)} historical trades. Current Win Rate: {self.bayesian.get_current_beliefs()['win_rate']['mean']:.1%}")

    def save_trade(self, trade_data: Dict[str, Any]):
        history = []
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                history = json.load(f)
        history.append(trade_data)
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=4)

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def display_dashboard(self, analysis: Dict[str, Any]):
        self.clear_screen()
        print("="*60)
        print(f" C0MR4DE TERMINAL AI ASSISTANT - {datetime.now().strftime('%H:%M:%S')}")
        print("="*60)
        
        # 1. Market Status
        print(f"\n[MARKET STATUS] {analysis.get('ticker', 'N/A')}")
        print(f"Price: {analysis.get('current_price', 0):.2f}")
        print(f"Session: {analysis.get('market_session', 'Unknown')}")

        # 1.5 Institutional Regime
        quant = analysis.get('quant_institutional', {})
        if quant:
            regime = quant.get('regime', {}).get('primary_regime', 'Unknown')
            risk = quant.get('risk_assessment', {}).get('composite_risk_score', 0)
            print(f"Regime: {regime} | Risk Score: {risk:.2f}")
        
        # 2. Timing
        timing = analysis.get('timing_signals', [])
        if timing:
            last_signal = timing[-1]
            if isinstance(last_signal, dict):
                print(f"\n[TIMING] {last_signal.get('event', 'Signal')}")
                print(f"Action: {last_signal.get('action', 'WAIT')}")
                print(f"Message: {last_signal.get('message', '')}")
        
        # 3. Risk (Placeholder)
        # risk = analysis.get('full_analysis', {}).get('risk_assessment', {})
        # print(f"\n[RISK ASSESSMENT]")
        
        # 4. Bayesian Beliefs
        beliefs = self.bayesian.get_current_beliefs()
        print(f"\n[STRATEGY INTELLIGENCE]")
        print(f"Win Rate: {beliefs['win_rate']['mean']:.1%}")
        print(f"Confidence: {beliefs['confidence']['score']:.0%}")
        
        # 5. Opportunity
        entry = analysis.get('combined_entry_decision', {})
        
        # Institutional Signals
        if quant and quant.get('integrated_signals', {}).get('high_confidence_signals'):
             print(f"\n[INSTITUTIONAL SIGNALS]")
             for sig in quant['integrated_signals']['high_confidence_signals']:
                  print(f"• {sig['type']} ({sig['source']}) - Conf: {sig['confidence']:.2f}")

        if entry.get('action') == 'ENTRY':
            print("\n" + "*"*60)
            print("!!! TRADE OPPORTUNITY DETECTED !!!")
            # entry['signals'] is a list of signals
            print(f"Confidence: {entry.get('confidence', 0):.2f}")
            print(f"Target: {entry.get('target', 0):.2f}")
            print(f"Stop Loss: {entry.get('stop_loss', 0):.2f}")
            print("*"*60)
            return True
        return False

    async def run(self):
        print("Starting C0MR4DE TERMINAL Assistant...")
        # ticker is initialized in self.system
        
        while True:
            try:
                # 1. Analyze
                print("Fetching live data...")
                analysis = await self.system.get_complete_analysis()
                
                if analysis and "error" in analysis:
                    print(f"Error: {analysis['error']}")
                    await asyncio.sleep(10)
                    continue

                # 2. Display
                has_signal = self.display_dashboard(analysis)
                
                # 3. Interact
                if has_signal:
                    user_input = input("\n>> Do you want to take this trade? (y/n): ").lower()
                    if user_input == 'y':
                        self.track_trade(analysis)
                
                # 4. Check Active Trades (Simplified for assistant)
                # In a real loop, we would track P&L here too.
                
                print("\nNext scan in 60 seconds... (Ctrl+C to stop)")
                await asyncio.sleep(60)
                
            except KeyboardInterrupt:
                print("\nAssistant stopped.")
                break
            except Exception as e:
                import traceback
                print(f"❌ [CRITICAL ERROR]: {e}")
                traceback.print_exc()
                print("\n⚠️ Entering 'Safe Mode' - Attempting recovery in 30 seconds...")
                await asyncio.sleep(30)

    def track_trade(self, analysis):
        print("\n--- Trade Tracking Started ---")
        entry_price = float(input("Enter Entry Price: "))
        trade_id = f"trade_{int(datetime.now().timestamp())}"
        
        trade = {
            "id": trade_id,
            "entry_time": datetime.now().isoformat(),
            "entry_price": entry_price,
            "analysis_snapshot": analysis
        }
        
        print(f"Trade {trade_id} tracked.")
        print("When you exit this trade, come back to record the result.")
        # For simplicity in this CLI version, we ask for result immediately or simulate a wait
        # In a real app, this would be async.
        # Here we will just log it and ask for the result now (manual mode)
        
        input("Press Enter when you have exited the trade...")
        exit_price = float(input("Enter Exit Price: "))
        pnl = exit_price - entry_price # Simplified for Directional
        
        result = {
            'pnl': pnl,
            'entry_time': datetime.fromisoformat(trade['entry_time']),
            'exit_time': datetime.now(),
            'reason': 'MANUAL_EXIT'
        }
        
        # Update Bayesian Model
        new_beliefs = self.bayesian.update_with_trade(result)
        self.save_trade({**trade, "exit": result})
        
        print(f"\nTrade Recorded. P&L: {pnl}")
        print(f"New Win Rate: {new_beliefs['win_rate']['mean']:.1%}")
        time.sleep(2)

if __name__ == "__main__":
    assistant = LiveTradingAssistant()
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        pass
