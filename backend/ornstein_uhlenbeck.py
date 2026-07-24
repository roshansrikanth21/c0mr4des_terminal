"""
Ornstein-Uhlenbeck Process for Mean Reversion Trading
Ideal for Nifty/Sensex range-bound markets
"""

import numpy as np
import pandas as pd
try:
    from scipy.optimize import minimize
    from scipy.stats import norm
except ImportError:
    minimize = None
    norm = None
import yfinance as yf

class OrnsteinUhlenbeckStrategy:
    """
    OU Process for detecting mean reversion opportunities
    θ = speed of reversion, μ = mean level, σ = volatility
    dX(t) = θ(μ - X(t))dt + σ dW(t)
    """
    
    def __init__(self, ticker="^NSEI"):
        self.ticker = ticker
        self.theta = None  # Speed of mean reversion
        self.mu = None     # Long-term mean
        self.sigma = None  # Volatility
        self.half_life = None  # Time for deviation to halve
    
    def calibrate_ou_parameters(self, prices, dt=1/252, window=None):
        """
        Calibrate OU parameters using MLE (Maximum Likelihood Estimation)
        """
        if window is not None and len(prices) > window:
            prices = prices[-window:]
        if len(prices) < 2:
            return None
            
        returns = np.diff(np.log(prices))
        n = len(returns)
        
        # MLE formulas for OU process
        Sx = np.sum(prices[:-1])
        Sy = np.sum(prices[1:])
        Sxx = np.sum(prices[:-1] ** 2)
        Syy = np.sum(prices[1:] ** 2)
        Sxy = np.sum(prices[:-1] * prices[1:])
        
        # MLE estimators
        mu_numer = (Sy * Sxx - Sx * Sxy)
        mu_denom = (n * (Sxx - Sxy) - (Sx ** 2 - Sx * Sy))
        
        if abs(mu_denom) < 1e-9:
             mu = np.mean(prices) # Fallback
        else:
             mu = mu_numer / mu_denom

        theta_arg = (Sxy - mu * Sx - mu * Sy + n * mu ** 2) / (Sxx - 2 * mu * Sx + n * mu ** 2)
        # Ensure argument for log is positive
        if theta_arg <= 0:
            theta = 0.001
        else:
            theta = -np.log(theta_arg) / dt
            
        sigma_sq_numer = (Syy - 2 * np.exp(-theta * dt) * Sxy + 
                        np.exp(-2 * theta * dt) * Sxx - 
                        2 * mu * (1 - np.exp(-theta * dt)) * 
                        (Sy - np.exp(-theta * dt) * Sx) + 
                        n * mu ** 2 * (1 - np.exp(-theta * dt)) ** 2)
        
        sigma_sq = (2 * theta * sigma_sq_numer) / (n * (1 - np.exp(-2*theta*dt)))
        
        # Ensure stability
        if sigma_sq < 0: sigma_sq = 0
        
        sigma = np.sqrt(sigma_sq)
        theta = max(0.001, min(theta, 100))
        
        self.theta = float(theta)
        self.mu = float(mu)
        self.sigma = float(sigma)
        self.half_life = float(np.log(2) / theta) if theta > 0 else 0.0
        
        return {
            'theta': self.theta,
            'mu': self.mu,
            'sigma': self.sigma,
            'half_life_days': float(self.half_life / dt) if dt > 0 else 0.0,
            'volatility_annual': float(sigma * np.sqrt(1/dt)) if dt > 0 else 0.0
        }
    
    def calculate_z_score(self, prices, window=None):
        """
        Calculate Z-score for mean reversion trading
        Z = (X - μ) / (σ / √(2θ))
        """
        self.calibrate_ou_parameters(prices, window=window)
        
        current_price = prices[-1]
        
        # Theoretical standard deviation
        sigma_eq = self.sigma / np.sqrt(2 * self.theta) if self.theta > 0 else self.sigma
        
        if sigma_eq == 0:
            z_score = 0
        else:
            z_score = (current_price - self.mu) / sigma_eq
        
        # Ensure scalar conversion
        if hasattr(z_score, "item"): z_score = z_score.item()
        if hasattr(current_price, "item"): current_price = current_price.item()
        
        return {
            'z_score': float(z_score),
            'current_price': float(current_price),
            'mean': float(self.mu),
            'deviation_pct': float((current_price - self.mu) / self.mu * 100) if self.mu != 0 else 0,
            'sigma_eq': float(sigma_eq),
            'half_life_days': float(self.half_life * 252) if self.half_life else 0 
        }
    
    def generate_ou_signals(self, prices, entry_z=1.5, exit_z=0.5, window=60):
        """
        Generate mean reversion trading signals
        """
        z_data = self.calculate_z_score(prices, window=window)
        z_score = z_data['z_score']
        current_price = float(prices.iloc[-1]) if hasattr(prices, 'iloc') else float(prices[-1])
        
        signals = []
        
        # Short signal (overbought)
        if z_score > entry_z:
            target_price = float(self.mu)
            sigma_eq = float(z_data['sigma_eq'])
            stop_loss = current_price + (2 * sigma_eq)
            
            signals.append({
                'type': 'OU_MEAN_REVERSION_SHORT',
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'target': target_price,
                'z_score': float(z_score),
                'confidence': min(abs(float(z_score)) / 3, 0.9),
                'reason': f'Overbought: Z-score {z_score:.2f} > {entry_z}',
                'expected_hold_days': float(self.half_life) if self.half_life else 0,
                'risk_reward': float((current_price - target_price) / (stop_loss - current_price)) if (stop_loss - current_price) != 0 else 0
            })
        
        # Long signal (oversold)
        elif z_score < -entry_z:
            target_price = float(self.mu)
            sigma_eq = float(z_data['sigma_eq'])
            stop_loss = current_price - (2 * sigma_eq)
            
            signals.append({
                'type': 'OU_MEAN_REVERSION_LONG',
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'target': target_price,
                'z_score': float(z_score),
                'confidence': min(abs(float(z_score)) / 3, 0.9),
                'reason': f'Oversold: Z-score {z_score:.2f} < -{entry_z}',
                'expected_hold_days': float(self.half_life) if self.half_life else 0,
                'risk_reward': float((target_price - current_price) / (current_price - stop_loss)) if (current_price - stop_loss) != 0 else 0
            })
        
        return {
            'signals': signals,
            'ou_parameters': {
                'z_score': float(z_score),
                'mean': float(self.mu),
                'half_life_days': float(self.half_life * 252) if self.half_life else 0,
                'current_vs_mean_pct': float((current_price - self.mu) / self.mu * 100) if self.mu else 0
            }
        }
    
    def forecast_price_path(self, current_price, days_ahead=10, n_simulations=1000):
        """
        Monte Carlo simulation of OU process
        """
        if self.theta is None or self.mu is None or self.sigma is None:
            return None
        
        dt = 1/252  # Daily steps
        paths = []
        
        for _ in range(n_simulations):
            price_path = [current_price]
            price = current_price
            
            for _ in range(days_ahead):
                # OU process: dX = θ(μ - X)dt + σ dW
                drift = self.theta * (self.mu - price) * dt
                diffusion = self.sigma * np.sqrt(dt) * np.random.normal()
                price = price + drift + diffusion
                price_path.append(price)
            
            paths.append(price_path)
        
        paths = np.array(paths)
        
        # Calculate confidence intervals
        percentiles = np.percentile(paths[:, -1], [5, 25, 50, 75, 95])
        
        return {
            'current_price': float(current_price),
            'mean_forecast': float(np.mean(paths[:, -1])),
            'confidence_90': [float(percentiles[0]), float(percentiles[4])],
            'probability_up': float(np.mean(paths[:, -1] > current_price))
        }

