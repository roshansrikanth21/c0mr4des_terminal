"""
Enhanced Order Flow Analysis using Broker-Level Data
Implements concepts from Varsity, Order Flow Trading books, and institutional flow detection
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


class InstitutionalOrderFlowAnalyzer:
    """
    Advanced order flow analysis using Level 2 market data
    Implements concepts from:
    - Zerodha Varsity (Market Profile, Volume Analysis)
    - Order Flow Trading books (Bid/Ask Imbalance, Absorption)
    - Institutional footprint detection
    """
    
    def __init__(self, ticker: str = "^NSEI"):
        self.ticker = ticker
        self.order_book_history = deque(maxlen=100)  # Store last 100 order book snapshots
        self.large_order_threshold = 1000000  # ₹10L+ considered large order
        self.absorption_threshold = 0.7  # 70% of ask/bid absorbed = absorption
        
    def analyze_order_book_imbalance(self, order_book: Dict) -> Dict:
        """
        Analyze bid/ask imbalance from Level 2 order book
        Key concept: When bid volume >> ask volume, buyers are aggressive (bullish)
        """
        if not order_book.get('bid') or not order_book.get('ask'):
            return {'imbalance': 0, 'signal': 'NEUTRAL', 'strength': 0}
        
        bid_volume = sum([level.get('quantity', 0) * level.get('price', 0) 
                         for level in order_book['bid'][:5]])  # Top 5 bid levels
        ask_volume = sum([level.get('quantity', 0) * level.get('price', 0) 
                         for level in order_book['ask'][:5]])  # Top 5 ask levels
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return {'imbalance': 0, 'signal': 'NEUTRAL', 'strength': 0}
        
        # Imbalance ratio: positive = more buying pressure, negative = more selling
        imbalance_ratio = (bid_volume - ask_volume) / total_volume
        
        # Determine signal strength
        if imbalance_ratio > 0.3:
            signal = 'STRONG_BUY'
            strength = min(abs(imbalance_ratio) * 2, 1.0)
        elif imbalance_ratio > 0.1:
            signal = 'BUY'
            strength = abs(imbalance_ratio) * 1.5
        elif imbalance_ratio < -0.3:
            signal = 'STRONG_SELL'
            strength = min(abs(imbalance_ratio) * 2, 1.0)
        elif imbalance_ratio < -0.1:
            signal = 'SELL'
            strength = abs(imbalance_ratio) * 1.5
        else:
            signal = 'NEUTRAL'
            strength = 0
        
        return {
            'imbalance': float(imbalance_ratio),
            'signal': signal,
            'strength': float(strength),
            'bid_volume': float(bid_volume),
            'ask_volume': float(ask_volume),
            'total_volume': float(total_volume)
        }
    
    def detect_absorption(self, order_book: Dict, price_level: float, side: str = 'ask') -> Dict:
        """
        Detect absorption at price levels
        Absorption = Large orders sitting at a level that get filled but price doesn't move
        This indicates institutional support/resistance
        
        Concept from Order Flow Trading: When large orders are absorbed without price movement,
        it shows where smart money is positioned
        """
        if side == 'ask':
            levels = order_book.get('ask', [])
            ltp = order_book.get('ltp', 0)
            # Check if price is near ask levels
            relevant_levels = [l for l in levels if abs(l.get('price', 0) - price_level) < price_level * 0.001]
        else:
            levels = order_book.get('bid', [])
            ltp = order_book.get('ltp', 0)
            relevant_levels = [l for l in levels if abs(l.get('price', 0) - price_level) < price_level * 0.001]
        
        if not relevant_levels:
            return {'absorbed': False, 'volume_absorbed': 0, 'strength': 0}
        
        # Calculate total volume at this level
        total_volume = sum([l.get('quantity', 0) * l.get('price', 0) for l in relevant_levels])
        
        # If volume is large and price hasn't moved much, it's absorption
        if total_volume > self.large_order_threshold:
            # Check price movement (compare with previous order book snapshots)
            if len(self.order_book_history) > 0:
                prev_ob = self.order_book_history[-1]
                price_change = abs(order_book.get('ltp', 0) - prev_ob.get('ltp', 0)) / prev_ob.get('ltp', 1)
                
                # If large volume but small price change = absorption
                if price_change < 0.001:  # Less than 0.1% price change
                    return {
                        'absorbed': True,
                        'volume_absorbed': float(total_volume),
                        'strength': min(total_volume / self.large_order_threshold, 2.0),
                        'level': price_level,
                        'side': side
                    }
        
        return {'absorbed': False, 'volume_absorbed': 0, 'strength': 0}
    
    def detect_large_orders(self, order_book: Dict) -> List[Dict]:
        """
        Detect large orders (institutional footprint)
        Large orders often indicate where institutions are positioned
        """
        large_orders = []
        
        # Check bid side
        for level in order_book.get('bid', []):
            volume_value = level.get('quantity', 0) * level.get('price', 0)
            if volume_value >= self.large_order_threshold:
                large_orders.append({
                    'side': 'BID',
                    'price': level.get('price', 0),
                    'quantity': level.get('quantity', 0),
                    'value': float(volume_value),
                    'type': 'INSTITUTIONAL_BUY' if volume_value > self.large_order_threshold * 2 else 'LARGE_BUY'
                })
        
        # Check ask side
        for level in order_book.get('ask', []):
            volume_value = level.get('quantity', 0) * level.get('price', 0)
            if volume_value >= self.large_order_threshold:
                large_orders.append({
                    'side': 'ASK',
                    'price': level.get('price', 0),
                    'quantity': level.get('quantity', 0),
                    'value': float(volume_value),
                    'type': 'INSTITUTIONAL_SELL' if volume_value > self.large_order_threshold * 2 else 'LARGE_SELL'
                })
        
        return large_orders
    
    def calculate_delta(self, order_book: Dict, prev_order_book: Optional[Dict] = None) -> Dict:
        """
        Calculate Order Flow Delta
        Delta = Volume at bid - Volume at ask
        Positive delta = more buying pressure
        Negative delta = more selling pressure
        
        This is a key concept from Order Flow Trading books
        """
        if not prev_order_book:
            return {'delta': 0, 'delta_percent': 0, 'trend': 'NEUTRAL'}
        
        # Current bid/ask volumes
        current_bid_vol = sum([l.get('quantity', 0) for l in order_book.get('bid', [])])
        current_ask_vol = sum([l.get('quantity', 0) for l in order_book.get('ask', [])])
        
        # Previous bid/ask volumes
        prev_bid_vol = sum([l.get('quantity', 0) for l in prev_order_book.get('bid', [])])
        prev_ask_vol = sum([l.get('quantity', 0) for l in prev_order_book.get('ask', [])])
        
        # Calculate delta change
        bid_delta = current_bid_vol - prev_bid_vol
        ask_delta = current_ask_vol - prev_ask_vol
        net_delta = bid_delta - ask_delta
        
        total_volume = current_bid_vol + current_ask_vol
        delta_percent = (net_delta / total_volume * 100) if total_volume > 0 else 0
        
        # Determine trend
        if delta_percent > 5:
            trend = 'STRONG_BUYING'
        elif delta_percent > 2:
            trend = 'BUYING'
        elif delta_percent < -5:
            trend = 'STRONG_SELLING'
        elif delta_percent < -2:
            trend = 'SELLING'
        else:
            trend = 'NEUTRAL'
        
        return {
            'delta': float(net_delta),
            'delta_percent': float(delta_percent),
            'trend': trend,
            'bid_volume': float(current_bid_vol),
            'ask_volume': float(current_ask_vol)
        }

    def update_cvd(self, order_book: Dict) -> float:
        """
        Calculates Cumulative Volume Delta (CVD) for the session.
        CVD is a running total of the delta between buying and selling pressure.
        """
        prev_ob = self.order_book_history[-2] if len(self.order_book_history) > 1 else None
        delta_info = self.calculate_delta(order_book, prev_ob)
        
        # We track session_cvd in an instance variable if possible, 
        # but for this stateless analysis, we'll calculate from history
        cvd = 0.0
        if len(self.order_book_history) > 1:
            for i in range(1, len(self.order_book_history)):
                d = self.calculate_delta(self.order_book_history[i], self.order_book_history[i-1])
                cvd += d['delta']
        
        return float(cvd)

    def detect_order_book_sweeps(self, order_book: Dict) -> List[Dict]:
        """
        Detect aggressive "Sweeps" where multiple levels are cleared.
        Indicates extreme institutional urgency.
        """
        sweeps = []
        prev_ob = self.order_book_history[-2] if len(self.order_book_history) > 1 else None
        if not prev_ob: return sweeps

        # Bullish Sweep: Price jumped across multiple Ask levels
        curr_ltp = order_book.get('ltp', 0)
        prev_ltp = prev_ob.get('ltp', 0)
        
        if curr_ltp > prev_ltp:
            cleared_levels = [l for l in prev_ob.get('ask', []) if l['price'] < curr_ltp]
            if len(cleared_levels) >= 3: # Cleared 3+ levels
                sweeps.append({
                    "type": "bullish_sweep",
                    "levels_cleared": len(cleared_levels),
                    "impact": float(curr_ltp - prev_ltp),
                    "description": f"Aggressive Buyer Sweep ({len(cleared_levels)} levels)"
                })

        # Bearish Sweep: Price dropped across multiple Bid levels
        if curr_ltp < prev_ltp:
            cleared_levels = [l for l in prev_ob.get('bid', []) if l['price'] > curr_ltp]
            if len(cleared_levels) >= 3:
                sweeps.append({
                    "type": "bearish_sweep",
                    "levels_cleared": len(cleared_levels),
                    "impact": float(prev_ltp - curr_ltp),
                    "description": f"Aggressive Seller Sweep ({len(cleared_levels)} levels)"
                })

        return sweeps
    
    def detect_momentum_shift(self, order_book_history: List[Dict]) -> Dict:
        """
        Detect momentum shifts using order book history
        When order flow delta changes direction, it often signals a momentum shift
        """
        if len(order_book_history) < 5:
            return {'shift_detected': False, 'direction': None}
        
        # Calculate deltas for recent snapshots
        deltas = []
        for i in range(1, len(order_book_history)):
            delta_info = self.calculate_delta(order_book_history[i], order_book_history[i-1])
            deltas.append(delta_info.get('delta_percent', 0))
        
        # Check for reversal pattern
        if len(deltas) >= 3:
            recent = deltas[-3:]
            # If going from negative to positive = bullish shift
            if recent[0] < -2 and recent[-1] > 2:
                return {
                    'shift_detected': True,
                    'direction': 'BULLISH',
                    'strength': min(abs(recent[-1]), 1.0),
                    'signal': 'BUY'
                }
            # If going from positive to negative = bearish shift
            elif recent[0] > 2 and recent[-1] < -2:
                return {
                    'shift_detected': True,
                    'direction': 'BEARISH',
                    'strength': min(abs(recent[-1]), 1.0),
                    'signal': 'SELL'
                }
        
        return {'shift_detected': False, 'direction': None}
    
    def analyze_comprehensive_flow(self, order_book: Dict, price_data: pd.DataFrame) -> Dict:
        """
        Comprehensive order flow analysis combining all techniques
        """
        # Store current order book
        self.order_book_history.append(order_book.copy())
        
        # 1. Order book imbalance
        imbalance = self.analyze_order_book_imbalance(order_book)
        
        # 2. Large orders detection
        large_orders = self.detect_large_orders(order_book)
        
        # 3. Absorption detection at current price
        ltp = order_book.get('ltp', 0)
        ask_absorption = self.detect_absorption(order_book, ltp, 'ask')
        bid_absorption = self.detect_absorption(order_book, ltp, 'bid')
        
        # 4. Delta calculation
        prev_ob = self.order_book_history[-2] if len(self.order_book_history) > 1 else None
        delta_info = self.calculate_delta(order_book, prev_ob)
        
        # 5. Momentum shift detection
        momentum_shift = self.detect_momentum_shift(list(self.order_book_history))
        
        # 6. Combine with price action
        price_signals = self._analyze_price_with_flow(price_data, imbalance, delta_info)
        
        # Generate final signal
        signal_strength = self._calculate_signal_strength(
            imbalance, delta_info, large_orders, ask_absorption, bid_absorption, momentum_shift
        )
        
        return {
            'timestamp': datetime.now().isoformat(),
            'order_book_imbalance': imbalance,
            'delta': delta_info,
            'large_orders': large_orders,
            'absorption': {
                'ask': ask_absorption,
                'bid': bid_absorption
            },
            'momentum_shift': momentum_shift,
            'price_signals': price_signals,
            'final_signal': {
                'action': self._determine_action(signal_strength),
                'confidence': signal_strength,
                'reason': self._generate_reason(imbalance, delta_info, large_orders, momentum_shift)
            }
        }
    
    def _analyze_price_with_flow(self, price_data: pd.DataFrame, imbalance: Dict, delta: Dict) -> Dict:
        """Combine price action with order flow"""
        if price_data.empty or len(price_data) < 2:
            return {'signal': 'NEUTRAL', 'strength': 0}
        
        current_price = float(price_data['Close'].iloc[-1])
        prev_price = float(price_data['Close'].iloc[-2])
        price_change = (current_price - prev_price) / prev_price
        
        # If price is rising AND order flow is bullish = strong signal
        if price_change > 0 and imbalance['signal'] in ['BUY', 'STRONG_BUY']:
            return {'signal': 'BULLISH_CONFIRMED', 'strength': 0.8}
        # If price is falling AND order flow is bearish = strong signal
        elif price_change < 0 and imbalance['signal'] in ['SELL', 'STRONG_SELL']:
            return {'signal': 'BEARISH_CONFIRMED', 'strength': 0.8}
        # Divergence = potential reversal
        elif price_change > 0 and imbalance['signal'] in ['SELL', 'STRONG_SELL']:
            return {'signal': 'BULLISH_DIVERGENCE', 'strength': 0.4}
        elif price_change < 0 and imbalance['signal'] in ['BUY', 'STRONG_BUY']:
            return {'signal': 'BEARISH_DIVERGENCE', 'strength': 0.4}
        
        return {'signal': 'NEUTRAL', 'strength': 0}
    
    def _calculate_signal_strength(self, imbalance: Dict, delta: Dict, large_orders: List,
                                   ask_abs: Dict, bid_abs: Dict, momentum: Dict) -> float:
        """Calculate overall signal strength from all factors"""
        strength = 0.0
        
        # Imbalance contributes 30%
        strength += imbalance.get('strength', 0) * 0.3
        
        # Delta contributes 25%
        delta_strength = abs(delta.get('delta_percent', 0)) / 10  # Normalize to 0-1
        if delta.get('trend') in ['STRONG_BUYING', 'BUYING']:
            strength += delta_strength * 0.25
        elif delta.get('trend') in ['STRONG_SELLING', 'SELLING']:
            strength -= delta_strength * 0.25
        
        # Large orders contribute 20%
        buy_orders = [o for o in large_orders if 'BUY' in o.get('type', '')]
        sell_orders = [o for o in large_orders if 'SELL' in o.get('type', '')]
        if len(buy_orders) > len(sell_orders):
            strength += min(len(buy_orders) / 5, 1.0) * 0.2
        elif len(sell_orders) > len(buy_orders):
            strength -= min(len(sell_orders) / 5, 1.0) * 0.2
        
        # Absorption contributes 15%
        if ask_abs.get('absorbed'):
            strength += ask_abs.get('strength', 0) * 0.15  # Ask absorption = bullish
        if bid_abs.get('absorbed'):
            strength -= bid_abs.get('strength', 0) * 0.15  # Bid absorption = bearish
        
        # Momentum shift contributes 10%
        if momentum.get('shift_detected'):
            if momentum.get('direction') == 'BULLISH':
                strength += momentum.get('strength', 0) * 0.1
            else:
                strength -= momentum.get('strength', 0) * 0.1
        
        return max(-1.0, min(1.0, strength))  # Clamp to [-1, 1]
    
    def _determine_action(self, signal_strength: float) -> str:
        """Determine trading action from signal strength"""
        if signal_strength > 0.6:
            return 'STRONG_BUY'
        elif signal_strength > 0.3:
            return 'BUY'
        elif signal_strength < -0.6:
            return 'STRONG_SELL'
        elif signal_strength < -0.3:
            return 'SELL'
        else:
            return 'HOLD'
    
    def _generate_reason(self, imbalance: Dict, delta: Dict, large_orders: List, momentum: Dict) -> str:
        """Generate human-readable reason for signal"""
        reasons = []
        
        if imbalance.get('strength', 0) > 0.5:
            reasons.append(f"Strong {imbalance.get('signal', '')} imbalance")
        
        if abs(delta.get('delta_percent', 0)) > 5:
            reasons.append(f"{delta.get('trend', '')} pressure")
        
        if len(large_orders) > 0:
            buy_count = len([o for o in large_orders if 'BUY' in o.get('type', '')])
            sell_count = len([o for o in large_orders if 'SELL' in o.get('type', '')])
            if buy_count > sell_count:
                reasons.append(f"{buy_count} large buy orders detected")
            elif sell_count > buy_count:
                reasons.append(f"{sell_count} large sell orders detected")
        
        if momentum.get('shift_detected'):
            reasons.append(f"Momentum shift: {momentum.get('direction', '')}")
        
        return " | ".join(reasons) if reasons else "Neutral order flow"
