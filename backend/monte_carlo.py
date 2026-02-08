"""
Monte Carlo Simulation for Options Trading Risk Assessment
Calculates Value at Risk, Expected Shortfall, and Profit Probabilities
"""

import numpy as np
import pandas as pd
from scipy.stats import norm, t
from datetime import datetime, timedelta
import yfinance as yf

class MonteCarloRiskAnalyzer:
    def __init__(self, ticker="^NSEI", n_simulations=10000):
        self.ticker = ticker
        self.n_simulations = n_simulations
        self.historical_data = None
        
    def fetch_historical_data(self, period="2y"):
        """Fetch historical data for the ticker"""
        try:
            df = yf.download(self.ticker, period=period, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            self.historical_data = df
            return True
        except Exception as e:
            print(f"Error fetching data: {e}")
            return False
    
    def simulate_price_paths(self, days_ahead=30, method='geometric_brownian'):
        """
        Simulate future price paths using Monte Carlo
        
        Methods:
        - 'geometric_brownian': Standard GBM model
        - 'historical': Bootstrapping from historical returns
        - 'garch': GARCH model for volatility clustering
        """
        if self.historical_data is None or self.historical_data.empty:
            if not self.fetch_historical_data():
                return None
        
        returns = self.historical_data['Close'].pct_change().dropna()
        
        if method == 'geometric_brownian':
            return self._gbm_simulation(returns, days_ahead)
        elif method == 'historical':
            return self._historical_bootstrap(returns, days_ahead)
        elif method == 'garch':
            return self._garch_simulation(returns, days_ahead)
        else:
            return self._gbm_simulation(returns, days_ahead)
    
    def _gbm_simulation(self, returns, days_ahead):
        """Geometric Brownian Motion simulation"""
        mu = returns.mean() * 252  # Annualized return
        sigma = returns.std() * np.sqrt(252)  # Annualized volatility
        S0 = self.historical_data['Close'].iloc[-1]
        
        dt = 1/252  # Daily steps
        simulations = []
        
        for _ in range(self.n_simulations):
            # Generate random path
            shock = np.random.normal(mu * dt, sigma * np.sqrt(dt), days_ahead)
            path = S0 * np.exp(np.cumsum(shock))
            simulations.append(path)
        
        return np.array(simulations)
    
    def _historical_bootstrap(self, returns, days_ahead):
        """Historical bootstrap simulation"""
        S0 = self.historical_data['Close'].iloc[-1]
        simulations = []
        
        for _ in range(self.n_simulations):
            # Randomly sample historical returns
            random_returns = np.random.choice(returns.values, size=days_ahead, replace=True)
            path = S0 * np.cumprod(1 + random_returns)
            simulations.append(path)
        
        return np.array(simulations)
    
    def _garch_simulation(self, returns, days_ahead):
        """GARCH simulation for volatility clustering"""
        # Simple GARCH(1,1) implementation
        from arch import arch_model
        
        try:
            model = arch_model(returns * 100, vol='Garch', p=1, q=1)
            fitted = model.fit(disp='off')
            
            # Forecast volatility
            forecast = fitted.forecast(horizon=days_ahead)
            conditional_volatility = np.sqrt(forecast.variance.values[-1, :])
            
            S0 = self.historical_data['Close'].iloc[-1]
            mu = returns.mean()
            simulations = []
            
            for _ in range(self.n_simulations):
                returns_sim = np.random.normal(mu, conditional_volatility)
                path = S0 * np.cumprod(1 + returns_sim)
                simulations.append(path)
            
            return np.array(simulations)
        except:
            # Fall back to GBM if GARCH fails
            return self._gbm_simulation(returns, days_ahead)
    
    def calculate_var_es(self, simulations, confidence_level=0.95):
        """Calculate Value at Risk and Expected Shortfall"""
        final_prices = simulations[:, -1]
        initial_price = simulations[0, 0]
        
        # Calculate returns
        returns = (final_prices - initial_price) / initial_price
        
        # Value at Risk
        var_percentile = np.percentile(returns, (1 - confidence_level) * 100)
        var_price = initial_price * (1 + var_percentile)
        
        # Expected Shortfall (Conditional VaR)
        es_returns = returns[returns <= var_percentile]
        es_percentile = es_returns.mean() if len(es_returns) > 0 else var_percentile
        es_price = initial_price * (1 + es_percentile)
        
        return {
            "var_percent": float(var_percentile * 100),
            "var_price": float(var_price),
            "es_percent": float(es_percentile * 100),
            "es_price": float(es_price),
            "confidence_level": confidence_level
        }
    
    def calculate_option_risk(self, spot_price, strike, days_to_expiry, iv, option_type="CE"):
        """Calculate risk metrics for options positions"""
        # Simulate underlying price paths
        simulations = self.simulate_price_paths(days_ahead=days_to_expiry)
        if simulations is None:
            return None
        
        # Calculate option payoff for each simulation
        payoffs = []
        for path in simulations:
            final_price = path[-1]
            
            if option_type == "CE":
                payoff = max(final_price - strike, 0)
            else:  # PE
                payoff = max(strike - final_price, 0)
            
            # Discount for time (simple discounting)
            # In reality, you'd use Black-Scholes at each point
            payoffs.append(payoff)
        
        payoffs = np.array(payoffs)
        
        # Calculate risk metrics
        var_95 = np.percentile(payoffs, 5)  # 95% VaR
        expected_shortfall = payoffs[payoffs <= var_95].mean()
        
        # Probability metrics
        prob_profit = np.mean(payoffs > 0)
        prob_50_percent_profit = np.mean(payoffs > (payoffs.max() * 0.5))
        
        # Expected value
        expected_payoff = payoffs.mean()
        std_payoff = payoffs.std()
        
        return {
            "expected_payoff": float(expected_payoff),
            "std_payoff": float(std_payoff),
            "var_95": float(var_95),
            "expected_shortfall": float(expected_shortfall),
            "probabilities": {
                "any_profit": float(prob_profit),
                "50_percent_max_profit": float(prob_50_percent_profit),
                "breakeven": float(np.mean(payoffs >= 0))
            },
            "risk_reward": {
                "sharpe_ratio": float(expected_payoff / std_payoff if std_payoff > 0 else 0),
                "sortino_ratio": self._calculate_sortino_ratio(payoffs),
                "max_drawdown": float(self._calculate_max_drawdown(payoffs))
            },
            "summary": self._generate_option_risk_summary(payoffs, option_type)
        }
    
    def _calculate_sortino_ratio(self, returns, risk_free_rate=0.05/252):
        """Calculate Sortino ratio (downside risk adjusted)"""
        downside_returns = returns[returns < risk_free_rate]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else 0
        
        if downside_std > 0:
            return (returns.mean() - risk_free_rate) / downside_std
        return 0
    
    def _calculate_max_drawdown(self, values):
        """Calculate maximum drawdown"""
        peak = values[0]
        max_dd = 0
        
        for value in values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    def _generate_option_risk_summary(self, payoffs, option_type):
        """Generate human-readable risk summary"""
        avg_payoff = payoffs.mean()
        median_payoff = np.median(payoffs)
        
        if option_type == "CE":
            option_type_name = "Call"
        else:
            option_type_name = "Put"
        
        if avg_payoff <= 0:
            risk_level = "HIGH"
            recommendation = "Avoid - Expected value negative"
        elif avg_payoff < median_payoff:
            risk_level = "MEDIUM_HIGH"
            recommendation = "Caution - Potential for losses"
        elif np.mean(payoffs > 0) > 0.6:
            risk_level = "MEDIUM"
            recommendation = "Moderate risk - Positive expected value"
        else:
            risk_level = "LOW_MEDIUM"
            recommendation = "Favorable risk/reward"
        
        return {
            "risk_level": risk_level,
            "recommendation": recommendation,
            "expected_value_positive": bool(avg_payoff > 0),
            "probability_positive": float(np.mean(payoffs > 0)),
            "worst_case": float(payoffs.min()),
            "best_case": float(payoffs.max())
        }
    
    def portfolio_risk_analysis(self, positions):
        """
        Analyze risk for a portfolio of options positions
        
        positions = [
            {
                'type': 'CE' or 'PE',
                'strike': float,
                'quantity': int,
                'premium': float,
                'days_to_expiry': int,
                'iv': float
            },
            ...
        ]
        """
        if not positions:
            return {"error": "No positions provided"}
        
        # Simulate underlying paths
        max_days = max(pos['days_to_expiry'] for pos in positions)
        simulations = self.simulate_price_paths(days_ahead=max_days)
        
        if simulations is None:
            return {"error": "Failed to simulate price paths"}
        
        portfolio_payoffs = np.zeros(self.n_simulations)
        
        for pos in positions:
            # Calculate payoff for this position
            pos_payoffs = []
            for i in range(self.n_simulations):
                # Get price at expiry for this position
                expiry_idx = min(pos['days_to_expiry'], len(simulations[i])) - 1
                expiry_price = simulations[i, expiry_idx]
                
                if pos['type'] == 'CE':
                    payoff = max(expiry_price - pos['strike'], 0) - pos['premium']
                else:  # PE
                    payoff = max(pos['strike'] - expiry_price, 0) - pos['premium']
                
                pos_payoffs.append(payoff * pos['quantity'])
            
            # Add to portfolio
            portfolio_payoffs += np.array(pos_payoffs)
        
        # Calculate portfolio risk metrics
        var_95 = np.percentile(portfolio_payoffs, 5)
        expected_shortfall = portfolio_payoffs[portfolio_payoffs <= var_95].mean()
        
        # Correlation analysis (simplified)
        if len(positions) > 1:
            # Generate correlation matrix of payoffs
            corr_matrix = self._calculate_position_correlations(positions, simulations)
        else:
            corr_matrix = None
        
        return {
            "portfolio_metrics": {
                "expected_value": float(portfolio_payoffs.mean()),
                "std_deviation": float(portfolio_payoffs.std()),
                "var_95": float(var_95),
                "expected_shortfall": float(expected_shortfall),
                "prob_positive": float(np.mean(portfolio_payoffs > 0)),
                "prob_negative": float(np.mean(portfolio_payoffs < 0)),
                "max_loss": float(portfolio_payoffs.min()),
                "max_gain": float(portfolio_payoffs.max())
            },
            "correlation_analysis": corr_matrix,
            "risk_assessment": self._assess_portfolio_risk(portfolio_payoffs)
        }
    
    def _calculate_position_correlations(self, positions, simulations):
        """Calculate correlation between positions"""
        n_positions = len(positions)
        payoffs_matrix = np.zeros((self.n_simulations, n_positions))
        
        for j, pos in enumerate(positions):
            pos_payoffs = []
            for i in range(self.n_simulations):
                expiry_idx = min(pos['days_to_expiry'], len(simulations[i])) - 1
                expiry_price = simulations[i, expiry_idx]
                
                if pos['type'] == 'CE':
                    payoff = max(expiry_price - pos['strike'], 0) - pos['premium']
                else:
                    payoff = max(pos['strike'] - expiry_price, 0) - pos['premium']
                
                pos_payoffs.append(payoff)
            
            payoffs_matrix[:, j] = pos_payoffs
        
        # Calculate correlation matrix
        corr_matrix = np.corrcoef(payoffs_matrix.T)
        
        # Convert to dictionary format
        corr_dict = {}
        for i in range(n_positions):
            for j in range(i+1, n_positions):
                key = f"Pos{i+1}_vs_Pos{j+1}"
                corr_dict[key] = {
                    "correlation": float(corr_matrix[i, j]),
                    "interpretation": self._interpret_correlation(corr_matrix[i, j])
                }
        
        return corr_dict
    
    def _interpret_correlation(self, corr):
        """Interpret correlation value"""
        if corr > 0.7:
            return "HIGHLY_POSITIVE - Positions move together"
        elif corr > 0.3:
            return "POSITIVE - Some co-movement"
        elif corr > -0.3:
            return "NEUTRAL - Little relationship"
        elif corr > -0.7:
            return "NEGATIVE - Some diversification benefit"
        else:
            return "HIGHLY_NEGATIVE - Good diversification"
    
    def _assess_portfolio_risk(self, portfolio_payoffs):
        """Assess overall portfolio risk"""
        expected_value = portfolio_payoffs.mean()
        var_95 = np.percentile(portfolio_payoffs, 5)
        
        if expected_value < 0:
            return {
                "risk_level": "VERY_HIGH",
                "action": "REDUCE_POSITIONS",
                "reason": "Negative expected value",
                "details": "Portfolio is expected to lose money"
            }
        elif var_95 < -expected_value * 2:
            return {
                "risk_level": "HIGH",
                "action": "HEDGE",
                "reason": "High downside risk relative to upside",
                "details": f"95% VaR: {var_95:.2f}, Expected: {expected_value:.2f}"
            }
        elif np.mean(portfolio_payoffs > 0) > 0.6:
            return {
                "risk_level": "MODERATE",
                "action": "MONITOR",
                "reason": "Positive expected value with reasonable risk",
                "details": f"Probability of profit: {np.mean(portfolio_payoffs > 0):.1%}"
            }
        else:
            return {
                "risk_level": "LOW_MODERATE",
                "action": "HOLD",
                "reason": "Favorable risk/reward profile",
                "details": f"Expected: {expected_value:.2f}, Std: {portfolio_payoffs.std():.2f}"
            }

# Quick risk assessment function
def quick_risk_assessment(ticker="^NSEI", days_ahead=30, n_simulations=5000):
    """Quick Monte Carlo risk assessment"""
    analyzer = MonteCarloRiskAnalyzer(ticker, n_simulations)
    simulations = analyzer.simulate_price_paths(days_ahead)
    
    if simulations is None:
        return {"error": "Failed to simulate"}
    
    risk_metrics = analyzer.calculate_var_es(simulations)
    
    # Additional metrics
    initial_price = simulations[0, 0]
    final_prices = simulations[:, -1]
    
    return {
        "initial_price": float(initial_price),
        "expected_price": float(final_prices.mean()),
        "price_std": float(final_prices.std()),
        "confidence_intervals": {
            "90%": [
                float(np.percentile(final_prices, 5)),
                float(np.percentile(final_prices, 95))
            ],
            "95%": [
                float(np.percentile(final_prices, 2.5)),
                float(np.percentile(final_prices, 97.5))
            ]
        },
        "probability_up_10%": float(np.mean(final_prices > initial_price * 1.1)),
        "probability_down_10%": float(np.mean(final_prices < initial_price * 0.9)),
        "risk_metrics": risk_metrics
    }

if __name__ == "__main__":
    # Test Monte Carlo analysis
    print("Testing Monte Carlo Risk Analyzer...")
    
    analyzer = MonteCarloRiskAnalyzer("^NSEI", n_simulations=1000)
    
    # Quick risk assessment
    result = quick_risk_assessment("^NSEI", days_ahead=30)
    
    print(f"Initial Price: {result['initial_price']:.2f}")
    print(f"Expected Price in 30 days: {result['expected_price']:.2f}")
    print(f"95% VaR: {result['risk_metrics']['var_percent']:.2f}%")
    print(f"Probability of 10% gain: {result['probability_up_10%']:.1%}")
