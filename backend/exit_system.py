"""
Multi-layer Exit System for Indian Options Trading
Combines technical, time-based, and volatility exits
"""

import numpy as np
from datetime import datetime, timedelta
import pytz

class DynamicExitSystem:
    def __init__(self, trade_params):
        """
        trade_params = {
            'entry_price': float,
            'entry_time': datetime,
            'option_type': 'CE' or 'PE',
            'strike': float,
            'lot_size': int,
            'spot_price': float,
            'iv_at_entry': float
        }
        """
        self.params = trade_params
        self.stop_loss = None
        self.take_profit = None
        self.trailing_stop = None
        self.highest_price = trade_params['entry_price']
        self.lowest_price = trade_params['entry_price']
        self.partial_exits = []
        
    def evaluate_exit(self, market_data):
        """
        market_data = {
            'current_price': float,
            'current_time': datetime,
            'spot_price': float,
            'atr': float,
            'iv_current': float,
            'volume': float,
            'time_to_expiry_hours': float
        }
        """
        exit_signals = []
        
        # Layer 1: Technical Exits
        tech_exits = self._technical_exits(market_data)
        exit_signals.extend(tech_exits)
        
        # Layer 2: Time-based Exits
        time_exits = self._time_based_exits(market_data)
        exit_signals.extend(time_exits)
        
        # Layer 3: Volatility Exits
        vol_exits = self._volatility_exits(market_data)
        exit_signals.extend(vol_exits)
        
        # Layer 4: Profit Protection Exits
        profit_exits = self._profit_protection_exits(market_data)
        exit_signals.extend(profit_exits)
        
        # Combine and prioritize
        final_decision = self._prioritize_exits(exit_signals, market_data)
        
        return {
            "decision": final_decision,
            "all_signals": exit_signals,
            "current_stop": self.trailing_stop,
            "current_target": self.take_profit,
            "partial_exit_recommended": self._check_partial_exit(market_data)
        }
    
    def _technical_exits(self, market_data):
        """ATR-based exits with trailing stops"""
        signals = []
        
        # Initialize stops if not set
        if self.stop_loss is None:
            self.stop_loss = self._calculate_initial_stop(market_data)
            self.take_profit = self._calculate_initial_target(market_data)
            self.trailing_stop = self.stop_loss
        
        current_price = market_data['current_price']
        
        # Update highest price for trailing stop
        if self.params['option_type'] == 'CE':
            self.highest_price = max(self.highest_price, current_price)
        else:  # PE
            self.lowest_price = min(self.lowest_price, current_price)
        
        # Update trailing stop (only moves in favorable direction)
        new_trailing_stop = self._update_trailing_stop(market_data)
        if ((self.params['option_type'] == 'CE' and new_trailing_stop > self.trailing_stop) or
            (self.params['option_type'] == 'PE' and new_trailing_stop < self.trailing_stop)):
            self.trailing_stop = new_trailing_stop
        
        # Check exit conditions
        if self.params['option_type'] == 'CE':
            if current_price <= self.trailing_stop:
                signals.append(("EXIT", "TRAILING_STOP", f"Price {current_price:.2f} <= Trailing Stop {self.trailing_stop:.2f}"))
            elif current_price >= self.take_profit:
                signals.append(("EXIT", "TAKE_PROFIT", f"Price {current_price:.2f} >= Target {self.take_profit:.2f}"))
        else:  # PE
            if current_price >= self.trailing_stop:
                signals.append(("EXIT", "TRAILING_STOP", f"Price {current_price:.2f} >= Trailing Stop {self.trailing_stop:.2f}"))
            elif current_price <= self.take_profit:
                signals.append(("EXIT", "TAKE_PROFIT", f"Price {current_price:.2f} <= Target {self.take_profit:.2f}"))
        
        return signals
    
    def _calculate_initial_stop(self, market_data):
        """Initial stop loss based on ATR"""
        atr = market_data.get('atr', market_data['current_price'] * 0.01)
        
        if self.params['option_type'] == 'CE':
            return self.params['entry_price'] - (atr * 1.8)  # Tighter stop for options
        else:  # PE
            return self.params['entry_price'] + (atr * 1.8)
    
    def _calculate_initial_target(self, market_data):
        """Initial target based on risk:reward"""
        stop = self._calculate_initial_stop(market_data)
        risk = abs(self.params['entry_price'] - stop)
        
        if self.params['option_type'] == 'CE':
            return self.params['entry_price'] + (risk * 2.2)  # 2.2:1 RR
        else:  # PE
            return self.params['entry_price'] - (risk * 2.2)
    
    def _update_trailing_stop(self, market_data):
        """Dynamic trailing stop that tightens as profit increases"""
        atr = market_data.get('atr', market_data['current_price'] * 0.01)
        current_price = market_data['current_price']
        
        if self.params['option_type'] == 'CE':
            # Move to breakeven + 0.5 ATR once in profit
            if current_price > self.params['entry_price']:
                return max(self.params['entry_price'] + (atr * 0.5), 
                          current_price - (atr * 1.5))
            else:
                return current_price - (atr * 1.8)
        else:  # PE
            if current_price < self.params['entry_price']:
                return min(self.params['entry_price'] - (atr * 0.5),
                          current_price + (atr * 1.5))
            else:
                return current_price + (atr * 1.8)
    
    def _time_based_exits(self, market_data):
        """Exit based on time decay and market hours"""
        signals = []
        current_time = market_data['current_time']
        entry_time = self.params['entry_time']
        
        # Calculate time elapsed
        time_elapsed = (current_time - entry_time).total_seconds() / 3600  # hours
        
        # Theta decay becomes significant after 2 hours
        if time_elapsed > 2 and market_data['time_to_expiry_hours'] < 4:
            signals.append(("CONSIDER_EXIT", "THETA_DECAY", 
                          f"High time decay - {time_elapsed:.1f}h elapsed, {market_data['time_to_expiry_hours']:.1f}h to expiry"))
        
        # Don't hold overnight (for intraday)
        ist = pytz.timezone('Asia/Kolkata')
        current_ist = current_time.astimezone(ist)
        
        if current_ist.hour >= 15 and current_ist.minute >= 10:  # After 3:10 PM
            signals.append(("EXIT", "MARKET_CLOSE", 
                          "Exit before market close - Indian markets"))
        
        # Expiry day special rule (Thursday for weekly options)
        if current_ist.weekday() == 3:  # Thursday
            if current_ist.hour >= 14:  # After 2 PM on expiry day
                signals.append(("EXIT", "EXPIRY_DAY", 
                              "Expiry day - exit early to avoid settlement risk"))
        
        return signals
    
    def _volatility_exits(self, market_data):
        """Exit based on volatility changes"""
        signals = []
        
        iv_change = market_data['iv_current'] - self.params['iv_at_entry']
        
        # IV Crush (bad for long options)
        if iv_change < -0.05:  # 5% IV drop
            signals.append(("EXIT", "IV_CRUSH", 
                          f"IV dropped by {abs(iv_change):.2%} - option premium decaying"))
        
        # IV Spike without price movement (bad)
        price_change = abs(market_data['current_price'] - self.params['entry_price']) / self.params['entry_price']
        if iv_change > 0.10 and price_change < 0.02:  # 10% IV rise, <2% price move
            signals.append(("CONSIDER_EXIT", "IV_PUMP_NO_MOVE",
                          "IV rising without price movement - poor risk/reward"))
        
        return signals
    
    def _profit_protection_exits(self, market_data):
        """Protect profits at different levels"""
        signals = []
        current_price = market_data['current_price']
        
        profit_pct = (current_price - self.params['entry_price']) / self.params['entry_price']
        if self.params['option_type'] == 'PE':
            profit_pct = -profit_pct  # For puts, price down = profit
        
        # Book partial profits at different levels
        if profit_pct >= 0.15 and not any(e[0] == 'PARTIAL' for e in self.partial_exits):
            signals.append(("PARTIAL_EXIT", "PROFIT_15%", 
                          f"Book 30% at {profit_pct:.1%} profit"))
            self.partial_exits.append(("PARTIAL", "15%", current_price))
        
        if profit_pct >= 0.25 and not any(e[0] == 'PARTIAL' and e[1] == '25%' for e in self.partial_exits):
            signals.append(("PARTIAL_EXIT", "PROFIT_25%",
                          f"Book another 30% at {profit_pct:.1%} profit"))
            self.partial_exits.append(("PARTIAL", "25%", current_price))
        
        # Protect profits if they start to fade
        if profit_pct > 0.10:
            # Check if profit is eroding
            if self.params['option_type'] == 'CE':
                if current_price < self.highest_price * 0.97:  # 3% retracement from high
                    signals.append(("CONSIDER_EXIT", "PROFIT_ERODING",
                                  f"Profit eroding from high of {self.highest_price:.2f}"))
            else:  # PE
                if current_price > self.lowest_price * 1.03:  # 3% retracement from low
                    signals.append(("CONSIDER_EXIT", "PROFIT_ERODING",
                                  f"Profit eroding from low of {self.lowest_price:.2f}"))
        
        return signals
    
    def _check_partial_exit(self, market_data):
        """Recommend partial exit if conditions met"""
        current_price = market_data['current_price']
        profit_pct = abs(current_price - self.params['entry_price']) / self.params['entry_price']
        
        if profit_pct > 0.15 and len(self.partial_exits) == 0:
            return {
                "action": "PARTIAL_EXIT_30%",
                "reason": f"First profit target hit: {profit_pct:.1%}",
                "price": current_price
            }
        
        return None
    
    def _prioritize_exits(self, signals, market_data):
        """Prioritize exit signals"""
        # Priority order
        priority_map = {
            "EXIT": 1,
            "PARTIAL_EXIT": 2,
            "CONSIDER_EXIT": 3
        }
        
        exit_signals = [s for s in signals if s[0] == "EXIT"]
        partial_signals = [s for s in signals if s[0] == "PARTIAL_EXIT"]
        consider_signals = [s for s in signals if s[0] == "CONSIDER_EXIT"]
        
        if exit_signals:
            # Take the highest priority exit signal
            return {
                "action": "EXIT",
                "reason": exit_signals[0][2],
                "urgency": "IMMEDIATE"
            }
        elif partial_signals:
            return {
                "action": "PARTIAL_EXIT",
                "reason": partial_signals[0][2],
                "urgency": "SOON"
            }
        elif consider_signals:
            # Check if we have multiple "consider" signals
            if len(consider_signals) >= 2:
                return {
                    "action": "EXIT",
                    "reason": f"Multiple warnings: {consider_signals[0][1]}, {consider_signals[1][1]}",
                    "urgency": "SOON"
                }
            else:
                return {
                    "action": "HOLD",
                    "reason": consider_signals[0][2] if consider_signals else "No exit signals",
                    "urgency": "MONITOR"
                }
        
        return {
            "action": "HOLD",
            "reason": "No exit signals triggered",
            "urgency": "CONTINUE"
        }
