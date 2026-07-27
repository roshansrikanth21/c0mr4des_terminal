"""
Volatility-based position sizing system
Automatically adjusts position size based on market volatility
"""

import math
import numpy as np
import pandas as pd
import yfinance as yf

try:
    from scipy.stats import norm
except ImportError:
    class norm:
        @staticmethod
        def ppf(q):
            # Normal distribution percent point function approximation (Winitzki)
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

class VolatilityPositionSizer:
    """
    Professional position sizing using volatility targeting
    """
    
    def __init__(self, capital=1000000, target_volatility=0.15, max_position_vol=0.02):
        """
        Args:
            capital: Total trading capital
            target_volatility: Annual target volatility (e.g., 0.15 for 15%)
            max_position_vol: Maximum volatility contribution from single position
        """
        self.capital = capital
        self.target_volatility = target_volatility
        self.max_position_vol = max_position_vol
        
    def calculate_position_size(self, instrument_volatility, correlation_matrix=None, 
                               portfolio_volatility=None, current_positions=None):
        """
        Calculate optimal position size using volatility targeting
        """
        base_weight = self.target_volatility / instrument_volatility if instrument_volatility > 0 else 0
        max_weight = self.max_position_vol / instrument_volatility if instrument_volatility > 0 else 0
        weight = min(base_weight, max_weight)
        
        position_value = self.capital * weight
        
        if correlation_matrix is not None and current_positions is not None:
            position_value = self._adjust_for_correlation(
                position_value, instrument_volatility, 
                correlation_matrix, current_positions
            )
        
        return {
            'position_value': float(position_value),
            'position_weight': float(weight),
            'instrument_volatility': float(instrument_volatility),
            'target_volatility_contribution': float(weight * instrument_volatility),
            'max_allowed_volatility': float(self.max_position_vol),
            'volatility_scaling_factor': float(self.target_volatility / instrument_volatility if instrument_volatility > 0 else 0),
            'risk_adjusted_size': 'LARGE' if weight > 0.05 else 'MEDIUM' if weight > 0.02 else 'SMALL'
        }
    
    def _adjust_for_correlation(self, position_value, instrument_volatility, 
                               correlation_matrix, current_positions):
        """
        Adjust position size based on correlation with existing positions
        """
        total_correlation_impact = 0
        count = 0
        
        for pos_name, pos_data in current_positions.items():
            if hasattr(correlation_matrix, 'columns') and pos_name in correlation_matrix.columns:
                correlation = correlation_matrix.loc['NEW', pos_name] if 'NEW' in correlation_matrix.index else 0
                pos_vol = pos_data.get('volatility', 0.2)
                pos_weight = pos_data.get('weight', 0.05)
                
                correlation_impact = correlation * pos_weight * pos_vol
                total_correlation_impact += correlation_impact
                count += 1
        
        if count > 0:
            avg_correlation_impact = total_correlation_impact / count
            
            if avg_correlation_impact > 0.3:
                adjustment_factor = 0.5
            elif avg_correlation_impact > 0.1:
                adjustment_factor = 0.7
            elif avg_correlation_impact < -0.3:
                adjustment_factor = 1.5
            elif avg_correlation_impact < -0.1:
                adjustment_factor = 1.2
            else:
                adjustment_factor = 1.0
            
            position_value *= adjustment_factor
        
        return position_value
    
    def calculate_stop_loss_level(self, entry_price, instrument_volatility, 
                                  confidence_level=0.95, time_horizon=1/252):
        """
        Calculate stop loss based on volatility
        """
        daily_vol = instrument_volatility / np.sqrt(252)
        z_score = norm.ppf(confidence_level)
        expected_move = daily_vol * z_score * np.sqrt(time_horizon * 252)
        
        stop_loss_long = entry_price * (1 - expected_move)
        stop_loss_short = entry_price * (1 + expected_move)
        
        return {
            'long_stop_loss': float(stop_loss_long),
            'short_stop_loss': float(stop_loss_short),
            'expected_move_pct': float(expected_move * 100),
            'confidence_level': confidence_level,
            'time_horizon_days': time_horizon * 252,
            'volatility_based': True
        }
    
    def calculate_position_size_for_option(self, option_price, underlying_volatility, 
                                          option_delta, option_vega):
        """
        Calculate position size for options considering Greeks
        """
        delta_exposure = option_delta * self.capital / 100
        vega_risk = option_vega * underlying_volatility * 0.01
        
        base_size = self.calculate_position_size(underlying_volatility)
        base_value = base_size['position_value']
        
        adjustment_factors = {
            'delta_adjustment': float(min(1.0, abs(option_delta))),
            'vega_adjustment': float(max(0.5, 1 - abs(vega_risk) / 100)),
            'time_decay_adjustment': 0.8
        }
        
        total_adjustment = float(np.prod(list(adjustment_factors.values())))
        option_position_value = base_value * total_adjustment
        contract_count = option_position_value / option_price if option_price > 0 else 0
        
        return {
            'contract_count': int(contract_count),
            'position_value': float(option_position_value),
            'delta_exposure': float(delta_exposure),
            'vega_risk': float(vega_risk),
            'adjustment_factors': adjustment_factors,
            'total_adjustment': float(total_adjustment)
        }

