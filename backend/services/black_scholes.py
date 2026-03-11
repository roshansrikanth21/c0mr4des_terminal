"""
Black-Scholes Options Pricing Model for AI Trading System
Implements European options pricing with Greeks calculation
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any
from scipy import stats
from datetime import datetime, timedelta

class BlackScholesModel:
    """
    Black-Scholes options pricing model with Greeks calculation
    """
    
    @staticmethod
    def norm_cdf(x: float) -> float:
        """Normal cumulative distribution function"""
        return stats.norm.cdf(x)
    
    @staticmethod
    def norm_pdf(x: float) -> float:
        """Normal probability density function"""
        return stats.norm.pdf(x)
    
    @staticmethod
    def calculate_d1(
        S: float,  # Underlying price
        K: float,  # Strike price
        T: float,  # Time to expiration (years)
        r: float,  # Risk-free rate
        sigma: float  # Volatility
    ) -> float:
        """Calculate d1 parameter for Black-Scholes"""
        return (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    
    @staticmethod
    def calculate_d2(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        d1: float
    ) -> float:
        """Calculate d2 parameter for Black-Scholes"""
        return d1 - sigma * np.sqrt(T)
    
    @classmethod
    def european_call_price(
        cls,
        S: float,  # Underlying price
        K: float,  # Strike price
        T: float,  # Time to expiration (years)
        r: float,  # Risk-free rate
        sigma: float  # Volatility
    ) -> float:
        """
        Calculate European call option price using Black-Scholes
        
        Args:
            S: Current stock price
            K: Option strike price
            T: Time to expiration in years
            r: Risk-free interest rate
            sigma: Volatility of the underlying
            
        Returns:
            Call option price
        """
        if T <= 0:
            return max(0, S - K)  # Expired or at expiration
        
        if sigma <= 0:
            return max(0, S - K)  # No volatility
        
        d1 = cls.calculate_d1(S, K, T, r, sigma)
        d2 = cls.calculate_d2(S, K, T, r, sigma, d1)
        
        call_price = (S * cls.norm_cdf(d1) - 
                     K * np.exp(-r * T) * cls.norm_cdf(d2))
        
        return max(0, call_price)  # Can't be negative
    
    @classmethod
    def european_put_price(
        cls,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float
    ) -> float:
        """
        Calculate European put option price using Black-Scholes
        
        Args:
            S: Current stock price
            K: Option strike price
            T: Time to expiration in years
            r: Risk-free interest rate
            sigma: Volatility of the underlying
            
        Returns:
            Put option price
        """
        if T <= 0:
            return max(0, K - S)  # Expired or at expiration
        
        if sigma <= 0:
            return max(0, K - S)  # No volatility
        
        d1 = cls.calculate_d1(S, K, T, r, sigma)
        d2 = cls.calculate_d2(S, K, T, r, sigma, d1)
        
        put_price = (K * np.exp(-r * T) * cls.norm_cdf(-d2) - 
                    S * cls.norm_cdf(-d1))
        
        return max(0, put_price)  # Can't be negative
    
    @classmethod
    def calculate_greeks(
        cls,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = 'call'
    ) -> Dict[str, float]:
        """
        Calculate option Greeks
        
        Args:
            S: Current stock price
            K: Option strike price
            T: Time to expiration in years
            r: Risk-free interest rate
            sigma: Volatility of the underlying
            option_type: 'call' or 'put'
            
        Returns:
            Dictionary with all Greeks
        """
        if T <= 0 or sigma <= 0:
            return {
                'delta': 0.0,
                'gamma': 0.0,
                'theta': 0.0,
                'vega': 0.0,
                'rho': 0.0
            }
        
        d1 = cls.calculate_d1(S, K, T, r, sigma)
        d2 = cls.calculate_d2(S, K, T, r, sigma, d1)
        
        sqrt_T = np.sqrt(T)
        exp_rT = np.exp(-r * T)
        norm_pdf_d1 = cls.norm_pdf(d1)
        
        # Delta - rate of change of option price with respect to underlying price
        if option_type.lower() == 'call':
            delta = cls.norm_cdf(d1)
        else:  # put
            delta = cls.norm_cdf(d1) - 1
        
        # Gamma - rate of change of delta with respect to underlying price
        gamma = norm_pdf_d1 / (S * sigma * sqrt_T)
        
        # Theta - time decay of option price
        if option_type.lower() == 'call':
            theta = (-(S * norm_pdf_d1 * sigma) / (2 * sqrt_T) -
                   r * K * exp_rT * cls.norm_cdf(d2))
        else:  # put
            theta = (-(S * norm_pdf_d1 * sigma) / (2 * sqrt_T) +
                   r * K * exp_rT * cls.norm_cdf(-d2))
        
        # Convert theta to daily (per day instead of per year)
        theta_daily = theta / 365.0
        
        # Vega - sensitivity to volatility
        vega = S * sqrt_T * norm_pdf_d1
        
        # Rho - sensitivity to interest rate
        if option_type.lower() == 'call':
            rho = K * T * exp_rT * cls.norm_cdf(d2)
        else:  # put
            rho = -K * T * exp_rT * cls.norm_cdf(-d2)
        
        return {
            'delta': delta,
            'gamma': gamma,
            'theta': theta,
            'theta_daily': theta_daily,
            'vega': vega,
            'rho': rho
        }
    
    @classmethod
    def calculate_implied_volatility(
        cls,
        S: float,
        K: float,
        T: float,
        r: float,
        market_price: float,
        option_type: str = 'call',
        initial_guess: float = 0.2,
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson method
        
        Args:
            S: Current stock price
            K: Option strike price
            T: Time to expiration in years
            r: Risk-free interest rate
            market_price: Market price of the option
            option_type: 'call' or 'put'
            initial_guess: Initial volatility guess
            max_iterations: Maximum iterations
            tolerance: Convergence tolerance
            
        Returns:
            Implied volatility
        """
        sigma = initial_guess
        
        for i in range(max_iterations):
            if option_type.lower() == 'call':
                model_price = cls.european_call_price(S, K, T, r, sigma)
            else:
                model_price = cls.european_put_price(S, K, T, r, sigma)
            
            error = model_price - market_price
            
            if abs(error) < tolerance:
                return sigma
            
            # Calculate vega for Newton-Raphson
            d1 = cls.calculate_d1(S, K, T, r, sigma)
            sqrt_T = np.sqrt(T)
            vega = S * sqrt_T * cls.norm_pdf(d1)
            
            if vega == 0:
                break
            
            # Newton-Raphson update
            sigma = sigma - error / vega
            
            # Ensure volatility stays positive
            sigma = max(0.001, sigma)
        
        return sigma
    
    @classmethod
    def calculate_option_chain(
        cls,
        S: float,
        T: float,
        r: float,
        sigma: float,
        strikes: list,
        option_type: str = 'call'
    ) -> pd.DataFrame:
        """
        Calculate option prices for a chain of strikes
        
        Args:
            S: Current stock price
            T: Time to expiration in years
            r: Risk-free interest rate
            sigma: Volatility
            strikes: List of strike prices
            option_type: 'call' or 'put'
            
        Returns:
            DataFrame with option prices and Greeks
        """
        results = []
        
        for K in strikes:
            if option_type.lower() == 'call':
                price = cls.european_call_price(S, K, T, r, sigma)
            else:
                price = cls.european_put_price(S, K, T, r, sigma)
            
            greeks = cls.calculate_greeks(S, K, T, r, sigma, option_type)
            
            # Calculate moneyness
            moneyness = K / S
            moneyness_label = "ATM" if abs(moneyness - 1) < 0.05 else \
                           "ITM" if (option_type.lower() == 'call' and moneyness < 1) or \
                                     (option_type.lower() == 'put' and moneyness > 1) else "OTM"
            
            results.append({
                'strike': K,
                'price': price,
                'moneyness': moneyness,
                'moneyness_label': moneyness_label,
                'intrinsic_value': max(0, abs(S - K)) if option_type.lower() == 'call' else max(0, abs(K - S)),
                **greeks
            })
        
        return pd.DataFrame(results)
    
    @classmethod
    def calculate_time_to_expiration(
        cls,
        expiry_date: str,
        current_date: datetime = None
    ) -> float:
        """
        Calculate time to expiration in years
        
        Args:
            expiry_date: Expiration date (YYYY-MM-DD format)
            current_date: Current date (defaults to today)
            
        Returns:
            Time to expiration in years
        """
        if current_date is None:
            current_date = datetime.now()
        
        try:
            expiry = datetime.strptime(expiry_date, '%Y-%m-%d')
        except ValueError:
            # Try different date formats
            for fmt in ['%d-%m-%Y', '%Y/%m/%d', '%d/%m/%Y']:
                try:
                    expiry = datetime.strptime(expiry_date, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Could not parse date: {expiry_date}")
        
        # Calculate trading days (assuming 252 trading days per year)
        delta = expiry - current_date
        total_days = abs(delta.days)
        
        # Convert to years (considering only trading days)
        trading_years = total_days / 252.0
        
        return max(0, trading_years)


class OptionsPricingService:
    """Service for options pricing with Black-Scholes model"""
    
    def __init__(self):
        self.bs_model = BlackScholesModel()
    
    def analyze_options_for_trading(
        self,
        ticker: str,
        current_price: float,
        expiry_date: str,
        risk_free_rate: float = 0.06,  # 6% default
        volatility: float = None,
        num_strikes: int = 10
    ) -> Dict[str, Any]:
        """
        Comprehensive options analysis for trading decisions
        
        Args:
            ticker: Stock ticker
            current_price: Current stock price
            expiry_date: Options expiration date
            risk_free_rate: Risk-free interest rate
            volatility: Historical volatility (calculated if None)
            num_strikes: Number of strikes to analyze
            
        Returns:
            Dictionary with comprehensive options analysis
        """
        # Calculate time to expiration
        T = self.bs_model.calculate_time_to_expiration(expiry_date)
        
        if T <= 0:
            return {
                'status': 'error',
                'message': 'Options have expired',
                'data': None
            }
        
        # Use implied volatility if not provided
        if volatility is None:
            volatility = 0.25  # Default 25% annual volatility
        
        # Generate strike range around ATM
        strike_range_pct = 0.1  # 10% above and below current price
        strike_min = current_price * (1 - strike_range_pct)
        strike_max = current_price * (1 + strike_range_pct)
        strikes = np.linspace(strike_min, strike_max, num_strikes)
        
        # Calculate option chain for calls and puts
        call_chain = self.bs_model.calculate_option_chain(
            current_price, T, risk_free_rate, volatility, strikes, 'call'
        )
        
        put_chain = self.bs_model.calculate_option_chain(
            current_price, T, risk_free_rate, volatility, strikes, 'put'
        )
        
        # Find best trading opportunities
        opportunities = self._find_trading_opportunities(
            call_chain, put_chain, current_price, T, risk_free_rate
        )
        
        # Calculate put-call parity check
        pcp_violations = self._check_put_call_parity(call_chain, put_chain, current_price, T, risk_free_rate)
        
        return {
            'status': 'success',
            'ticker': ticker,
            'current_price': current_price,
            'expiry_date': expiry_date,
            'time_to_expiry_years': T,
            'time_to_expiry_days': int(T * 252),
            'volatility': volatility,
            'risk_free_rate': risk_free_rate,
            'call_chain': call_chain.to_dict('records'),
            'put_chain': put_chain.to_dict('records'),
            'trading_opportunities': opportunities,
            'put_call_parity_violations': pcp_violations,
            'analysis_summary': self._generate_analysis_summary(opportunities)
        }
    
    def _find_trading_opportunities(
        self,
        call_chain: pd.DataFrame,
        put_chain: pd.DataFrame,
        current_price: float,
        T: float,
        r: float
    ) -> list:
        """Find best trading opportunities based on various criteria"""
        opportunities = []
        
        # High delta opportunities (near ATM)
        for _, row in call_chain.iterrows():
            if 0.4 <= abs(row['delta']) <= 0.6 and row['price'] > 0.5:
                opportunities.append({
                    'type': 'call',
                    'strike': row['strike'],
                    'price': row['price'],
                    'delta': row['delta'],
                    'theta_daily': row['theta_daily'],
                    'reason': 'High delta near ATM',
                    'score': abs(row['delta']) * (1 / max(row['price'], 0.1))
                })
        
        for _, row in put_chain.iterrows():
            if -0.6 <= row['delta'] <= -0.4 and row['price'] > 0.5:
                opportunities.append({
                    'type': 'put',
                    'strike': row['strike'],
                    'price': row['price'],
                    'delta': row['delta'],
                    'theta_daily': row['theta_daily'],
                    'reason': 'High delta near ATM',
                    'score': abs(row['delta']) * (1 / max(row['price'], 0.1))
                })
        
        # Sort by score (higher is better)
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        return opportunities[:5]  # Return top 5 opportunities
    
    def _check_put_call_parity(
        self,
        call_chain: pd.DataFrame,
        put_chain: pd.DataFrame,
        S: float,
        T: float,
        r: float
    ) -> list:
        """Check for put-call parity violations"""
        violations = []
        
        for i in range(len(call_chain)):
            call_strike = call_chain.iloc[i]['strike']
            put_strike = put_chain.iloc[i]['strike']
            
            if abs(call_strike - put_strike) < 0.01:  # Same strike
                call_price = call_chain.iloc[i]['price']
                put_price = put_chain.iloc[i]['price']
                
                # Put-call parity: C - P = S - K * exp(-r*T)
                pcp_diff = abs((call_price - put_price) - (S - call_strike * np.exp(-r * T)))
                
                if pcp_diff > 0.01:  # Significant violation
                    violations.append({
                        'strike': call_strike,
                        'call_price': call_price,
                        'put_price': put_price,
                        'theoretical_diff': (S - call_strike * np.exp(-r * T)),
                        'actual_diff': (call_price - put_price),
                        'violation': pcp_diff
                    })
        
        return violations
    
    def _generate_analysis_summary(self, opportunities: list) -> dict:
        """Generate summary of trading opportunities"""
        if not opportunities:
            return {'message': 'No clear trading opportunities identified'}
        
        best_call = [opp for opp in opportunities if opp['type'] == 'call']
        best_put = [opp for opp in opportunities if opp['type'] == 'put']
        
        summary = {
            'total_opportunities': len(opportunities),
            'calls_analyzed': len(best_call),
            'puts_analyzed': len(best_put),
        }
        
        if best_call:
            best_call = max(best_call, key=lambda x: x['score'])
            summary['best_call'] = {
                'strike': best_call['strike'],
                'price': best_call['price'],
                'delta': best_call['delta'],
                'reason': best_call['reason']
            }
        
        if best_put:
            best_put = max(best_put, key=lambda x: x['score'])
            summary['best_put'] = {
                'strike': best_put['strike'],
                'price': best_put['price'],
                'delta': best_put['delta'],
                'reason': best_put['reason']
            }
        
        return summary


# Global service instance
options_pricing_service = OptionsPricingService()