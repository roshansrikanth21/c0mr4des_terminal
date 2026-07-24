"""
Market regime detection system
Identifies risk-on/risk-off, inflationary/deflationary regimes
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
try:
    from scipy.stats import norm
except ImportError:
    norm = None
import warnings
warnings.filterwarnings('ignore')

try:
    from backend.services.market_data_service import get_sync_market_data
    from backend.services.memory_service import memory_service
except ImportError:
    get_sync_market_data = None
    memory_service = None

class MarketRegimeDetector:
    """
    Detect market regimes using multiple indicators
    """
    
    def __init__(self):
        self.indicators = {}
        self.current_regime = None
        self.regime_history = []
        
    def _robust_fetch(self, ticker, period="5d"):
        try:
            if get_sync_market_data:
                # Use standardized service for caching and TrueData access
                df = get_sync_market_data(ticker, period=period, interval="1d")
            else:
                df = yf.download(ticker, period=period, progress=False)
                
            if df.empty: return None
            
            # Data from standardized service is already normalized
            return df if 'Close' in df.columns else None
        except Exception as e:
            print(f"   ⚠️ Regime Fetch Failed for {ticker}: {e}")
            return None

    def collect_macro_indicators(self):
        """
        Collect key macroeconomic indicators for regime detection
        """
        indicators = {}
        
        try:
            # 1. Yield curve (10Y - 2Y spread)
            print("   • Fetching Yield Curve data...")
            us10y_df = self._robust_fetch("^TNX")
            us2y_df = self._robust_fetch("^IRX")
            
            if us10y_df is not None and us2y_df is not None:
                us10y = us10y_df['Close'].iloc[-1] / 100
                us2y = us2y_df['Close'].iloc[-1] / 100
                yield_spread = us10y - us2y
                indicators['yield_spread'] = yield_spread
                indicators['yield_curve'] = 'INVERTED' if yield_spread < 0 else 'NORMAL' if yield_spread > 0.5 else 'FLAT'
            
            # 2. Volatility (VIX)
            print("   • Fetching VIX data...")
            vix_df = self._robust_fetch("^VIX")
            if vix_df is not None:
                vix = vix_df['Close'].iloc[-1] / 100
                indicators['vix'] = vix
                indicators['vol_regime'] = 'PANIC' if vix > 0.3 else 'ELEVATED' if vix > 0.2 else 'NORMAL'
            
            # 3. Dollar index
            print("   • Fetching Dollar Index...")
            dxy_df = self._robust_fetch("DX-Y.NYB")
            if dxy_df is not None:
                indicators['dxy'] = dxy_df['Close'].iloc[-1]
            
            # 4. Commodities (Gold, Oil)
            print("   • Fetching Commodities...")
            gold_df = self._robust_fetch("GC=F")
            oil_df = self._robust_fetch("CL=F")
            if gold_df is not None: indicators['gold'] = gold_df['Close'].iloc[-1]
            if oil_df is not None: indicators['oil'] = oil_df['Close'].iloc[-1]
            
            # 5. Indian market indicators
            print("   • Fetching Nifty returns...")
            nifty = self._robust_fetch("^NSEI", period="1mo")
            if nifty is not None:
                indicators['nifty_returns_1m'] = (nifty['Close'].iloc[-1] / nifty['Close'].iloc[0] - 1) * 100
                indicators['nifty_volatility'] = nifty['Close'].pct_change().std() * np.sqrt(252)
            
            # 6. India VIX
            print("   • Fetching India VIX...")
            india_vix_df = self._robust_fetch("^INDIAVIX")
            if india_vix_df is not None:
                indicators['india_vix'] = india_vix_df['Close'].iloc[-1] / 100
            
            # 7. USDINR
            print("   • Fetching USD/INR...")
            usdinr_df = self._robust_fetch("INR=X")
            if usdinr_df is not None:
                usdinr = usdinr_df['Close'].iloc[-1]
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
        
        # 1. Risk On/Off scoring
        vix = indicators.get('vix', 0.2)
        india_vix = indicators.get('india_vix', 0.2)
        
        if vix < 0.15 and india_vix < 0.15:
            regime_scores['RISK_ON'] += 3
        elif vix > 0.25 or india_vix > 0.25:
            regime_scores['RISK_OFF'] += 3
        
        # 2. Yield curve analysis
        yield_spread = indicators.get('yield_spread', 0)
        if yield_spread < 0:
            regime_scores['RECESSIONARY'] += 2
        elif yield_spread > 0.5:
            regime_scores['EXPANSIONARY'] += 2
        
        # 3. Market momentum
        nifty_returns = indicators.get('nifty_returns_1m', 0)
        if nifty_returns > 5:
            regime_scores['RISK_ON'] += 2
            regime_scores['EXPANSIONARY'] += 1
        elif nifty_returns < -5:
            regime_scores['RISK_OFF'] += 2
            regime_scores['RECESSIONARY'] += 1
        
        # Determine primary regime
        primary_regime = max(regime_scores, key=regime_scores.get)
        
        # Determine secondary regime
        temp_scores = regime_scores.copy()
        temp_scores[primary_regime] = -999
        secondary_regime = max(temp_scores, key=temp_scores.get)
        
        # Calculate regime confidence
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
        
        # [NEW] Check for regime shift and store in long-term memory
        prev_regime = self.regime_history[-1].get('primary_regime') if self.regime_history else None
        if primary_regime != prev_regime and memory_service:
            memory_service.add_memory(
                content=f"Market Regime Shift Detected: {prev_regime} -> {primary_regime}. Confidence: {confidence:.2f}",
                source="regime_detector",
                metadata={
                    "memory_type": "market",
                    "primary_regime": primary_regime,
                    "secondary_regime": secondary_regime,
                    "regime": primary_regime,
                    "confidence": confidence,
                    "sample_count": max(len(self.regime_history), 1),
                }
            )

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
                'options_strategy': 'BULL_CALL_SPREADS',
                'position_sizing': 'FULL'
            },
            'RISK_OFF': {
                'equities': 'UNDERWEIGHT',
                'bonds': 'OVERWEIGHT',
                'options_strategy': 'BEAR_PUT_SPREADS',
                'position_sizing': 'HALF'
            },
            'INFLATIONARY': {
                'equities': 'UNDERWEIGHT_GROWTH',
                'commodities': 'OVERWEIGHT',
                'options_strategy': 'COMMODITY_OPTIONS',
                'position_sizing': 'REDUCED'
            },
            'DEFLATIONARY': {
                'equities': 'UNDERWEIGHT',
                'bonds': 'OVERWEIGHT',
                'options_strategy': 'LONG_PUTS',
                'position_sizing': 'REDUCED'
            },
            'RECESSIONARY': {
                'equities': 'HEAVY_UNDERWEIGHT',
                'bonds': 'OVERWEIGHT',
                'options_strategy': 'PROTECTIVE_PUTS',
                'position_sizing': 'MINIMAL'
            },
            'EXPANSIONARY': {
                'equities': 'OVERWEIGHT',
                'bonds': 'UNDERWEIGHT',
                'options_strategy': 'LEVERAGED_CALLS',
                'position_sizing': 'FULL'
            }
        }
        
        return strategies.get(primary_regime, strategies['RISK_ON'])

class MarkovRegimeSwitching:
    """
    Simplified Markov switching model for regime detection based on volatility
    """
    
    def __init__(self, n_regimes=3):
        self.n_regimes = n_regimes
        self.transition_matrix = None
        
    def fit(self, returns):
        """
        Fit simplified threshold-based Markov switching
        """
        if returns.empty: return {}
        
        volatility = returns.rolling(window=20).std().dropna()
        if volatility.empty: return {}
        
        low_vol_threshold = volatility.expanding(min_periods=20).quantile(0.33)
        high_vol_threshold = volatility.expanding(min_periods=20).quantile(0.67)
        
        regimes = pd.Series(index=volatility.index, data='NORMAL')
        regimes[volatility < low_vol_threshold] = 'LOW_VOL'
        regimes[volatility > high_vol_threshold] = 'HIGH_VOL'
        
        # Calculate transition probabilities
        regime_values = ['LOW_VOL', 'NORMAL', 'HIGH_VOL']
        n = len(regime_values)
        transition_counts = np.zeros((n, n))
        
        for i in range(len(regimes) - 1):
            curr_r = regimes.iloc[i]
            next_r = regimes.iloc[i+1]
            curr_idx = regime_values.index(curr_r)
            next_idx = regime_values.index(next_r)
            transition_counts[curr_idx, next_idx] += 1
            
        self.transition_matrix = transition_counts / transition_counts.sum(axis=1, keepdims=True)
        self.transition_matrix = np.nan_to_num(self.transition_matrix, nan=1.0/n)
        
        return {
            'current_regime': regimes.iloc[-1],
            'transition_matrix': self.transition_matrix.tolist()
        }
