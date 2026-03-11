"""
Momentum-based trading system for Indian markets
Implements 50/200-day moving average strategies with volatility scaling
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

class MomentumTradingSystem:
    """
    Professional momentum trading with volatility scaling
    Combines trend following with risk management
    """
    
    def __init__(self, ticker="^NSEI"):
        self.ticker = ticker
        self.fast_ma = 50
        self.slow_ma = 200
        self.vol_lookback = 20
        self.current_signal = None
        
    def calculate_momentum_signals(self, df, use_vol_scaling=True):
        """
        Calculate momentum signals with MA crossovers
        """
        # Calculate moving averages
        df['MA_fast'] = df['Close'].rolling(window=self.fast_ma).mean()
        df['MA_slow'] = df['Close'].rolling(window=self.slow_ma).mean()
        
        # Calculate volatility
        df['Returns'] = df['Close'].pct_change()
        df['Volatility'] = df['Returns'].rolling(window=self.vol_lookback).std() * np.sqrt(252)
        
        # Generate signals
        signals = []
        
        # MA Crossover signal
        if len(df) > 2:
            if df['MA_fast'].iloc[-1] > df['MA_slow'].iloc[-1] and df['MA_fast'].iloc[-2] <= df['MA_slow'].iloc[-2]:
                signals.append({
                    'type': 'MA_CROSSOVER_BULLISH',
                    'strength': 'STRONG',
                    'reason': f'Fast MA ({self.fast_ma}d) crossed above Slow MA ({self.slow_ma}d)',
                    'entry_price': float(df['Close'].iloc[-1]),
                    'fast_ma': float(df['MA_fast'].iloc[-1]),
                    'slow_ma': float(df['MA_slow'].iloc[-1])
                })
            elif df['MA_fast'].iloc[-1] < df['MA_slow'].iloc[-1] and df['MA_fast'].iloc[-2] >= df['MA_slow'].iloc[-2]:
                signals.append({
                    'type': 'MA_CROSSOVER_BEARISH',
                    'strength': 'STRONG',
                    'reason': f'Fast MA ({self.fast_ma}d) crossed below Slow MA ({self.slow_ma}d)',
                    'entry_price': float(df['Close'].iloc[-1]),
                    'fast_ma': float(df['MA_fast'].iloc[-1]),
                    'slow_ma': float(df['MA_slow'].iloc[-1])
                })
        
        # Trend confirmation
        price_above_fast = df['Close'].iloc[-1] > df['MA_fast'].iloc[-1]
        fast_above_slow = df['MA_fast'].iloc[-1] > df['MA_slow'].iloc[-1]
        
        if price_above_fast and fast_above_slow:
            signals.append({
                'type': 'TREND_BULLISH_CONFIRMED',
                'strength': 'MODERATE',
                'reason': 'Price > Fast MA > Slow MA',
                'distance_fast': float((df['Close'].iloc[-1] - df['MA_fast'].iloc[-1]) / df['MA_fast'].iloc[-1] * 100),
                'distance_slow': float((df['Close'].iloc[-1] - df['MA_slow'].iloc[-1]) / df['MA_slow'].iloc[-1] * 100)
            })
        elif not price_above_fast and not fast_above_slow:
            signals.append({
                'type': 'TREND_BEARISH_CONFIRMED',
                'strength': 'MODERATE',
                'reason': 'Price < Fast MA < Slow MA',
                'distance_fast': float((df['Close'].iloc[-1] - df['MA_fast'].iloc[-1]) / df['MA_fast'].iloc[-1] * 100),
                'distance_slow': float((df['Close'].iloc[-1] - df['MA_slow'].iloc[-1]) / df['MA_slow'].iloc[-1] * 100)
            })
        
        # Volatility-based position sizing
        if use_vol_scaling:
            current_vol = df['Volatility'].iloc[-1]
            avg_vol = df['Volatility'].rolling(window=60).mean().iloc[-1]
            
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
            position_size = 1.0 / vol_ratio  # Inverse volatility scaling
            
            for signal in signals:
                signal['volatility_ratio'] = float(vol_ratio)
                signal['position_size_multiplier'] = float(position_size)
                signal['recommended_size'] = 'REDUCE' if vol_ratio > 1.5 else 'INCREASE' if vol_ratio < 0.8 else 'NORMAL'
        
        return signals
    
    def calculate_momentum_score(self, df):
        """
        Calculate composite momentum score (0-100)
        """
        scores = []
        
        # 1. Price vs MA score (0-25)
        price_vs_fast = (df['Close'].iloc[-1] - df['MA_fast'].iloc[-1]) / df['MA_fast'].iloc[-1] * 100
        price_vs_slow = (df['Close'].iloc[-1] - df['MA_slow'].iloc[-1]) / df['MA_slow'].iloc[-1] * 100
        
        if price_vs_fast > 0 and price_vs_slow > 0:
            ma_score = min(25, (price_vs_fast + price_vs_slow) * 2)
        elif price_vs_fast < 0 and price_vs_slow < 0:
            ma_score = max(0, 25 + (price_vs_fast + price_vs_slow) * 2)
        else:
            ma_score = 12.5
        
        scores.append(ma_score)
        
        # 2. Trend persistence score (0-25)
        # Count days above/below MAs
        days_above_fast = (df['Close'] > df['MA_fast']).tail(20).sum()
        days_above_slow = (df['Close'] > df['MA_slow']).tail(60).sum()
        
        persistence_score = (days_above_fast / 20 * 12.5) + (days_above_slow / 60 * 12.5)
        scores.append(persistence_score)
        
        # 3. Volatility-adjusted momentum (0-25)
        returns = df['Returns'].tail(20).dropna()
        if len(returns) > 0:
            vol = returns.std() * np.sqrt(252)
            if vol > 0:
                sharpe_ratio = returns.mean() * 252 / vol
                vol_score = min(25, max(0, (sharpe_ratio + 2) * 6.25))
            else:
                vol_score = 12.5
        else:
            vol_score = 12.5
        scores.append(vol_score)
        
        # 4. Rate of change (0-25)
        if len(df) > 61:
            roc_20 = (df['Close'].iloc[-1] / df['Close'].iloc[-21] - 1) * 100
            roc_60 = (df['Close'].iloc[-1] / df['Close'].iloc[-61] - 1) * 100
        else:
            roc_20 = 0
            roc_60 = 0
        
        roc_score = min(25, (abs(roc_20) + abs(roc_60)) / 2)
        if (roc_20 > 0 and roc_60 > 0):
            roc_score = roc_score  # Positive momentum
        elif (roc_20 < 0 and roc_60 < 0):
            roc_score = 25 - roc_score  # Negative momentum
        else:
            roc_score = 12.5
        
        scores.append(roc_score)
        
        total_score = sum(scores)
        
        return {
            'momentum_score': float(total_score),
            'components': {
                'ma_alignment': float(scores[0]),
                'trend_persistence': float(scores[1]),
                'volatility_adjusted': float(scores[2]),
                'rate_of_change': float(scores[3])
            },
            'interpretation': 'BULLISH' if total_score > 60 else 'BEARISH' if total_score < 40 else 'NEUTRAL',
            'signal_strength': 'STRONG' if total_score > 75 or total_score < 25 else 'MODERATE' if total_score > 60 or total_score < 40 else 'WEAK'
        }
    
    def generate_trading_plan(self, df):
        """
        Generate complete trading plan with entry/exit/stops
        """
        signals = self.calculate_momentum_signals(df)
        momentum_score = self.calculate_momentum_score(df)
        
        if not signals:
            return {
                'action': 'HOLD',
                'reason': 'No clear momentum signals',
                'momentum_score': momentum_score
            }
        
        # Get strongest signal
        primary_signal = signals[0]
        
        # Determine entry/exit levels
        current_price = df['Close'].iloc[-1]
        fast_ma = df['MA_fast'].iloc[-1]
        slow_ma = df['MA_slow'].iloc[-1]
        atr = self.calculate_atr(df)
        
        if 'BULLISH' in primary_signal['type']:
            # Bullish setup
            entry = current_price
            stop_loss = min(fast_ma, slow_ma) - (atr * 2)
            target_1 = current_price + (atr * 3)
            target_2 = current_price + (atr * 5)
            
            action = 'BUY'
            confidence = min(0.9, momentum_score['momentum_score'] / 100)
            
        else:
            # Bearish setup
            entry = current_price
            stop_loss = max(fast_ma, slow_ma) + (atr * 2)
            target_1 = current_price - (atr * 3)
            target_2 = current_price - (atr * 5)
            
            action = 'SELL'
            confidence = min(0.9, (100 - momentum_score['momentum_score']) / 100)
        
        # Position sizing
        vol_ratio = primary_signal.get('volatility_ratio', 1.0)
        base_size = 1.0 / vol_ratio
        
        return {
            'action': action,
            'entry_price': float(entry),
            'stop_loss': float(stop_loss),
            'targets': [float(target_1), float(target_2)],
            'risk_reward': float(abs(entry - stop_loss) / abs(target_1 - entry)) if abs(target_1 - entry) != 0 else 0,
            'confidence': float(confidence),
            'momentum_score': momentum_score,
            'signals': signals,
            'position_size': {
                'base_size': float(base_size),
                'vol_adjusted_size': float(base_size * 0.7 if vol_ratio > 1.2 else base_size * 1.3 if vol_ratio < 0.8 else base_size),
                'recommendation': 'NORMAL' if 0.8 <= vol_ratio <= 1.2 else 'REDUCE' if vol_ratio > 1.2 else 'INCREASE'
            },
            'timeframe': 'SWING' if self.fast_ma >= 20 else 'DAY',
            'expiry_priority': 'WEEKLY' if self.fast_ma <= 20 else 'MONTHLY'
        }
    
    def calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else df['Close'].iloc[-1] * 0.02

# Momentum-based options strategy generator
class MomentumOptionsStrategies:
    """
    Generate options strategies based on momentum signals
    """
    
    @staticmethod
    def get_strategy_for_momentum(momentum_score, volatility_ratio, trend_direction):
        """
        Select optimal options strategy
        """
        if trend_direction == 'BULLISH':
            if momentum_score > 70 and volatility_ratio < 1.0:
                # Strong bullish, low vol
                return {
                    'strategy': 'BULL_CALL_SPREAD',
                    'description': 'Buy ITM/ATM call, sell OTM call',
                    'delta_range': [0.6, 0.8],
                    'position_size': 'LARGE',
                    'risk': 'LIMITED'
                }
            elif momentum_score > 70 and volatility_ratio > 1.2:
                # Strong bullish, high vol
                return {
                    'strategy': 'COVERED_CALL',
                    'description': 'Long stock + short OTM call',
                    'delta_range': [0.7, 0.9],
                    'position_size': 'MEDIUM',
                    'risk': 'LIMITED'
                }
            else:
                # Moderate bullish
                return {
                    'strategy': 'LONG_CALL',
                    'description': 'Buy ATM call',
                    'delta_range': [0.5, 0.6],
                    'position_size': 'SMALL',
                    'risk': 'LIMITED'
                }
        
        elif trend_direction == 'BEARISH':
            if momentum_score < 30 and volatility_ratio < 1.0:
                # Strong bearish, low vol
                return {
                    'strategy': 'BEAR_PUT_SPREAD',
                    'description': 'Buy ITM/ATM put, sell OTM put',
                    'delta_range': [-0.6, -0.8],
                    'position_size': 'LARGE',
                    'risk': 'LIMITED'
                }
            elif momentum_score < 30 and volatility_ratio > 1.2:
                # Strong bearish, high vol
                return {
                    'strategy': 'PROTECTIVE_PUT',
                    'description': 'Short stock + long OTM put',
                    'delta_range': [-0.7, -0.9],
                    'position_size': 'MEDIUM',
                    'risk': 'LIMITED'
                }
            else:
                # Moderate bearish
                return {
                    'strategy': 'LONG_PUT',
                    'description': 'Buy ATM put',
                    'delta_range': [-0.5, -0.6],
                    'position_size': 'SMALL',
                    'risk': 'LIMITED'
                }
        
        else:  # NEUTRAL
            if volatility_ratio > 1.5:
                # High volatility, range expected
                return {
                    'strategy': 'IRON_CONDOR',
                    'description': 'Sell OTM call spread + OTM put spread',
                    'delta_range': [-0.2, 0.2],
                    'position_size': 'MEDIUM',
                    'risk': 'LIMITED'
                }
            else:
                # Low volatility, breakout expected
                return {
                    'strategy': 'LONG_STRADDLE',
                    'description': 'Buy ATM call + ATM put',
                    'delta_range': [-0.5, 0.5],
                    'position_size': 'SMALL',
                    'risk': 'LIMITED'
                }
