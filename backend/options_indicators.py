"""
Options Greeks Calculator for Indian Markets
Delta, Gamma, Theta, Vega for Nifty/BankNifty options
"""

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

from datetime import datetime
import pytz

class OptionsGreeksAnalyzer:
    def __init__(self):
        self.risk_free_rate = 0.05  # 5% for India
        
    def calculate_black_scholes_greeks(self, spot_price, strike_price, time_to_expiry_days,
                                      implied_volatility, option_type="CE"):
        """
        Calculate Black-Scholes Greeks for Indian options
        
        Parameters:
        - spot_price: Current underlying price
        - strike_price: Option strike price
        - time_to_expiry_days: Days to expiry
        - implied_volatility: Annualized IV (0.20 for 20%)
        - option_type: "CE" for Call, "PE" for Put
        
        Returns: Dictionary with Greeks and derived signals
        """
        # Convert days to years
        T = time_to_expiry_days / 365.0
        
        if T <= 0:
            T = 1/365  # Minimum 1 day to avoid division by zero
        
        # Calculate d1 and d2
        d1 = (np.log(spot_price / strike_price) + 
              (self.risk_free_rate + 0.5 * implied_volatility ** 2) * T) / \
             (implied_volatility * np.sqrt(T))
        d2 = d1 - implied_volatility * np.sqrt(T)
        
        # Calculate Greeks
        if option_type.upper() == "CE":
            delta = norm.cdf(d1)
            gamma = norm.pdf(d1) / (spot_price * implied_volatility * np.sqrt(T))
            theta = (-(spot_price * norm.pdf(d1) * implied_volatility) / (2 * np.sqrt(T)) -
                    self.risk_free_rate * strike_price * np.exp(-self.risk_free_rate * T) * norm.cdf(d2))
            vega = spot_price * norm.pdf(d1) * np.sqrt(T)
        else:  # Put option
            delta = norm.cdf(d1) - 1
            gamma = norm.pdf(d1) / (spot_price * implied_volatility * np.sqrt(T))
            theta = (-(spot_price * norm.pdf(d1) * implied_volatility) / (2 * np.sqrt(T)) +
                    self.risk_free_rate * strike_price * np.exp(-self.risk_free_rate * T) * norm.cdf(-d2))
            vega = spot_price * norm.pdf(d1) * np.sqrt(T)
        
        # Calculate probability metrics
        probability_itm = norm.cdf(d2) if option_type == "CE" else norm.cdf(-d2)
        probability_otm = 1 - probability_itm
        
        # Calculate Break-Even
        if option_type == "CE":
            break_even = strike_price + self._calculate_option_price(
                spot_price, strike_price, T, implied_volatility, option_type)
        else:
            break_even = strike_price - self._calculate_option_price(
                spot_price, strike_price, T, implied_volatility, option_type)
        
        # Generate trading signals based on Greeks
        signals = self._generate_greeks_signals(delta, gamma, theta, vega, T, option_type)
        
        return {
            "greeks": {
                "delta": round(float(delta), 4),
                "gamma": round(float(gamma), 6),
                "theta": round(float(theta), 4),
                "vega": round(float(vega), 4)
            },
            "probabilities": {
                "itm": round(float(probability_itm), 4),
                "otm": round(float(probability_otm), 4),
                "break_even": round(float(break_even), 2)
            },
            "signals": signals,
            "time_sensitivity": self._calculate_time_sensitivity(theta, T, option_type),
            "volatility_sensitivity": self._calculate_vol_sensitivity(vega, implied_volatility)
        }
    
    def _calculate_option_price(self, S, K, T, sigma, option_type):
        """Calculate theoretical option price"""
        d1 = (np.log(S / K) + (self.risk_free_rate + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == "CE":
            price = S * norm.cdf(d1) - K * np.exp(-self.risk_free_rate * T) * norm.cdf(d2)
        else:
            price = K * np.exp(-self.risk_free_rate * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
        return price
    
    def _generate_greeks_signals(self, delta, gamma, theta, vega, T, option_type):
        """Generate trading signals based on Greeks values"""
        signals = []
        
        # Delta signals
        if option_type == "CE":
            if delta > 0.7:
                signals.append(("WARNING", "DELTA_HIGH", "Option is deep ITM - consider rolling or exiting"))
            elif delta < 0.3:
                signals.append(("WARNING", "DELTA_LOW", "Option is deep OTM - low probability"))
            elif 0.45 < delta < 0.55:
                signals.append(("POSITIVE", "DELTA_ATM", "ATM option - good balance of risk/reward"))
        else:  # PE
            if delta < -0.7:
                signals.append(("WARNING", "DELTA_HIGH", "Option is deep ITM - consider rolling or exiting"))
            elif delta > -0.3:
                signals.append(("WARNING", "DELTA_LOW", "Option is deep OTM - low probability"))
            elif -0.55 < delta < -0.45:
                signals.append(("POSITIVE", "DELTA_ATM", "ATM option - good balance of risk/reward"))
        
        # Theta signals (time decay)
        theta_daily = theta / 365
        if theta_daily < -0.001 and T < 7/365:  # High time decay, less than 7 days
            signals.append(("WARNING", "HIGH_THETA", f"High time decay: {theta_daily:.4f} per day"))
        
        # Gamma signals
        if gamma > 0.1 and T < 3/365:  # High gamma risk, less than 3 days
            signals.append(("WARNING", "HIGH_GAMMA", "High gamma risk - delta changes rapidly"))
        
        # Vega signals (volatility sensitivity)
        if vega > 0.3:
            signals.append(("INFO", "HIGH_VEGA", "Highly sensitive to volatility changes"))
        
        return signals
    
    def _calculate_time_sensitivity(self, theta, T, option_type):
        """Calculate how sensitive option is to time decay"""
        days_to_expiry = T * 365
        
        if days_to_expiry < 1:
            return {
                "status": "EXTREME",
                "message": f"Expiring today - theta: {theta:.4f}",
                "decay_per_hour": abs(theta / 24)
            }
        elif days_to_expiry < 7:
            return {
                "status": "HIGH",
                "message": f"Expiring in {int(days_to_expiry)} days - theta: {theta:.4f}",
                "decay_per_day": abs(theta / 365)
            }
        else:
            return {
                "status": "MODERATE",
                "message": f"Time decay manageable",
                "decay_per_week": abs(theta * 7 / 365)
            }
    
    def _calculate_vol_sensitivity(self, vega, implied_vol):
        """Calculate sensitivity to volatility changes"""
        vol_impact_per_1percent = vega * 0.01  # Price change for 1% IV change
        
        return {
            "vega": float(vega),
            "impact_1percent_iv": float(vol_impact_per_1percent),
            "iv_current": float(implied_vol),
            "sensitivity": "HIGH" if vega > 0.2 else "MODERATE" if vega > 0.1 else "LOW"
        }
    
    def analyze_option_chain(self, spot_price, expiry_date, option_type="CE"):
        """
        Analyze complete option chain for best strikes
        
        Parameters:
        - spot_price: Current underlying price
        - expiry_date: datetime of expiry
        - option_type: "CE" or "PE"
        
        Returns: Analysis of different strikes
        """
        from datetime import datetime
        
        # Calculate days to expiry
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        days_to_expiry = (expiry_date - now).days
        if days_to_expiry < 0:
            days_to_expiry = 0
        
        # Common strikes for Nifty (50 point intervals) and BankNifty (100 point intervals)
        if spot_price > 20000:  # Likely Nifty
            strike_interval = 50
        else:
            strike_interval = 100
        
        # Generate strikes around spot
        atm_strike = round(spot_price / strike_interval) * strike_interval
        
        strikes = []
        for i in range(-5, 6):  # 5 strikes on each side
            strike = atm_strike + (i * strike_interval)
            strikes.append(strike)
        
        # Analyze each strike
        analysis = []
        for strike in strikes:
            # Assuming 20% IV for analysis (you should get real IV)
            greeks_data = self.calculate_black_scholes_greeks(
                spot_price=spot_price,
                strike_price=strike,
                time_to_expiry_days=days_to_expiry,
                implied_volatility=0.20,
                option_type=option_type
            )
            
            analysis.append({
                "strike": strike,
                "distance_from_spot": abs(strike - spot_price),
                "percent_distance": abs(strike - spot_price) / spot_price * 100,
                "moneyness": self._get_moneyness(spot_price, strike, option_type),
                "greeks": greeks_data["greeks"],
                "probability_itm": greeks_data["probabilities"]["itm"],
                "signals": greeks_data["signals"]
            })
        
        # Sort by distance from spot
        analysis.sort(key=lambda x: x["distance_from_spot"])
        
        # Find recommended strikes
        recommended = self._find_recommended_strikes(analysis, option_type)
        
        return {
            "spot_price": spot_price,
            "expiry_date": expiry_date.strftime("%Y-%m-%d"),
            "days_to_expiry": days_to_expiry,
            "option_type": option_type,
            "analysis": analysis[:5],  # Top 5 closest strikes
            "recommended_strikes": recommended,
            "summary": self._generate_chain_summary(analysis, option_type)
        }
    
    def _get_moneyness(self, spot, strike, option_type):
        """Determine if option is ITM, ATM, or OTM"""
        if option_type == "CE":
            if strike < spot * 0.98:
                return "DEEP_ITM"
            elif strike < spot * 0.995:
                return "ITM"
            elif abs(strike - spot) / spot < 0.005:
                return "ATM"
            elif strike < spot * 1.02:
                return "OTM"
            else:
                return "DEEP_OTM"
        else:  # PE
            if strike > spot * 1.02:
                return "DEEP_ITM"
            elif strike > spot * 1.005:
                return "ITM"
            elif abs(strike - spot) / spot < 0.005:
                return "ATM"
            elif strike > spot * 0.98:
                return "OTM"
            else:
                return "DEEP_OTM"
    
    def _find_recommended_strikes(self, analysis, option_type):
        """Find best strikes based on multiple factors"""
        recommended = {
            "for_directional_trade": None,
            "for_premium_selling": None,
            "for_high_probability": None,
            "for_high_leverage": None
        }
        
        for strike_data in analysis:
            strike = strike_data["strike"]
            delta = abs(strike_data["greeks"]["delta"])
            prob_itm = strike_data["probability_itm"]
            moneyness = strike_data["moneyness"]
            
            # For directional trade (balance of delta and cost)
            if 0.4 < delta < 0.6 and moneyness in ["ATM", "OTM"]:
                recommended["for_directional_trade"] = {
                    "strike": strike,
                    "delta": delta,
                    "reason": "Good balance of probability and cost"
                }
            
            # For premium selling (high probability, low delta)
            if prob_itm > 0.7 and delta < 0.3:
                recommended["for_premium_selling"] = {
                    "strike": strike,
                    "probability": prob_itm,
                    "reason": "High probability of profit for selling"
                }
            
            # For high probability trade
            if prob_itm > 0.6 and moneyness in ["ITM", "ATM"]:
                recommended["for_high_probability"] = {
                    "strike": strike,
                    "probability": prob_itm,
                    "reason": f"{prob_itm:.1%} probability ITM"
                }
            
            # For high leverage (low probability, high reward)
            if prob_itm < 0.3 and moneyness == "DEEP_OTM":
                recommended["for_high_leverage"] = {
                    "strike": strike,
                    "probability": prob_itm,
                    "reason": "High leverage, low probability"
                }
        
        return recommended
    
    def _generate_chain_summary(self, analysis, option_type):
        """Generate summary of option chain analysis"""
        if not analysis:
            return {}
        
        avg_delta = np.mean([abs(a["greeks"]["delta"]) for a in analysis])
        avg_prob = np.mean([a["probability_itm"] for a in analysis])
        
        summary = {
            "average_delta": round(float(avg_delta), 3),
            "average_itm_probability": round(float(avg_prob), 3),
            "strike_range": f"{analysis[0]['strike']} to {analysis[-1]['strike']}",
            "recommendation": self._get_overall_recommendation(analysis, option_type)
        }
        
        # Add volatility skew if we have multiple strikes
        if len(analysis) >= 3:
            ivs = [0.20] * len(analysis)  # Assuming constant IV, replace with real data
            if len(set(ivs)) > 1:
                summary["volatility_skew"] = {
                    "exists": True,
                    "direction": "PUT" if ivs[0] > ivs[-1] else "CALL" if ivs[0] < ivs[-1] else "FLAT"
                }
        
        return summary
    
    def _get_overall_recommendation(self, analysis, option_type):
        """Generate overall recommendation based on chain analysis"""
        if not analysis:
            return "No analysis available"
        
        # Look at ATM options
        atm_options = [a for a in analysis if a["moneyness"] == "ATM"]
        if atm_options:
            atm = atm_options[0]
            delta = atm["greeks"]["delta"]
            
            if option_type == "CE":
                if delta > 0.55:
                    return "Bullish momentum - Consider ITM/ATM calls"
                elif delta < 0.45:
                    return "Weak momentum - Consider OTM calls or wait"
                else:
                    return "Neutral - ATM calls suitable"
            else:  # PE
                if delta < -0.55:
                    return "Bearish momentum - Consider ITM/ATM puts"
                elif delta > -0.45:
                    return "Weak momentum - Consider OTM puts or wait"
                else:
                    return "Neutral - ATM puts suitable"
        
        return "Analyze specific strikes for recommendations"

# Helper function for quick analysis
def quick_options_analysis(spot_price, strike, days_to_expiry, iv=0.20, option_type="CE"):
    """Quick analysis for a single option"""
    analyzer = OptionsGreeksAnalyzer()
    return analyzer.calculate_black_scholes_greeks(
        spot_price=spot_price,
        strike_price=strike,
        time_to_expiry_days=days_to_expiry,
        implied_volatility=iv,
        option_type=option_type
    )

if __name__ == "__main__":
    # Test the analyzer
    analyzer = OptionsGreeksAnalyzer()
    
    # Test for Nifty
    result = analyzer.calculate_black_scholes_greeks(
        spot_price=22000,
        strike_price=22000,
        time_to_expiry_days=7,
        implied_volatility=0.15,
        option_type="CE"
    )
    
    print("Nifty ATM Call Analysis:")
    print(f"Delta: {result['greeks']['delta']}")
    print(f"Gamma: {result['greeks']['gamma']}")
    print(f"Theta: {result['greeks']['theta']}")
    print(f"Probability ITM: {result['probabilities']['itm']:.2%}")
    print(f"Signals: {result['signals']}")
