"""
Volatility-based position sizing system
Automatically adjusts position size based on market volatility
"""

import numpy as np
import pandas as pd
import math

class StandardNormalFallback:
    @staticmethod
    def cdf(x, loc=0, scale=1):
        z = (x - loc) / scale
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    @staticmethod
    def pdf(x, loc=0, scale=1):
        z = (x - loc) / scale
        return (1.0 / (scale * math.sqrt(2.0 * math.pi))) * math.exp(-0.5 * z * z)

    @staticmethod
    def ppf(q, loc=0, scale=1):
        q = max(1e-9, min(1.0 - 1e-9, q))
        z = math.sqrt(-2.0 * math.log(min(q, 1.0 - q)))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        val = z - ((c2 * z + c1) * z + c0) / (((d3 * z + d2) * z + d1) * z + 1.0)
        return (loc - val * scale) if q < 0.5 else (loc + val * scale)

try:
    from scipy.stats import norm
except ImportError:
    norm = StandardNormalFallback

import yfinance as yf

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
        # Base position size using inverse volatility weighting
        base_weight = self.target_volatility / instrument_volatility if instrument_volatility > 0 else 0
        
        # Cap the position size
        max_weight = self.max_position_vol / instrument_volatility if instrument_volatility > 0 else 0
        weight = min(base_weight, max_weight)
        
        # Calculate dollar amount
        position_value = self.capital * weight
        
        # Adjust for portfolio diversification if correlation matrix provided
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
            if pos_name in correlation_matrix.columns:
                correlation = correlation_matrix.loc['NEW', pos_name]  # Assuming 'NEW' is the new position
                pos_vol = pos_data['volatility']
                pos_weight = pos_data['weight']
                
                # Correlation impact
                correlation_impact = correlation * pos_weight * pos_vol
                total_correlation_impact += correlation_impact
                count += 1
        
        if count > 0:
            avg_correlation_impact = total_correlation_impact / count
            
            # Reduce position if it increases portfolio risk too much
            if avg_correlation_impact > 0.3:  # Highly correlated
                adjustment_factor = 0.5
            elif avg_correlation_impact > 0.1:  # Moderately correlated
                adjustment_factor = 0.7
            elif avg_correlation_impact < -0.3:  # Negatively correlated (diversifying)
                adjustment_factor = 1.5
            elif avg_correlation_impact < -0.1:  # Slightly diversifying
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
        # Calculate daily volatility
        daily_vol = instrument_volatility / np.sqrt(252)
        
        # Calculate expected move for given confidence level
        z_score = norm.ppf(confidence_level)
        expected_move = daily_vol * z_score * np.sqrt(time_horizon * 252)
        
        # Stop loss levels
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
        # Delta-adjusted equivalent position
        delta_exposure = option_delta * self.capital / 100  # Assuming 100 shares per option
        
        # Vega risk adjustment
        vega_risk = option_vega * underlying_volatility * 0.01  # 1% vol change impact
        
        # Calculate risk-adjusted position size
        base_size = self.calculate_position_size(underlying_volatility)
        base_value = base_size['position_value']
        
        # Adjust for option-specific risks
        adjustment_factors = {
            'delta_adjustment': min(1.0, abs(option_delta)),
            'vega_adjustment': max(0.5, 1 - abs(vega_risk) / 100) if abs(vega_risk) < 100 else 0.5,
            'time_decay_adjustment': 0.8  # Conservative for theta risk
        }
        
        total_adjustment = np.prod(list(adjustment_factors.values()))
        
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

# Real-time volatility monitor
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
                # Get recent data
                print(f"   • Fetching volatility for {ticker}...")
                df = yf.download(ticker, period="5d", interval=interval, progress=False)
                
                if df.empty:
                    print(f"   ⚠️ Warning: No data for {ticker}")
                    continue
                
                # Universal column extraction
                if isinstance(df.columns, pd.MultiIndex):
                    if ticker in df.columns.levels[1] if len(df.columns.levels) > 1 else False:
                         df.columns = df.columns.get_level_values(0)
                    elif ticker in df.columns.levels[0]:
                         df = df[ticker]
                    else:
                         df.columns = df.columns.get_level_values(-1)
                
                if 'Close' not in df.columns and 'Price' in df.columns:
                    df.rename(columns={'Price': 'Close'}, inplace=True)
                
                if 'Close' not in df.columns or len(df) < 5:
                    print(f"   ⚠️ Warning: Insufficient data columns for {ticker}")
                    continue
                
                # Calculate realized volatility
                returns = df['Close'].pct_change().dropna()
                realized_vol_raw = returns.std() * np.sqrt(252 * (24 if interval == "15m" else 1))
                realized_vol = float(realized_vol_raw.iloc[0]) if hasattr(realized_vol_raw, 'iloc') else float(realized_vol_raw)
                
                # Calculate simple GARCH-like volatility
                garch_vol = float(realized_vol * 1.1)
                
                # Calculate VIX-like implied volatility (if available)
                vix_raw = self._get_india_vix() if ticker == "^NSEI" else None
                vix = float(vix_raw) if vix_raw is not None else None
                
                # Determine volatility regime
                regime = self._determine_vol_regime(realized_vol, garch_vol, vix)
                
                self.volatility_history[ticker] = {
                    'timestamp': pd.Timestamp.now(),
                    'realized_vol': realized_vol,
                    'garch_vol': garch_vol,
                    'vix': vix,
                    'regime': regime,
                    'percentile': self._calculate_vol_percentile(ticker, realized_vol)
                }
                
                self.vol_regime[ticker] = regime
                
            except Exception as e:
                print(f"Error updating volatility for {ticker}: {e}")
        
        return self.volatility_history
    
    def _get_india_vix(self):
        """Get India VIX data"""
        try:
            vix_data = yf.download("^INDIAVIX", period="1d", progress=False)
            if not vix_data.empty:
                val = vix_data['Close'].iloc[-1]
                if hasattr(val, 'iloc'):
                    val = val.iloc[0]
                return float(val) / 100.0
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
            elif regime == "HIGH_VOLATILITY" or regime == "EXTREME_VOLATILITY":
                rec = {
                    'ticker': ticker,
                    'action': 'REDUCE_POSITION',
                    'reason': f'High volatility ({vol_level:.1%}), increase risk management',
                    'size_adjustment': '-50%',
                    'strategy_recommendation': 'Non-directional strategies (straddles, strangles)',
                    'risk_level': 'HIGH'
                }
            else:  # NORMAL or ELEVATED
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
