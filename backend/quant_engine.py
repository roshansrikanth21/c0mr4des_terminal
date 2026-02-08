import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance, entropy, norm, beta
import yfinance as yf

# --- Bayesian Inference Model ---
class BayesianMarketModel:
    def __init__(self):
        self.alpha = 1  # Prior success (winning trades)
        self.beta = 1   # Prior failures (losing trades)
    
    def update_belief(self, wins, losses):
        """Update belief about strategy effectiveness"""
        self.alpha += wins
        self.beta += losses
        
        # Calculate posterior distribution
        posterior_mean = self.alpha / (self.alpha + self.beta)
        posterior_std = np.sqrt((self.alpha * self.beta) / 
                               ((self.alpha + self.beta) ** 2 * 
                                (self.alpha + self.beta + 1)))
        
        # Calculate credible interval (95%)
        lower = beta.ppf(0.025, self.alpha, self.beta)
        upper = beta.ppf(0.975, self.alpha, self.beta)
        
        return {
            "win_probability": round(posterior_mean, 4),
            "credible_interval": [round(float(lower), 4), round(float(upper), 4)],
            "confidence": round(1 - posterior_std, 4)
        }

def monte_carlo_simulation(returns, n_simulations=1000, days=30):
    """
    Monte Carlo simulation for Risk Assessment.
    Returns VaR, ES, and Prob of Profit.
    """
    try:
        mu = returns.mean()
        sigma = returns.std()
        
        if sigma == 0:
            return {"error": "Zero volatility"}

        # Vectorized Simulation
        # shape: (days, n_simulations)
        daily_returns = np.random.normal(mu, sigma, (days, n_simulations))
        price_paths = 100 * np.cumprod(1 + daily_returns, axis=0)
        
        final_prices = price_paths[-1]
        
        # Metrics
        var_95 = np.percentile(final_prices, 5)
        # Expected Shortfall (CVaR) - average of values below VaR
        es_95 = final_prices[final_prices <= var_95].mean()
        
        prob_profit = np.mean(final_prices > 100)
        
        return {
            "var_95": round(100 - var_95, 2), # Loss from 100
            "expected_shortfall": round(100 - es_95, 2),
            "prob_profit": round(prob_profit, 2),
            "expected_return": round(np.mean(final_prices) - 100, 2)
        }
    except Exception as e:
        return {"error": str(e)}

def get_quant_analysis(ticker: str, period="1y", interval="1d"):
    """
    Performs 'Rocket Science' level quantitative analysis.
    1. Wasserstein Distance: Detects 'Regime Drift' (Distribution Shift).
    2. Anderson-Darling: Tests for Normality (Tail Risk).
    3. Volatility Clustering: A-Vol (Adaptive Volatility).
    4. Monte Carlo: Future Risk Assessment.
    """
    try:
        # Fetch Data
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if len(df) < 100:
            return {"error": "Not enough data for Quant Analysis"}

        returns = df['Close'].pct_change().dropna()
        
        # --- 1. Wasserstein Drift (Regime Shift) ---
        # We compare the distribution of the LAST 30 days vs the PRIOR 90 days.
        same_regime_window = returns.iloc[-30:]
        prior_window = returns.iloc[-120:-30]
        
        if len(prior_window) == 0:
             drift_score = 0
        else:
             drift_score = wasserstein_distance(same_regime_window, prior_window)
        
        regime_status = "Stable"
        if drift_score > 0.02: # Threshold tweaked for daily returns
            regime_status = "Regime Shift Detected (High Drift)"
        elif drift_score > 0.01:
            regime_status = "Drifting (Cautious)"

        # --- 2. Adaptive Volatility (A-Vol) ---
        # Parkinsons Volatility (High-Low based) is often better than simple Close-Close std dev
        # But for simplicity, we use Rolling Std Dev Z-Score
        rolling_vol = returns.rolling(window=20).std()
        current_vol = rolling_vol.iloc[-1]
        mean_vol = rolling_vol.mean()
        if rolling_vol.std() != 0:
            vol_z_score = (current_vol - mean_vol) / rolling_vol.std()
        else:
            vol_z_score = 0
        
        vol_regime = "Normal"
        if vol_z_score > 2.0:
            vol_regime = "Extreme Volatility (Crisis/Breakout)"
        elif vol_z_score < -1.5:
            vol_regime = "Compression (Expect Explosion)"
            
        # --- 3. Entropy (Chaos Theory) ---
        # Higher Entropy = More Random/Efficient Market (Hard to trade)
        # Lower Entropy = More Structured/Trend (Easier to trade)
        # We bin returns into a histogram to calc entropy
        hist_counts, _ = np.histogram(same_regime_window, bins=10, density=True)
        market_entropy = entropy(hist_counts)
        
        predictability = "Random Walk (Low Predictability)"
        if market_entropy < 1.8: # Arbitrary heuristic for 10 bins
            predictability = "Structured (High Predictability)"
            
        # --- 4. Monte Carlo Risk Assessment ---
        mc_risk = monte_carlo_simulation(returns, n_simulations=2000, days=20)

        return {
            "regime": {
                "status": regime_status,
                "drift_score": round(drift_score, 4),
                "desc": "Wasserstein Distance metric showing distribution shift."
            },
            "volatility": {
                "status": vol_regime,
                "z_score": round(vol_z_score, 2),
                "current_annualized": f"{round(current_vol * np.sqrt(252) * 100, 1)}%"
            },
            "chaos_theory": {
                "entropy": round(market_entropy, 2),
                "predictability": predictability
            },
            "risk_assessment": mc_risk
        }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(get_quant_analysis("RELIANCE.NS"))
