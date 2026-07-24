"""
Bayesian Inference for Trading Probability Updates
Updates beliefs about strategy effectiveness based on new evidence
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

class BetaFallback:
    @staticmethod
    def ppf(q, a, b):
        return max(0.0, min(1.0, a / (a + b)))

try:
    from scipy.stats import beta, norm
except ImportError:
    norm = StandardNormalFallback
    beta = BetaFallback

import pandas as pd
from datetime import datetime, timedelta

class BayesianTradingModel:
    def __init__(self, prior_alpha=1, prior_beta=1):
        """
        Initialize Bayesian model with prior beliefs
        
        alpha: Prior successes (winning trades)
        beta: Prior failures (losing trades)
        
        Default: Uniform prior (alpha=1, beta=1)
        """
        self.alpha = prior_alpha
        self.beta = prior_beta
        self.trade_history = []
        self.last_update = None
        
    def update_with_trade(self, trade_result):
        """
        Update beliefs with a new trade result
        
        trade_result: Dictionary with:
            - 'pnl': Profit/Loss amount
            - 'entry_time': When trade was entered
            - 'exit_time': When trade was exited
            - 'reason': Why trade was exited
        """
        is_win = trade_result['pnl'] > 0
        
        # Update parameters
        if is_win:
            self.alpha += 1
        else:
            self.beta += 1
        
        # Store trade
        trade_record = {
            **trade_result,
            'is_win': is_win,
            'update_time': datetime.now()
        }
        self.trade_history.append(trade_record)
        self.last_update = datetime.now()
        
        return self.get_current_beliefs()
    
    def get_current_beliefs(self):
        """Get current posterior distribution"""
        posterior_mean = self.alpha / (self.alpha + self.beta)
        posterior_std = np.sqrt(
            (self.alpha * self.beta) / 
            ((self.alpha + self.beta) ** 2 * (self.alpha + self.beta + 1))
        )
        
        # Calculate credible interval (95%)
        lower = beta.ppf(0.025, self.alpha, self.beta)
        upper = beta.ppf(0.975, self.alpha, self.beta)
        
        # Calculate probability that win rate > 0.5 (profitable)
        prob_profitable = 1 - beta.cdf(0.5, self.alpha, self.beta)
        
        return {
            "win_rate": {
                "mean": float(posterior_mean),
                "std": float(posterior_std),
                "credible_interval_95": [float(lower), float(upper)],
                "median": float(beta.ppf(0.5, self.alpha, self.beta))
            },
            "probabilities": {
                "profitable": float(prob_profitable),
                "win_rate_gt_60": float(1 - beta.cdf(0.6, self.alpha, self.beta)),
                "win_rate_lt_40": float(beta.cdf(0.4, self.alpha, self.beta))
            },
            "sample_size": self.alpha + self.beta - 2,  # Subtract initial priors
            "confidence": self._calculate_confidence(),
            "recommendation": self._generate_recommendation(
                float(posterior_mean), 
                float(prob_profitable), 
                float(self._calculate_confidence()["score"])
            )
        }
    
    def _calculate_confidence(self):
        """Calculate confidence in current estimates"""
        n = self.alpha + self.beta - 2  # Effective sample size
        
        if n < 10:
            return {"level": "LOW", "score": n / 10}
        elif n < 30:
            return {"level": "MEDIUM", "score": min(n / 30, 0.9)}
        else:
            # As sample size increases, confidence approaches 1
            confidence = 1 - np.exp(-n / 50)
            return {"level": "HIGH", "score": min(confidence, 0.99)}
    
    def _generate_recommendation(self, win_rate, prob_profitable, confidence):
        """Generate trading recommendation based on current beliefs"""
        
        if self.alpha + self.beta - 2 < 5:  # Less than 5 trades
            return {
                "action": "COLLECT_DATA",
                "message": "Need more trades to make reliable recommendations",
                "required_trades": 10 - (self.alpha + self.beta - 2)
            }
        
        if prob_profitable < 0.7:
            return {
                "action": "REDUCE_SIZE",
                "message": f"Only {prob_profitable:.1%} chance strategy is profitable",
                "risk_level": "HIGH"
            }
        elif win_rate < 0.45:
            return {
                "action": "IMPROVE_ENTRY",
                "message": f"Win rate {win_rate:.1%} is low - focus on entry timing",
                "risk_level": "MEDIUM_HIGH"
            }
        elif win_rate > 0.55 and confidence > 0.7:
            return {
                "action": "INCREASE_SIZE",
                "message": f"High win rate ({win_rate:.1%}) with good confidence",
                "risk_level": "LOW_MEDIUM"
            }
        else:
            return {
                "action": "CONTINUE",
                "message": f"Strategy performing adequately (win rate: {win_rate:.1%})",
                "risk_level": "MEDIUM"
            }
    
    def bayesian_optimal_stop(self, daily_pnl, max_daily_trades=10):
        """
        Bayesian optimal stopping rule for intraday trading
        
        Determines when to stop trading for the day based on:
        1. Current P&L
        2. Prior performance
        3. Remaining trading opportunities
        """
        trades_today = len([t for t in self.trade_history 
                           if t['update_time'].date() == datetime.now().date()])
        
        remaining_trades = max_daily_trades - trades_today
        
        if remaining_trades <= 0:
            return {
                "decision": "STOP",
                "reason": "Daily trade limit reached",
                "trades_today": trades_today
            }
        
        beliefs = self.get_current_beliefs()
        expected_win_rate = beliefs["win_rate"]["mean"]
        
        # Expected value of next trade (simplified)
        # Assuming average win = 100, average loss = 50
        expected_value = (expected_win_rate * 100) - ((1 - expected_win_rate) * 50)
        
        if daily_pnl > 0:
            # If already profitable, be more conservative
            if daily_pnl > expected_value * 2:
                return {
                    "decision": "LOCK_PROFITS",
                    "reason": f"Daily P&L ({daily_pnl:.2f}) > 2x expected value",
                    "expected_value": expected_value
                }
        
        # If consecutive losses, consider stopping
        recent_trades = self.trade_history[-3:]  # Last 3 trades
        if len(recent_trades) >= 3:
            recent_losses = sum(1 for t in recent_trades if not t['is_win'])
            if recent_losses >= 2:
                return {
                    "decision": "PAUSE",
                    "reason": f"{recent_losses} losses in last 3 trades",
                    "cool_off_period": "30 minutes"
                }
        
        # Normal continuation
        return {
            "decision": "CONTINUE",
            "reason": f"Expected value positive: {expected_value:.2f}",
            "remaining_trades": remaining_trades
        }
    
    def analyze_strategy_robustness(self, market_regime):
        """
        Analyze if strategy works across different market regimes
        
        market_regime: Current market condition
        ("TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOL", "LOW_VOL")
        """
        # Group trades by reason or characteristics
        if not self.trade_history:
            return {"error": "No trade history"}
        
        df_trades = pd.DataFrame(self.trade_history)
        
        # Analyze performance by exit reason
        performance_by_reason = {}
        if 'reason' in df_trades.columns:
            for reason in df_trades['reason'].unique():
                reason_trades = df_trades[df_trades['reason'] == reason]
                if len(reason_trades) >= 3:  # Minimum for analysis
                    wins = reason_trades['is_win'].sum()
                    total = len(reason_trades)
                    performance_by_reason[reason] = {
                        "win_rate": wins / total,
                        "total_trades": total,
                        "avg_pnl": reason_trades['pnl'].mean()
                    }
        
        # Analyze time-based performance
        df_trades['hour'] = df_trades['entry_time'].dt.hour
        performance_by_hour = {}
        for hour in range(9, 16):  # Market hours
            hour_trades = df_trades[df_trades['hour'] == hour]
            if len(hour_trades) >= 2:
                wins = hour_trades['is_win'].sum()
                performance_by_hour[hour] = {
                    "win_rate": wins / len(hour_trades),
                    "total_trades": len(hour_trades)
                }
        
        # Regime-specific analysis (simplified)
        current_regime_performance = None
        if 'market_regime' in df_trades.columns:
            regime_trades = df_trades[df_trades['market_regime'] == market_regime]
            if len(regime_trades) > 0:
                current_regime_performance = {
                    "win_rate": regime_trades['is_win'].mean(),
                    "avg_pnl": regime_trades['pnl'].mean(),
                    "total_trades": len(regime_trades)
                }
        
        return {
            "overall": self.get_current_beliefs(),
            "by_exit_reason": performance_by_reason,
            "by_hour": performance_by_hour,
            "current_regime": {
                "regime": market_regime,
                "performance": current_regime_performance
            },
            "strategy_assessment": self._assess_strategy_robustness(
                performance_by_reason, performance_by_hour)
        }
    
    def _assess_strategy_robustness(self, by_reason, by_hour):
        """Assess how robust the strategy is"""
        assessments = []
        
        # Check consistency across exit reasons
        if by_reason:
            win_rates = [data['win_rate'] for data in by_reason.values()]
            if len(win_rates) >= 3:
                consistency = 1 - np.std(win_rates)  # Higher = more consistent
                if consistency > 0.8:
                    assessments.append("GOOD_CONSISTENCY across exit reasons")
                elif consistency > 0.6:
                    assessments.append("MODERATE_CONSISTENCY across exit reasons")
                else:
                    assessments.append("POOR_CONSISTENCY - strategy depends heavily on exit type")
        
        # Check time consistency
        if by_hour and len(by_hour) >= 3:
            hour_win_rates = [data['win_rate'] for data in by_hour.values()]
            hour_consistency = 1 - np.std(hour_win_rates)
            if hour_consistency > 0.8:
                assessments.append("CONSISTENT_ACROSS_HOURS")
            elif hour_consistency < 0.5:
                assessments.append("TIME_DEPENDENT - works better at specific hours")
        
        # Overall assessment
        beliefs = self.get_current_beliefs()
        win_rate = beliefs["win_rate"]["mean"]
        confidence = beliefs["confidence"]["score"]
        
        if win_rate > 0.55 and confidence > 0.7:
            robustness = "HIGH"
        elif win_rate > 0.5 and confidence > 0.5:
            robustness = "MEDIUM"
        else:
            robustness = "LOW"
        
        return {
            "robustness_level": robustness,
            "assessments": assessments,
            "recommended_improvements": self._suggest_improvements(by_reason, by_hour)
        }
    
    def _suggest_improvements(self, by_reason, by_hour):
        """Suggest improvements based on analysis"""
        suggestions = []
        
        if by_reason:
            # Find worst performing exit reasons
            for reason, data in by_reason.items():
                if data['win_rate'] < 0.4 and data['total_trades'] >= 3:
                    suggestions.append(f"Improve exits for '{reason}' (win rate: {data['win_rate']:.1%})")
        
        if by_hour:
            # Find worst performing hours
            worst_hour = min(by_hour.items(), key=lambda x: x[1]['win_rate'])
            if worst_hour[1]['win_rate'] < 0.4 and worst_hour[1]['total_trades'] >= 3:
                suggestions.append(f"Avoid trading at {worst_hour[0]}:00 (win rate: {worst_hour[1]['win_rate']:.1%})")
        
        beliefs = self.get_current_beliefs()
        if beliefs["probabilities"]["profitable"] < 0.7:
            suggestions.append("Consider fundamental strategy review - low probability of profitability")
        
        return suggestions
    
    def predict_next_trade_outcome(self, trade_context):
        """
        Predict probability of success for next trade
        
        trade_context: Dictionary with trade characteristics
        {
            'hour': int,
            'market_regime': str,
            'signal_strength': float,
            'previous_trade_result': 'WIN' or 'LOSS' or None
        }
        """
        base_beliefs = self.get_current_beliefs()
        base_prob = base_beliefs["win_rate"]["mean"]
        
        # Adjust based on context (simplified adjustments)
        adjustment = 0.0
        
        # Time of day adjustment
        if 'hour' in trade_context:
            hour = trade_context['hour']
            if 9 <= hour <= 11:
                adjustment += 0.05  # Morning tends to be better for trends
            elif hour >= 14:
                adjustment -= 0.03  # Late afternoon often choppy
        
        # Signal strength adjustment
        if 'signal_strength' in trade_context:
            strength = trade_context['signal_strength']
            if strength > 0.8:
                adjustment += 0.1
            elif strength < 0.4:
                adjustment -= 0.1
        
        # Previous trade result (avoid revenge trading)
        if 'previous_trade_result' in trade_context:
            prev = trade_context['previous_trade_result']
            if prev == 'LOSS':
                adjustment -= 0.05  # Slightly reduce probability after loss
        
        # Market regime adjustment
        if 'market_regime' in trade_context:
            regime = trade_context['market_regime']
            if regime in ['HIGH_VOL', 'BREAKOUT']:
                adjustment += 0.07  # Strategies often work better in trending markets
            elif regime == 'RANGING':
                adjustment -= 0.05
        
        # Calculate final probability
        final_prob = max(0.1, min(0.9, base_prob + adjustment))
        
        # Calculate confidence in prediction
        confidence = base_beliefs["confidence"]["score"] * 0.7  # Reduce for prediction
        
        return {
            "predicted_win_probability": float(final_prob),
            "base_probability": float(base_prob),
            "adjustments": float(adjustment),
            "confidence": float(confidence),
            "recommendation": self._get_prediction_recommendation(final_prob, confidence)
        }
    
    def _get_prediction_recommendation(self, probability, confidence):
        """Get recommendation based on prediction"""
        if confidence < 0.5:
            return "LOW_CONFIDENCE - Use caution"
        elif probability > 0.6:
            return "FAVORABLE - Good chance of success"
        elif probability < 0.4:
            return "UNFAVORABLE - Consider skipping"
        else:
            return "NEUTRAL - Proceed with normal risk management"

class BayesianPortfolioOptimizer:
    """Bayesian optimization for portfolio allocation"""
    
    def __init__(self):
        self.strategies = {}  # strategy_name -> BayesianTradingModel
        
    def add_strategy(self, name, prior_alpha=1, prior_beta=1):
        """Add a trading strategy to optimize"""
        self.strategies[name] = BayesianTradingModel(prior_alpha, prior_beta)
    
    def update_strategy(self, name, trade_result):
        """Update a strategy with new trade result"""
        if name in self.strategies:
            return self.strategies[name].update_with_trade(trade_result)
        return None
    
    def optimal_allocation(self, total_capital, risk_per_trade=0.01):
        """
        Calculate optimal capital allocation across strategies
        
        Uses Kelly Criterion with Bayesian probabilities
        """
        allocations = {}
        
        for name, model in self.strategies.items():
            beliefs = model.get_current_beliefs()
            
            # Get strategy statistics
            win_rate = beliefs["win_rate"]["mean"]
            confidence = beliefs["confidence"]["score"]
            
            # Need more data for reliable allocation
            if confidence < 0.3:
                allocations[name] = {
                    "allocation": 0.0,
                    "reason": "Insufficient data",
                    "confidence": confidence
                }
                continue
            
            # Estimate win/loss sizes from history
            trades = model.trade_history
            if len(trades) >= 5:
                wins = [t['pnl'] for t in trades if t['is_win']]
                losses = [t['pnl'] for t in trades if not t['is_win']]
                
                avg_win = np.mean(wins) if wins else 100
                avg_loss = np.mean(losses) if losses else -50
            else:
                # Default estimates
                avg_win = 100
                avg_loss = -50
            
            # Calculate win/loss ratio
            win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 1
            
            # Bayesian Kelly Criterion
            # f* = p - (1-p)/b, where b = win/loss ratio
            kelly_fraction = win_rate - ((1 - win_rate) / win_loss_ratio)
            
            # Conservative Kelly (half Kelly)
            conservative_kelly = kelly_fraction / 2
            
            # Cap at reasonable allocation
            max_allocation = 0.2  # 20% max per strategy
            allocation = max(0, min(conservative_kelly, max_allocation))
            
            # Adjust for confidence
            allocation *= confidence
            
            allocations[name] = {
                "allocation": float(allocation),
                "capital": float(total_capital * allocation),
                "kelly_fraction": float(kelly_fraction),
                "win_rate": float(win_rate),
                "win_loss_ratio": float(win_loss_ratio),
                "confidence": float(confidence),
                "recommended_position_size": self._calculate_position_size(
                    total_capital * allocation, risk_per_trade, avg_loss)
            }
        
        # Normalize allocations to sum to 1
        total_allocated = sum(a["allocation"] for a in allocations.values())
        if total_allocated > 1:
            for name in allocations:
                allocations[name]["allocation"] /= total_allocated
                allocations[name]["capital"] = total_capital * allocations[name]["allocation"]
        
        return {
            "allocations": allocations,
            "total_capital": total_capital,
            "diversification_score": self._calculate_diversification_score(allocations),
            "risk_adjusted_return": self._estimate_portfolio_return(allocations)
        }
    
    def _calculate_position_size(self, strategy_capital, risk_per_trade, avg_loss):
        """Calculate position size based on risk"""
        risk_amount = strategy_capital * risk_per_trade
        if avg_loss == 0:
            return 0
        
        position_size = risk_amount / abs(avg_loss)
        return int(position_size)  # Round to whole shares/contracts
    
    def _calculate_diversification_score(self, allocations):
        """Calculate how diversified the portfolio is"""
        if not allocations:
            return 0
        
        # Herfindahl-Hirschman Index (HHI) for concentration
        weights = [alloc["allocation"] for alloc in allocations.values()]
        hhi = sum(w ** 2 for w in weights)
        
        # Convert to diversification score (0-100)
        diversification = (1 - hhi) * 100
        
        return {
            "score": float(diversification),
            "interpretation": "HIGH" if diversification > 70 else 
                             "MEDIUM" if diversification > 40 else "LOW",
            "hhi": float(hhi)
        }
    
    def _estimate_portfolio_return(self, allocations):
        """Estimate portfolio return based on strategy performance"""
        total_return = 0
        total_risk = 0
        
        for name, alloc in allocations.items():
            if name in self.strategies:
                model = self.strategies[name]
                beliefs = model.get_current_beliefs()
                
                # Get average P&L per trade
                trades = model.trade_history
                if trades:
                    avg_return = np.mean([t['pnl'] for t in trades])
                    return_std = np.std([t['pnl'] for t in trades]) if len(trades) > 1 else 0
                else:
                    avg_return = 0
                    return_std = 0
                
                # Weight by allocation
                weighted_return = avg_return * alloc["allocation"]
                weighted_risk = return_std * alloc["allocation"]
                
                total_return += weighted_return
                total_risk += weighted_risk
        
        if total_risk > 0:
            sharpe_ratio = total_return / total_risk
        else:
            sharpe_ratio = 0
        
        return {
            "expected_return": float(total_return),
            "expected_risk": float(total_risk),
            "sharpe_ratio": float(sharpe_ratio),
            "return_per_unit_risk": float(total_return / total_risk if total_risk > 0 else 0)
        }

# Quick Bayesian analysis function
def quick_bayesian_update(prior_wins, prior_losses, new_wins, new_losses):
    """Quick Bayesian update calculation"""
    model = BayesianTradingModel(prior_wins + 1, prior_losses + 1)
    
    # Simulate updates
    for _ in range(new_wins):
        model.update_with_trade({'pnl': 100, 'reason': 'test'})
    for _ in range(new_losses):
        model.update_with_trade({'pnl': -50, 'reason': 'test'})
    
    return model.get_current_beliefs()

if __name__ == "__main__":
    # Test Bayesian model
    print("Testing Bayesian Inference Model...")
    
    # Create model
    model = BayesianTradingModel(prior_alpha=2, prior_beta=2)  # Slight prior for profitability
    
    # Simulate some trades
    trades = [
        {'pnl': 120, 'entry_time': datetime.now(), 'exit_time': datetime.now(), 'reason': 'TAKE_PROFIT'},
        {'pnl': -45, 'entry_time': datetime.now(), 'exit_time': datetime.now(), 'reason': 'STOP_LOSS'},
        {'pnl': 80, 'entry_time': datetime.now(), 'exit_time': datetime.now(), 'reason': 'TARGET_HIT'},
        {'pnl': 150, 'entry_time': datetime.now(), 'exit_time': datetime.now(), 'reason': 'TRAILING_STOP'},
        {'pnl': -60, 'entry_time': datetime.now(), 'exit_time': datetime.now(), 'reason': 'STOP_LOSS'}
    ]
    
    for trade in trades:
        beliefs = model.update_with_trade(trade)
    
    print(f"Current win rate: {beliefs['win_rate']['mean']:.1%}")
    print(f"95% Credible Interval: {beliefs['win_rate']['credible_interval_95'][0]:.1%} to {beliefs['win_rate']['credible_interval_95'][1]:.1%}")
    print(f"Probability strategy is profitable: {beliefs['probabilities']['profitable']:.1%}")
    print(f"Recommendation: {beliefs['recommendation']['action']} - {beliefs['recommendation']['message']}")
