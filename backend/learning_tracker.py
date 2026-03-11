"""
Continuous Learning Tracker
Tracks model performance over time and ensures progressive improvement
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

class LearningTracker:
    def __init__(self, model_name="nifty_options_model"):
        self.model_name = model_name
        self.tracking_file = f"backend/models/{model_name}_tracking.json"
        self.performance_history = self._load_tracking_data()
        
    def _load_tracking_data(self):
        """Load tracking data from file"""
        try:
            with open(self.tracking_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                'daily_performance': [],
                'weekly_summary': [],
                'parameter_evolution': [],
                'learning_curves': [],
                'start_date': datetime.now().isoformat()
            }
    
    def track_trade(self, trade_data):
        """
        Track a single trade
        
        trade_data format:
        {
            'timestamp': datetime,
            'strategy': str,
            'entry_price': float,
            'exit_price': float,
            'pnl': float,
            'confidence': float,
            'parameters': dict,
            'features': list (optional)
        }
        """
        trade_record = {
            **trade_data,
            'tracking_id': f"TR{datetime.now().strftime('%Y%m%d%H%M%S')}"
        }
        
        # Add to daily performance
        today = datetime.now().strftime('%Y-%m-%d')
        daily_entry = next((d for d in self.performance_history['daily_performance'] 
                          if d['date'] == today), None)
        
        if not daily_entry:
            daily_entry = {
                'date': today,
                'trades': [],
                'total_pnl': 0,
                'win_rate': 0,
                'total_trades': 0
            }
            self.performance_history['daily_performance'].append(daily_entry)
        
        daily_entry['trades'].append(trade_record)
        daily_entry['total_trades'] += 1
        daily_entry['total_pnl'] += trade_data['pnl']
        
        # Update win rate
        winning_trades = [t for t in daily_entry['trades'] if t['pnl'] > 0]
        daily_entry['win_rate'] = len(winning_trades) / len(daily_entry['trades']) * 100
        
        # Track parameter evolution
        self._track_parameter_evolution(trade_data)
        
        # Save tracking data
        self._save_tracking_data()
        
        return trade_record
    
    def track_learning_session(self, learning_result):
        """
        Track a learning session
        
        learning_result format:
        {
            'timestamp': datetime,
            'training_samples': int,
            'model_accuracy': float,
            'optimized_params': dict,
            'test_results': dict,
            'learning_duration': float (seconds)
        }
        """
        learning_record = {
            **learning_result,
            'session_id': f"LS{datetime.now().strftime('%Y%m%d%H%M%S')}"
        }
        
        self.performance_history['learning_curves'].append(learning_record)
        
        # Update weekly summary
        self._update_weekly_summary()
        
        # Check for improvement
        improvement = self._check_improvement()
        
        self._save_tracking_data()
        
        return {
            'tracked': True,
            'improvement': improvement,
            'total_learning_sessions': len(self.performance_history['learning_curves'])
        }
    
    def _track_parameter_evolution(self, trade_data):
        """Track how parameters evolve over time"""
        if 'parameters' not in trade_data:
            return
        
        param_record = {
            'timestamp': datetime.now().isoformat(),
            'strategy': trade_data['strategy'],
            'parameters': trade_data['parameters'],
            'trade_result': trade_data['pnl'] > 0
        }
        
        self.performance_history['parameter_evolution'].append(param_record)
    
    def _update_weekly_summary(self):
        """Update weekly performance summary"""
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
        
        # Get this week's trades
        weekly_trades = []
        for daily in self.performance_history['daily_performance'][-7:]:
            weekly_trades.extend(daily['trades'])
        
        if not weekly_trades:
            return
        
        # Calculate weekly metrics
        weekly_pnl = sum(t['pnl'] for t in weekly_trades)
        winning_trades = [t for t in weekly_trades if t['pnl'] > 0]
        win_rate = len(winning_trades) / len(weekly_trades) * 100 if weekly_trades else 0
        
        weekly_summary = {
            'week_start': week_start,
            'total_trades': len(weekly_trades),
            'total_pnl': weekly_pnl,
            'win_rate': win_rate,
            'avg_confidence': np.mean([t.get('confidence', 0.5) for t in weekly_trades])
        }
        
        # Update or add weekly summary
        existing = next((w for w in self.performance_history['weekly_summary'] 
                       if w['week_start'] == week_start), None)
        
        if existing:
            existing.update(weekly_summary)
        else:
            self.performance_history['weekly_summary'].append(weekly_summary)
    
    def _check_improvement(self):
        """Check if model is improving over time"""
        if len(self.performance_history['weekly_summary']) < 2:
            return {'improving': False, 'reason': 'Insufficient data'}
        
        # Get last 4 weeks
        recent_weeks = self.performance_history['weekly_summary'][-4:]
        
        if len(recent_weeks) < 2:
            return {'improving': False, 'reason': 'Not enough weeks'}
        
        # Calculate improvement metrics
        win_rates = [w['win_rate'] for w in recent_weeks]
        pnls = [w['total_pnl'] for w in recent_weeks]
        
        # Check if win rate is improving
        win_rate_trend = np.polyfit(range(len(win_rates)), win_rates, 1)[0]
        
        # Check if P&L is improving
        pnl_trend = np.polyfit(range(len(pnls)), pnls, 1)[0]
        
        improving = win_rate_trend > 0 and pnl_trend > 0
        
        return {
            'improving': improving,
            'win_rate_trend': win_rate_trend,
            'pnl_trend': pnl_trend,
            'current_win_rate': win_rates[-1] if win_rates else 0,
            'current_pnl': pnls[-1] if pnls else 0
        }
    
    def get_performance_report(self, days=30):
        """Generate performance report"""
        # Filter data for specified days
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        recent_daily = [d for d in self.performance_history['daily_performance'] 
                       if d['date'] >= cutoff_date]
        
        # Calculate metrics
        all_trades = []
        for daily in recent_daily:
            all_trades.extend(daily['trades'])
        
        if not all_trades:
            return {'error': 'No trades in specified period'}
        
        df_trades = pd.DataFrame(all_trades)
        
        # Basic metrics
        total_trades = len(df_trades)
        winning_trades = df_trades[df_trades['pnl'] > 0]
        losing_trades = df_trades[df_trades['pnl'] <= 0]
        
        win_rate = len(winning_trades) / total_trades * 100
        total_pnl = df_trades['pnl'].sum()
        avg_pnl = df_trades['pnl'].mean()
        
        # Profit factor
        profit_factor = 0
        if len(losing_trades) > 0 and losing_trades['pnl'].sum() != 0:
            profit_factor = abs(winning_trades['pnl'].sum() / losing_trades['pnl'].sum())
        
        # Strategy performance
        strategy_performance = {}
        if 'strategy' in df_trades.columns:
            for strategy in df_trades['strategy'].unique():
                strat_trades = df_trades[df_trades['strategy'] == strategy]
                strat_wins = strat_trades[strat_trades['pnl'] > 0]
                
                strategy_performance[strategy] = {
                    'trades': len(strat_trades),
                    'win_rate': len(strat_wins) / len(strat_trades) * 100 if len(strat_trades) > 0 else 0,
                    'total_pnl': strat_trades['pnl'].sum(),
                    'avg_pnl': strat_trades['pnl'].mean()
                }
        
        # Confidence vs Performance
        # Fix: handle confidence column missing
        if 'confidence' not in df_trades.columns:
             df_trades['confidence'] = 0.5
        
        df_trades['confidence_bin'] = pd.cut(df_trades['confidence'], bins=[0, 0.3, 0.5, 0.7, 0.9, 1.0])
        # Fix: GroupBy apply needs check if empty
        try:
            confidence_performance = df_trades.groupby('confidence_bin').apply(
                lambda x: pd.Series({
                    'win_rate': (x['pnl'] > 0).mean() * 100,
                    'avg_pnl': x['pnl'].mean(),
                    'trades': len(x)
                })
            ).reset_index().to_dict('records')
        except Exception:
             confidence_performance = []
        
        # Learning progress
        learning_sessions = self.performance_history['learning_curves'][-10:]  # Last 10 sessions
        
        return {
            'period': f'Last {days} days',
            'summary': {
                'total_trades': total_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'avg_pnl': avg_pnl,
                'profit_factor': profit_factor,
                'best_strategy': max(strategy_performance.items(), 
                                   key=lambda x: x[1]['win_rate'])[0] if strategy_performance else None,
                'worst_strategy': min(strategy_performance.items(), 
                                    key=lambda x: x[1]['win_rate'])[0] if strategy_performance else None
            },
            'strategy_performance': strategy_performance,
            'confidence_performance': confidence_performance,
            'learning_progress': {
                'total_sessions': len(self.performance_history['learning_curves']),
                'recent_sessions': len(learning_sessions),
                'avg_accuracy': np.mean([s.get('model_accuracy', 0) for s in learning_sessions]) 
                               if learning_sessions else 0
            },
            'improvement_status': self._check_improvement()
        }
    
    def create_performance_dashboard(self):
        """Create interactive performance dashboard"""
        # Create figure with multiple subplots
        fig = make_subplots(
            rows=3, cols=3,
            subplot_titles=(
                'Daily P&L', 'Win Rate Trend', 'Trade Confidence Distribution',
                'Strategy Performance', 'Learning Progress', 'Parameter Evolution',
                'P&L Distribution', 'Trade Duration vs P&L', 'Weekly Summary'
            ),
            specs=[
                [{"type": "bar"}, {"type": "scatter"}, {"type": "histogram"}],
                [{"type": "bar"}, {"type": "scatter"}, {"type": "scatter"}],
                [{"type": "histogram"}, {"type": "scatter"}, {"type": "table"}]
            ]
        )
        
        # 1. Daily P&L
        if self.performance_history['daily_performance']:
            dates = [d['date'] for d in self.performance_history['daily_performance'][-30:]]
            pnls = [d['total_pnl'] for d in self.performance_history['daily_performance'][-30:]]
            
            colors = ['green' if p >= 0 else 'red' for p in pnls]
            
            fig.add_trace(
                go.Bar(x=dates, y=pnls, name='Daily P&L', marker_color=colors),
                row=1, col=1
            )
        
        # 2. Win Rate Trend
        if self.performance_history['weekly_summary']:
            weeks = [w['week_start'] for w in self.performance_history['weekly_summary'][-12:]]
            win_rates = [w['win_rate'] for w in self.performance_history['weekly_summary'][-12:]]
            
            fig.add_trace(
                go.Scatter(x=weeks, y=win_rates, mode='lines+markers', name='Win Rate'),
                row=1, col=2
            )
        
        # 3. Trade Confidence Distribution
        # Collect all trades
        all_trades = []
        for daily in self.performance_history['daily_performance'][-30:]:
            all_trades.extend(daily['trades'])
        
        if all_trades:
            confidences = [t.get('confidence', 0.5) for t in all_trades]
            fig.add_trace(
                go.Histogram(x=confidences, nbinsx=20, name='Confidence'),
                row=1, col=3
            )
        
        # 4. Strategy Performance
        if all_trades:
            df_trades = pd.DataFrame(all_trades)
            if 'strategy' in df_trades.columns:
                strategy_stats = df_trades.groupby('strategy').apply(
                    lambda x: pd.Series({
                        'win_rate': (x['pnl'] > 0).mean() * 100,
                        'total_pnl': x['pnl'].sum()
                    })
                ).reset_index()
                
                fig.add_trace(
                    go.Bar(x=strategy_stats['strategy'], 
                          y=strategy_stats['win_rate'],
                          name='Win Rate by Strategy'),
                    row=2, col=1
                )
        
        # 5. Learning Progress
        if self.performance_history['learning_curves']:
            sessions = range(len(self.performance_history['learning_curves'][-20:]))
            accuracies = [s.get('model_accuracy', 0) 
                         for s in self.performance_history['learning_curves'][-20:]]
            
            fig.add_trace(
                go.Scatter(x=sessions, y=accuracies, mode='lines+markers', 
                          name='Model Accuracy'),
                row=2, col=2
            )
        
        # Update layout
        fig.update_layout(
            height=1200,
            showlegend=True,
            title_text=f"Learning Tracker - {self.model_name}",
            template="plotly_dark"
        )
        
        return fig
    
    def suggest_improvements(self):
        """Suggest improvements based on performance data"""
        report = self.get_performance_report(days=30)
        
        if 'error' in report:
            return {'suggestions': ['Need more trading data']}
        
        suggestions = []
        
        # Check win rate
        win_rate = report['summary']['win_rate']
        if win_rate < 40:
            suggestions.append(f"Win rate ({win_rate:.1f}%) is low. Consider:")
            suggestions.append("  • Increasing stop loss distance (reduce false stops)")
            suggestions.append("  • Waiting for higher confidence signals (>70%)")
            suggestions.append("  • Focusing on best performing strategy")
        
        # Check profit factor
        profit_factor = report['summary']['profit_factor']
        if profit_factor < 1.2:
            suggestions.append(f"Profit factor ({profit_factor:.2f}) is low. Consider:")
            suggestions.append("  • Improving risk/reward ratio (aim for 2:1 minimum)")
            suggestions.append("  • Letting winners run longer")
            suggestions.append("  • Cutting losers faster")
        
        # Check strategy performance
        if report['strategy_performance']:
            best_strat = max(report['strategy_performance'].items(), 
                           key=lambda x: x[1]['win_rate'])
            worst_strat = min(report['strategy_performance'].items(), 
                            key=lambda x: x[1]['win_rate'])
            
            if best_strat[1]['win_rate'] - worst_strat[1]['win_rate'] > 20:
                suggestions.append(f"Strategy disparity detected:")
                suggestions.append(f"  • Best: {best_strat[0]} ({best_strat[1]['win_rate']:.1f}%)")
                suggestions.append(f"  • Worst: {worst_strat[0]} ({worst_strat[1]['win_rate']:.1f}%)")
                suggestions.append(f"  • Consider using {best_strat[0]} more often")
        
        # Check confidence performance
        if report['confidence_performance']:
            # Make sure keys exist
            high_conf = [c for c in report['confidence_performance'] 
                        if 'confidence_bin' in c and hasattr(c['confidence_bin'], 'right') and c['confidence_bin'].right >= 0.7]
            low_conf = [c for c in report['confidence_performance'] 
                       if 'confidence_bin' in c and hasattr(c['confidence_bin'], 'right') and c['confidence_bin'].right <= 0.5]
            
            if high_conf and low_conf:
                high_win_rate = np.mean([c['win_rate'] for c in high_conf])
                low_win_rate = np.mean([c['win_rate'] for c in low_conf])
                
                if high_win_rate > low_win_rate + 10:
                    suggestions.append("High confidence signals performing better.")
                    suggestions.append("  • Wait for signals with >70% confidence")
                else:
                    suggestions.append("Confidence not correlating with performance.")
                    suggestions.append("  • Review confidence calculation")
        
        if not suggestions:
            suggestions.append("Performance is good! Keep following current strategy.")
            suggestions.append("Consider:")
            suggestions.append("  • Gradually increasing position size")
            suggestions.append("  • Adding more strategies for diversification")
        
        return {
            'current_performance': report['summary'],
            'suggestions': suggestions,
            'improvement_status': report['improvement_status']
        }
    
    def _save_tracking_data(self):
        """Save tracking data to file"""
        try:
            with open(self.tracking_file, 'w') as f:
                # Fix: Handle non-serializable types using str default
                json.dump(self.performance_history, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving tracking data: {e}")

# Continuous learning manager
class ContinuousLearningManager:
    """Manages continuous learning process"""
    
    def __init__(self):
        self.learner = None
        self.tracker = None
        self.learning_schedule = {
            'daily_retrain': True,
            'weekly_optimization': True,
            'monthly_review': True,
            'retrain_after_trades': 50
        }
        
    def initialize(self, ticker="^NSEI"):
        """Initialize learning system"""
        from backend.self_learning_backtest import SelfLearningBacktester
        
        self.learner = SelfLearningBacktester(ticker=ticker)
        self.tracker = LearningTracker()
        
        # Try to load existing model
        if self.learner.load_model():
            print("✅ Loaded existing learned model")
        else:
            print("🆕 Starting fresh learning system")
        
        return {
            'learner_initialized': self.learner is not None,
            'tracker_initialized': self.tracker is not None,
            'model_info': self.learner.get_model_info() if self.learner else None
        }
    
    def process_trade(self, trade_data):
        """Process a new trade for learning"""
        if not self.learner or not self.tracker:
            return {'error': 'Learning system not initialized'}
        
        # Track the trade
        tracked_trade = self.tracker.track_trade(trade_data)
        
        # Update learner with trade
        learner_update = self.learner.update_from_live_trade(trade_data)
        
        # Check if we should retrain
        should_retrain = self._check_retrain_condition()
        
        if should_retrain:
            print("🔄 Scheduled retraining triggered")
            self._run_scheduled_learning()
        
        return {
            'trade_tracked': tracked_trade['tracking_id'],
            'learner_updated': learner_update,
            'should_retrain': should_retrain,
            'total_trades': len(self.learner.trade_history) if self.learner else 0
        }
    
    def _check_retrain_condition(self):
        """Check if we should retrain the model"""
        if not self.learner:
            return False
        
        # Check trade count condition
        if len(self.learner.trade_history) % self.learning_schedule['retrain_after_trades'] == 0:
            return True
        
        # Check performance degradation
        if self.tracker and len(self.tracker.performance_history['daily_performance']) >= 5:
            recent_daily = self.tracker.performance_history['daily_performance'][-5:]
            recent_win_rate = np.mean([d['win_rate'] for d in recent_daily])
            
            if recent_win_rate < 40:  # If win rate drops below 40%
                return True
        
        return False
    
    def _run_scheduled_learning(self):
        """Run scheduled learning session"""
        if not self.learner:
            return
        
        # Get data for learning (last 90 days)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        
        print(f"📚 Running scheduled learning from {start_date} to {end_date}")
        
        learning_start = datetime.now()
        
        # Run learning
        # Use 15m as standard for now
        learning_result = self.learner.learn_from_history(
            start_date, end_date, interval="15m"
        )
        
        learning_duration = (datetime.now() - learning_start).total_seconds()
        
        if learning_result:
            # Track learning session
            tracked_session = {
                'timestamp': datetime.now().isoformat(),
                'training_samples': learning_result['training_samples'],
                'model_accuracy': learning_result.get('model_accuracy'),
                'optimized_params': learning_result.get('optimized_params'),
                'test_results': learning_result.get('test_results'),
                'learning_duration': learning_duration
            }
            
            self.tracker.track_learning_session(tracked_session)
            
            print(f"✅ Scheduled learning complete in {learning_duration:.1f}s")
            
            # Get improvement suggestions
            suggestions = self.tracker.suggest_improvements()
            
            return {
                'learning_complete': True,
                'duration': learning_duration,
                'improvements': suggestions
            }
        
        return {'learning_complete': False}
    
    def get_optimized_signals(self, current_data):
        """Get optimized signals using learned model"""
        if not self.learner:
            return []
        
        return self.learner.get_optimized_signals(current_data)
    
    def get_performance_report(self):
        """Get performance report"""
        if not self.tracker:
            return {'error': 'Tracker not initialized'}
        
        return self.tracker.get_performance_report(days=30)
    
    def get_improvement_suggestions(self):
        """Get improvement suggestions"""
        if not self.tracker:
            return {'error': 'Tracker not initialized'}
        
        return self.tracker.suggest_improvements()
    
    def get_dashboard(self):
        """Get learning dashboard"""
        if not self.tracker:
            return None
        
        return self.tracker.create_performance_dashboard()

# Quick continuous learning demo
def demo_continuous_learning():
    """Demonstrate continuous learning system"""
    print("\n" + "="*70)
    print("🔄 CONTINUOUS LEARNING DEMONSTRATION")
    print("="*70)
    
    # Initialize manager
    manager = ContinuousLearningManager()
    init_result = manager.initialize("^NSEI")
    
    print(f"\n📊 INITIAL MODEL INFO:")
    print(f"   Total trades learned: {init_result['model_info']['total_trades_learned']}")
    print(f"   Current win rate: {init_result['model_info']['performance'].get('win_rate', 0):.1%}")
    
    # Simulate some trades
    print("\n📝 SIMULATING RECENT TRADES...")
    import random
    
    for i in range(10):
        trade = {
            'timestamp': (datetime.now() - timedelta(hours=i)).isoformat(),
            'strategy': random.choice(['vwap_pullback', 'breakout', 'sr_bounce']),
            'entry_price': 22000 + random.uniform(-100, 100),
            'exit_price': 22000 + random.uniform(-150, 150),
            'pnl': random.uniform(-500, 1000),
            'confidence': random.uniform(0.4, 0.9),
            'parameters': {'atr_multiplier': 1.5, 'target_multiplier': 2.0}
        }
        
        result = manager.process_trade(trade)
        print(f"   Trade {i+1}: {trade['strategy']}, P&L: {trade['pnl']:+.2f}")
    
    # Get performance report
    print("\n📈 PERFORMANCE REPORT:")
    report = manager.get_performance_report()
    
    if 'error' not in report:
        summary = report['summary']
        print(f"   Total Trades: {summary['total_trades']}")
        print(f"   Win Rate: {summary['win_rate']:.1f}%")
        print(f"   Total P&L: {summary['total_pnl']:.2f}")
        print(f"   Profit Factor: {summary['profit_factor']:.2f}")
    
    # Get improvement suggestions
    print("\n💡 IMPROVEMENT SUGGESTIONS:")
    suggestions = manager.get_improvement_suggestions()
    
    if 'suggestions' in suggestions:
        for suggestion in suggestions['suggestions'][:5]:  # Show first 5
            print(f"   • {suggestion}")
    
    print("\n" + "="*70)
    print("✅ Continuous learning demo complete!")
    print("   The system will now learn and improve with each trade")
    print("="*70)
    
    return manager

if __name__ == "__main__":
    demo_continuous_learning()