class RealTimeOUTrading:
    """Real-time OU trading system for Indian markets"""
    
    def __init__(self, ticker="^NSEI", window_days=90):
        self.ticker = ticker
        self.window_days = window_days
        self.ou_model = OrnsteinUhlenbeckStrategy(ticker)
        self.current_signals = []
        
    def update_and_get_signals(self, interval="15m"):
        """Update OU model and get latest signals"""
        try:
            # Get recent data (prefer shared provider service if available)
            try:
                from backend.services.market_data_service import get_sync_market_data
            except ImportError:
                get_sync_market_data = None

            if get_sync_market_data:
                df = get_sync_market_data(self.ticker, f"{self.window_days}d", interval)
            else:
                df = yf.download(self.ticker, period=f"{self.window_days}d", interval=interval, progress=False)
            
            if df.empty or len(df) < 50:
                return None
            
            # Data is already normalized if it comes from get_sync_market_data
            # But we double check for safety
            if 'Close' not in df.columns:
                 print(f"❌ Error in OU update: 'Close' column missing for {self.ticker}")
                 return None
            
            prices = df['Close'].values
            
            # Use float conversion to ensure scalar
            prices = prices.astype(float)
            
            # Calibrate OU parameters with trailing window
            params = self.ou_model.calibrate_ou_parameters(prices, window=60)
            
            # Generate signals
            signals_data = self.ou_model.generate_ou_signals(prices, window=60)
            
            # Forecast
            forecast = self.ou_model.forecast_price_path(prices[-1], days_ahead=5)
            
            self.current_signals = signals_data['signals']
            
            return {
                'timestamp': pd.Timestamp.now().isoformat(),
                'current_price': float(prices[-1]),
                'ou_parameters': params,
                'signals': signals_data['signals'],
                'z_score_info': self.ou_model.calculate_z_score(prices, window=60),
                'forecast': forecast,
                'market_regime': self._determine_regime(params, prices)
            }
        except Exception as e:
            import traceback
            print(f"❌ Error in OU update: {e}")
            traceback.print_exc()
            return None
    
    def _determine_regime(self, params, prices):
        """Determine market regime based on OU parameters"""
        if not params: return "UNKNOWN"
        half_life = params['half_life_days']
        
        if half_life < 10:
            return "MEAN_REVERTING_FAST"
        elif half_life < 30:
            return "MEAN_REVERTING_SLOW"
        elif half_life > 60: # Adjusted threshold
            return "TRENDING"
        else:
            return "NEUTRAL"