class RealTimeVolatilityMonitor:
    """
    Monitor market volatility and adjust positions in real-time
    """
    
    def __init__(self, tickers=None):
        self.tickers = tickers or ["^NSEI", "NIFTYBEES.NS", "BANKNIFTY.NS"]
        self.volatility_history = {}
        self.vol_regime = {}
        
    def update_volatility(self, interval="15m"):
        """
        Update volatility estimates for all tracked instruments
        """
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, period="5d", interval=interval, progress=False)
                
                if len(df) < 20:
                    continue
                
                close_series = _extract_series(df, 'Close')
                returns = close_series.pct_change().dropna()
                realized_vol = float(returns.std() * np.sqrt(252 * (24 if interval == "15m" else 1)))
                
                garch_vol = float(self._calculate_garch_volatility(returns))
                
                vix = self._get_india_vix() if ticker == "^NSEI" else None
                
                regime = self._determine_vol_regime(realized_vol, garch_vol, vix)
                
                self.volatility_history[ticker] = {
                    'timestamp': pd.Timestamp.now(),
                    'realized_vol': float(realized_vol),
                    'garch_vol': float(garch_vol),
                    'vix': float(vix) if vix else None,
                    'regime': regime,
                    'percentile': self._calculate_vol_percentile(ticker, realized_vol)
                }
                
                self.vol_regime[ticker] = regime
                
            except Exception as e:
                print(f"Error updating volatility for {ticker}: {e}")
        
        return self.volatility_history
    
    def _calculate_garch_volatility(self, returns, p=1, q=1):
        """
        Simple GARCH(1,1) volatility estimation with fallback
        """
        try:
            from arch import arch_model
            model = arch_model(returns * 100, vol='Garch', p=p, q=q, dist='normal')
            result = model.fit(disp='off')
            forecast = result.forecast(horizon=1)
            garch_vol = np.sqrt(forecast.variance.values[-1, 0]) / 100
            return garch_vol * np.sqrt(252)
        except Exception:
            return float(returns.std() * np.sqrt(252))
    
    def _get_india_vix(self):
        """Get India VIX data"""
        try:
            vix_data = yf.download("^INDIAVIX", period="1d", progress=False)
            if not vix_data.empty:
                close_series = _extract_series(vix_data, 'Close')
                return float(close_series.iloc[-1] / 100)
        except Exception:
            pass
        return None
    
    def _determine_vol_regime(self, realized_vol, garch_vol, vix=None):
        """Determine current volatility regime"""
        vol = vix if vix is not None else realized_vol
        
        if vol < 0.12:
            return "LOW_VOLATILITY"
        elif vol < 0.20:
            return "NORMAL_VOLATILITY"
        elif vol < 0.30:
            return "ELEVATED_VOLATILITY"
        elif vol < 0.40:
            return "HIGH_VOLATILITY"
        else:
            return "EXTREME_VOLATILITY"
    
    def _calculate_vol_percentile(self, ticker, current_vol):
        """Calculate percentile of current volatility vs history"""
        if current_vol < 0.15:
            return 30
        elif current_vol < 0.25:
            return 50
        elif current_vol < 0.35:
            return 75
        else:
            return 90
    
    def generate_trading_recommendations(self):
        """
        Generate volatility-based trading recommendations
        """
        recommendations = []
        
        for ticker, data in self.volatility_history.items():
            regime = data['regime']
            vol_level = data['realized_vol']
            
            if regime == "LOW_VOLATILITY":
                rec = {
                    'ticker': ticker,
                    'action': 'INCREASE_POSITION',
                    'reason': 'Low volatility environment, good for directional trades',
                    'size_adjustment': '+30%',
                    'strategy_recommendation': 'Directional options (calls/puts) or futures',
                    'risk_level': 'LOW'
                }
            elif regime in ["HIGH_VOLATILITY", "EXTREME_VOLATILITY"]:
                rec = {
                    'ticker': ticker,
                    'action': 'REDUCE_POSITION',
                    'reason': f'High volatility ({vol_level:.1%}), increase risk management',
                    'size_adjustment': '-50%',
                    'strategy_recommendation': 'Non-directional strategies (straddles, strangles)',
                    'risk_level': 'HIGH'
                }
            else:
                rec = {
                    'ticker': ticker,
                    'action': 'MAINTAIN',
                    'reason': 'Normal volatility environment',
                    'size_adjustment': '0%',
                    'strategy_recommendation': 'Standard strategies',
                    'risk_level': 'MEDIUM'
                }
            
            recommendations.append(rec)
        
        return recommendations
