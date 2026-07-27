"""
Market regime detection system
Identifies risk-on/risk-off, inflationary/deflationary regimes
"""

import math
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    from scipy.stats import norm
except ImportError:
    class norm:
        @staticmethod
        def ppf(q):
            if q <= 0 or q >= 1:
                return 0.0
            if q == 0.5:
                return 0.0
            if q > 0.5:
                p = 1 - q
                sign = 1
            else:
                p = q
                sign = -1
            t = np.sqrt(-2.0 * np.log(p))
            c0, c1, c2 = 2.515517, 0.802853, 0.010328
            d1, d2, d3 = 1.432788, 0.189269, 0.001308
            num = c0 + t * (c1 + t * c2)
            den = 1.0 + t * (d1 + t * (d2 + t * d3))
            return sign * (t - num / den)

        @staticmethod
        def cdf(x):
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def _extract_series(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Helper to extract a 1D Series from a DataFrame whether columns are flat or MultiIndex."""
    if col_name in df.columns:
        res = df[col_name]
        if isinstance(res, pd.DataFrame):
            return res.iloc[:, 0]
        return res
    for col in df.columns:
        if isinstance(col, tuple) and col[0].lower() == col_name.lower():
            res = df[col]
            if isinstance(res, pd.DataFrame):
                return res.iloc[:, 0]
            return res
    raise KeyError(f"Column '{col_name}' not found in DataFrame columns: {df.columns}")

class MarketRegimeDetector:
    """
    Detect market regimes using multiple indicators
    """
    
    def __init__(self):
        self.indicators = {}
        self.current_regime = None
        self.regime_history = []
        
    def collect_macro_indicators(self):
        """
        Collect key macroeconomic indicators for regime detection
        """
        indicators = {}
        
        try:
            us10y_df = yf.download("^TNX", period="5d", progress=False)
            us2y_df = yf.download("^IRX", period="5d", progress=False)
            
            us10y = float(_extract_series(us10y_df, 'Close').iloc[-1]) / 100 if not us10y_df.empty else 0.04
            us2y = float(_extract_series(us2y_df, 'Close').iloc[-1]) / 100 if not us2y_df.empty else 0.035
            
            yield_spread = us10y - us2y
            indicators['yield_spread'] = float(yield_spread)
            indicators['yield_curve'] = 'INVERTED' if yield_spread < 0 else 'NORMAL' if yield_spread > 0.005 else 'FLAT'
            
            vix_df = yf.download("^VIX", period="5d", progress=False)
            vix = float(_extract_series(vix_df, 'Close').iloc[-1]) / 100 if not vix_df.empty else 0.15
            indicators['vix'] = vix
            indicators['vol_regime'] = 'PANIC' if vix > 0.3 else 'ELEVATED' if vix > 0.2 else 'NORMAL'
            
            dxy_df = yf.download("DX-Y.NYB", period="5d", progress=False)
            dxy = float(_extract_series(dxy_df, 'Close').iloc[-1]) if not dxy_df.empty else 103.0
            indicators['dxy'] = dxy
            
            gold_df = yf.download("GC=F", period="5d", progress=False)
            oil_df = yf.download("CL=F", period="5d", progress=False)
            indicators['gold'] = float(_extract_series(gold_df, 'Close').iloc[-1]) if not gold_df.empty else 2000.0
            indicators['oil'] = float(_extract_series(oil_df, 'Close').iloc[-1]) if not oil_df.empty else 75.0
            
            nifty = yf.download("^NSEI", period="5d", progress=False)
            if not nifty.empty:
                nifty_close = _extract_series(nifty, 'Close')
                indicators['nifty_returns_1m'] = float((nifty_close.iloc[-1] / nifty_close.iloc[0] - 1) * 100)
                indicators['nifty_volatility'] = float(nifty_close.pct_change().std() * np.sqrt(252))
            
            india_vix_df = yf.download("^INDIAVIX", period="5d", progress=False)
            india_vix = float(_extract_series(india_vix_df, 'Close').iloc[-1]) / 100 if not india_vix_df.empty else 0.14
            indicators['india_vix'] = india_vix
            
            usdinr_df = yf.download("INR=X", period="5d", progress=False)
            usdinr = float(_extract_series(usdinr_df, 'Close').iloc[-1]) if not usdinr_df.empty else 83.0
            indicators['usdinr'] = usdinr
            indicators['rupee_trend'] = 'WEAKENING' if usdinr > 83 else 'STRENGTHENING' if usdinr < 82 else 'STABLE'
            
        except Exception as e:
            print(f"Error collecting macro indicators: {e}")
        
        self.indicators = indicators
        return indicators
    
    def determine_regime(self, indicators=None):
        """
        Determine current market regime
        """
        if indicators is None:
            indicators = self.collect_macro_indicators()
        
        regime_scores = {
            'RISK_ON': 0,
            'RISK_OFF': 0,
            'INFLATIONARY': 0,
            'DEFLATIONARY': 0,
            'RECESSIONARY': 0,
            'EXPANSIONARY': 0
        }
        
        vix = indicators.get('vix', 0.2)
        india_vix = indicators.get('india_vix', 0.2)
        
        if vix < 0.15 and india_vix < 0.15:
            regime_scores['RISK_ON'] += 3
        elif vix > 0.25 or india_vix > 0.25:
            regime_scores['RISK_OFF'] += 3
        
        yield_spread = indicators.get('yield_spread', 0)
        if yield_spread < 0:
            regime_scores['RECESSIONARY'] += 2
        elif yield_spread > 0.01:
            regime_scores['EXPANSIONARY'] += 2
        
        usdinr = indicators.get('usdinr', 82.5)
        if usdinr > 83:
            regime_scores['INFLATIONARY'] += 1
        
        nifty_returns = indicators.get('nifty_returns_1m', 0)
        if nifty_returns > 5:
            regime_scores['RISK_ON'] += 2
            regime_scores['EXPANSIONARY'] += 1
        elif nifty_returns < -5:
            regime_scores['RISK_OFF'] += 2
            regime_scores['RECESSIONARY'] += 1
        
        primary_regime = max(regime_scores, key=regime_scores.get)
        
        temp_scores = regime_scores.copy()
        temp_scores[primary_regime] = -999
        secondary_regime = max(temp_scores, key=temp_scores.get)
        
        total_score = sum(regime_scores.values())
        confidence = regime_scores[primary_regime] / total_score if total_score > 0 else 0.5
        
        regime_info = {
            'primary_regime': primary_regime,
            'secondary_regime': secondary_regime,
            'confidence': float(confidence),
            'scores': regime_scores,
            'indicators': indicators,
            'timestamp': datetime.now().isoformat()
        }
        
        self.current_regime = regime_info
        self.regime_history.append(regime_info)
        
        return regime_info
    
    def get_regime_specific_strategies(self, regime_info):
        """
        Get trading strategies specific to current regime
        """
        primary_regime = regime_info['primary_regime']
        
        strategies = {
            'RISK_ON': {
                'equities': 'OVERWEIGHT',
                'bonds': 'UNDERWEIGHT',
                'currency': 'SHORT_USD',
                'commodities': 'NEUTRAL',
                'options_strategy': 'BULL_CALL_SPREADS',
                'risk_level': 'MEDIUM',
                'position_sizing': 'FULL',
                'hedging': 'MINIMAL'
            },
            'RISK_OFF': {
                'equities': 'UNDERWEIGHT',
                'bonds': 'OVERWEIGHT',
                'currency': 'LONG_USD',
                'commodities': 'UNDERWEIGHT',
                'options_strategy': 'BEAR_PUT_SPREADS',
                'risk_level': 'HIGH',
                'position_sizing': 'HALF',
                'hedging': 'MAXIMUM'
            },
            'INFLATIONARY': {
                'equities': 'UNDERWEIGHT_GROWTH',
                'bonds': 'UNDERWEIGHT',
                'currency': 'SHORT_LOCAL',
                'commodities': 'OVERWEIGHT',
                'options_strategy': 'COMMODITY_OPTIONS',
                'risk_level': 'HIGH',
                'position_sizing': 'REDUCED',
                'hedging': 'ESSENTIAL'
            },
            'DEFLATIONARY': {
                'equities': 'UNDERWEIGHT',
                'bonds': 'OVERWEIGHT',
                'currency': 'LONG_LOCAL',
                'commodities': 'UNDERWEIGHT',
                'options_strategy': 'LONG_PUTS',
                'risk_level': 'MEDIUM',
                'position_sizing': 'REDUCED',
                'hedging': 'MODERATE'
            },
            'RECESSIONARY': {
                'equities': 'HEAVY_UNDERWEIGHT',
                'bonds': 'OVERWEIGHT',
                'currency': 'DEFENSIVE',
                'commodities': 'UNDERWEIGHT',
                'options_strategy': 'PROTECTIVE_PUTS',
                'risk_level': 'VERY_HIGH',
                'position_sizing': 'MINIMAL',
                'hedging': 'MAXIMUM'
            },
            'EXPANSIONARY': {
                'equities': 'OVERWEIGHT',
                'bonds': 'UNDERWEIGHT',
                'currency': 'RISK_CURRENCIES',
                'commodities': 'NEUTRAL',
                'options_strategy': 'LEVERAGED_CALLS',
                'risk_level': 'MEDIUM_HIGH',
                'position_sizing': 'FULL',
                'hedging': 'MINIMAL'
            }
        }
        
        return strategies.get(primary_regime, strategies['RISK_ON'])

class MarkovRegimeSwitching:
    """
    Markov switching model for regime detection
    """
    
    def __init__(self, n_regimes=3):
        self.n_regimes = n_regimes
        self.transition_matrix = None
        self.regime_probabilities = None
        
    def fit(self, returns, n_regimes=None):
        """
        Fit Markov switching model to returns
        """
        if n_regimes:
            self.n_regimes = n_regimes
        
        volatility = returns.rolling(window=20).std()
        
        low_vol_threshold = volatility.quantile(0.33) if not volatility.empty else 0.01
        high_vol_threshold = volatility.quantile(0.67) if not volatility.empty else 0.02
        
        regimes = pd.Series(index=returns.index, data='NORMAL')
        regimes[volatility < low_vol_threshold] = 'LOW_VOL'
        regimes[volatility > high_vol_threshold] = 'HIGH_VOL'
        
        self._calculate_transition_probabilities(regimes)
        
        return {
            'regimes': regimes,
            'transition_matrix': self.transition_matrix,
            'regime_stats': self._calculate_regime_statistics(returns, regimes)
        }
    
    def _calculate_transition_probabilities(self, regimes):
        """
        Calculate Markov transition probabilities
        """
        regime_values = regimes.unique()
        n_regimes = len(regime_values)
        
        transition_counts = np.zeros((n_regimes, n_regimes))
        
        for i in range(len(regimes) - 1):
            current = np.where(regime_values == regimes.iloc[i])[0][0]
            next_r = np.where(regime_values == regimes.iloc[i+1])[0][0]
            transition_counts[current, next_r] += 1
        
        row_sums = transition_counts.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        self.transition_matrix = transition_counts / row_sums
        self.transition_matrix = np.nan_to_num(self.transition_matrix, nan=1/n_regimes)
        
        return self.transition_matrix
    
    def _calculate_regime_statistics(self, returns, regimes):
        """
        Calculate statistics for each regime
        """
        stats = {}
        
        for regime in regimes.unique():
            regime_returns = returns[regimes == regime]
            m_ret = float(regime_returns.mean() * 252) if not regime_returns.empty else 0.0
            std_ret = float(regime_returns.std() * np.sqrt(252)) if not regime_returns.empty else 0.0
            
            stats[str(regime)] = {
                'mean_return': m_ret,
                'volatility': std_ret,
                'sharpe_ratio': float(m_ret / std_ret) if std_ret > 0 else 0.0,
                'count': int(len(regime_returns)),
                'duration_days': float(self._calculate_regime_duration(regimes, regime))
            }
        
        return stats
    
    def _calculate_regime_duration(self, regimes, target_regime):
        """
        Calculate average duration of a regime
        """
        durations = []
        current_duration = 0
        
        for regime in regimes:
            if regime == target_regime:
                current_duration += 1
            elif current_duration > 0:
                durations.append(current_duration)
                current_duration = 0
        
        if current_duration > 0:
            durations.append(current_duration)
        
        return float(np.mean(durations)) if durations else 0.0
    
    def predict_next_regime(self, current_regime):
        """
        Predict next regime based on transition matrix
        """
        if self.transition_matrix is None:
            return None
        
        regime_values = ['LOW_VOL', 'NORMAL', 'HIGH_VOL']
        
        if current_regime in regime_values:
            current_idx = regime_values.index(current_regime)
            next_probs = self.transition_matrix[current_idx] if current_idx < len(self.transition_matrix) else [0.33]*3
            next_regime = regime_values[np.argmax(next_probs)]
            
            return {
                'next_regime': next_regime,
                'probabilities': dict(zip(regime_values, [float(p) for p in next_probs])),
                'confidence': float(np.max(next_probs))
            }
        
        return None
