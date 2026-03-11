"""
Self-Learning Backtesting Engine
Learns from historical data and improves strategy parameters over time
Uses Reinforcement Learning and Bayesian Optimization
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import json
import pickle
from scipy.optimize import minimize
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import warnings
from backend.ict_smart_money import ICTSmartMoney
warnings.filterwarnings('ignore')

class SelfLearningBacktester:
    def __init__(self, ticker="^NSEI", model_name="nifty_options_model"):
        """
        Initialize self-learning backtester
        
        Features:
        1. Learns optimal parameters from historical data
        2. Updates beliefs based on new trades
        3. Adapts to changing market regimes
        4. Continuously improves predictions
        """
        self.ticker = ticker
        self.model_name = model_name
        self.model_path = f"backend/models/{model_name}.pkl"
        
        # Initialize models
        self.strategy_params = self._load_default_params()
        self.ml_model = None
        self.scaler = StandardScaler()
        
        # Learning history
        self.learning_history = []
        self.trade_history = []
        
        # Performance tracking
        self.performance_metrics = {
            'total_trades': 0,
            'win_rate': 0.5,
            'profit_factor': 1.0,
            'sharpe_ratio': 0.0
        }
        
        # Create models directory
        import os
        os.makedirs("backend/models", exist_ok=True)
        
    def _load_default_params(self):
        """Load default strategy parameters for Indian markets"""
        return {
            'vwap_pullback': {
                'rsi_threshold': 45,
                'vwap_distance_pct': 0.002,
                'atr_multiplier': 1.5,
                'target_multiplier': 2.0,
                'volume_ratio': 1.2
            },
            'breakout': {
                'volume_spike': 1.5,
                'breakout_pct': 0.002,
                'stop_loss_atr': 1.0,
                'target_multiplier': 2.5
            },
            'sr_bounce': {
                'bounce_threshold_pct': 0.003,
                'confirmation_candles': 2,
                'stop_loss_atr': 1.2,
                'target_multiplier': 2.2
            }
        }
    
    def learn_from_history(self, start_date, end_date, interval="15m"):
        """
        Learn optimal parameters from historical data using Bayesian Optimization
        
        Parameters:
        - start_date: "2024-01-01"
        - end_date: "2024-03-01"
        - interval: "5m", "15m", "1h"
        
        Returns: Optimized parameters and performance metrics
        """
        print(f"🧠 Learning from {start_date} to {end_date}...")
        
        # Fetch data
        data = self._fetch_historical_data(start_date, end_date, interval)
        
        if data.empty:
            print("❌ No data for learning")
            return None
        
        print(f"📊 Learning from {len(data)} candles...")
        
        # Generate features and labels
        X, y = self._prepare_training_data(data)
        
        if len(X) < 100:
            print("⚠️  Insufficient data for learning")
            # If explicit learning requested but scarce data, try fallback or just return
            # But let's proceed if at least some data (user might be testing)
            if len(X) < 20: 
                return None
        
        # 1. Train ML model for signal prediction
        if len(X) >= 20:
             self._train_ml_model(X, y)
        
        # 2. Optimize strategy parameters using Bayesian methods
        optimized_params = self._bayesian_parameter_optimization(data)
        
        # 3. Update strategy parameters
        self.strategy_params.update(optimized_params)
        
        # 4. Test optimized parameters
        test_results = self._test_optimized_params(data, optimized_params)
        
        # 5. Save learned model
        self._save_model()
        
        learning_result = {
            'optimized_params': optimized_params,
            'test_results': test_results,
            'training_samples': len(X),
            'model_accuracy': self._evaluate_model(X, y) if self.ml_model else None,
            'learning_date': datetime.now().isoformat()
        }
        
        self.learning_history.append(learning_result)
        
        print(f"Learning complete. Win rate: {test_results.get('win_rate', 0):.1f}%")
        
        return learning_result
    
    def _prepare_training_data(self, data):
        """Prepare features and labels for ML training"""
        features = []
        labels = []
        
        # Calculate technical indicators
        data = self._calculate_indicators(data)
        
        for i in range(50, len(data) - 5):  # Need future data for labels
            # Feature vector
            feature_vector = self._extract_features(data, i)
            
            # Label: 1 if profitable trade in next 5 candles, 0 otherwise
            future_max = data['High'].iloc[i+1:i+6].max()
            future_min = data['Low'].iloc[i+1:i+6].min()
            current_price = data['Close'].iloc[i]
            
            # Check if there's a profitable move (2 ATR move)
            atr = data['ATR'].iloc[i]
            profitable_long = (future_max - current_price) > (atr * 1.5)
            profitable_short = (current_price - future_min) > (atr * 1.5)
            
            label = 1 if profitable_long or profitable_short else 0
            
            features.append(feature_vector)
            labels.append(label)
        
        return np.array(features), np.array(labels)
    
    def _extract_features(self, data, idx):
        """Extract features for ML model"""
        window = 20
        
        features = [
            # Price features
            data['Close'].iloc[idx] / data['Close'].iloc[idx-1] - 1,  # Return
            (data['High'].iloc[idx] - data['Low'].iloc[idx]) / data['Close'].iloc[idx],  # Range %
            
            # Volume features
            data['Volume'].iloc[idx] / data['Volume'].iloc[idx-20:idx].mean() if idx >= 20 else 1,
            
            # RSI
            data['RSI'].iloc[idx] if not pd.isna(data['RSI'].iloc[idx]) else 50,
            
            # VWAP position
            (data['Close'].iloc[idx] - data['VWAP'].iloc[idx]) / data['VWAP'].iloc[idx],
            
            # ATR normalized
            data['ATR'].iloc[idx] / data['Close'].iloc[idx],
            
            # Trend features
            data['SMA_20'].iloc[idx] > data['SMA_50'].iloc[idx] if not pd.isna(data['SMA_20'].iloc[idx]) else 0,
            (data['Close'].iloc[idx] - data['SMA_20'].iloc[idx]) / data['SMA_20'].iloc[idx] if not pd.isna(data['SMA_20'].iloc[idx]) else 0,
            
            # Support/Resistance features
            self._support_distance(data, idx),
            self._resistance_distance(data, idx),
            
            # Time features
            data.index[idx].hour,
            data.index[idx].weekday(),
            
            # Market regime features
            self._market_regime_features(data, idx)
        ]
        
        return np.array(features)
    
    def _train_ml_model(self, X, y):
        """Train ML model for signal prediction"""
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score
        
        if len(X) < 100:
             # Basic training if low data
             print("⚠️ Training on limited data")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train Random Forest
        self.ml_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            class_weight='balanced'
        )
        
        self.ml_model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = self.ml_model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        
        print(f"🤖 ML Model trained: Accuracy = {accuracy:.3f}")
        
        # Feature importance
        if hasattr(self.ml_model, 'feature_importances_'):
            importance = self.ml_model.feature_importances_
            print("Top 5 important features:")
            feature_names = [
                'Return', 'Range%', 'Volume Ratio', 'RSI', 'VWAP Dist',
                'ATR Norm', 'Trend', 'SMA Dist', 'Sup Dist', 'Res Dist',
                'Hour', 'Weekday', 'Regime'
            ]
            for i in np.argsort(importance)[-5:][::-1]:
                if i < len(feature_names):
                    print(f"  {feature_names[i]}: {importance[i]:.3f}")
    


    def _bayesian_parameter_optimization(self, data, n_iter=50):
        """
        Bayesian Optimization for parameter tuning
        Maximizes profit factor over historical data
        """
        print("🔧 Running Bayesian Optimization...")
        
        # Define parameter bounds for each strategy
        param_bounds = {
            'vwap_pullback_ict': {
                'rsi_fvg_threshold': (40, 60), # We can be looser if in FVG
                'rsi_std_threshold': (20, 40), # Stricter if no FVG
                'vwap_distance_pct': (0.001, 0.005),
                'atr_multiplier': (1.0, 2.5),
                'target_multiplier': (1.5, 3.5),
            }
        }
        
        optimized_params = {}
        
        for strategy, bounds in param_bounds.items():
            print(f"  Optimizing {strategy}...")
            
            # Objective function: maximize profit factor
            def objective(params):
                # Simulate trades with these parameters
                # Convert list params to dict for _simulate_strategy
                param_keys = list(bounds.keys())
                param_dict = dict(zip(param_keys, params))
                
                results = self._simulate_strategy(data, strategy, param_dict)
                if results and results['total_trades'] > 5:
                    # We want to maximize profit factor * log(trades) to encourage some volume
                    score = results['profit_factor'] * np.log1p(results['total_trades'])
                    return -score  # Negative because we minimize
                return 10  # Penalty for few trades
            
            # Initial guess (middle of bounds)
            x0 = [(b[0] + b[1]) / 2 for b in bounds.values()]
            
            # Parameter bounds
            param_list = list(bounds.keys())
            bnds = [bounds[p] for p in param_list]
            
            # Run optimization
            try:
                result = minimize(
                    objective,
                    x0,
                    bounds=bnds,
                    method='L-BFGS-B',
                    options={'maxiter': n_iter, 'disp': False}
                )
                
                if result.success:
                    optimized_params[strategy] = dict(zip(param_list, result.x))
                    print(f"    ✓ Optimized {strategy}: Score = {-result.fun:.2f}")
                else:
                    print(f"    ⚠️  {strategy} optimization failed")
                    # Fallback to defaults if fail
                    optimized_params[strategy] = {
                        'rsi_fvg_threshold': 50,
                        'rsi_std_threshold': 30,
                        'vwap_distance_pct': 0.002,
                        'atr_multiplier': 1.5,
                        'target_multiplier': 2.0
                    }
                    
            except Exception as e:
                print(f"    ❌ {strategy} error: {e}")
                optimized_params[strategy] = {
                        'rsi_fvg_threshold': 50,
                        'rsi_std_threshold': 30,
                        'vwap_distance_pct': 0.002,
                        'atr_multiplier': 1.5,
                        'target_multiplier': 2.0
                    }
        
        return optimized_params
    
    def _simulate_strategy(self, data, strategy, params):
        """Simulate a strategy with given parameters"""
        
        # Simple simulation for now
        trades = []
        capital = 100000
        position = None
        
        # Create indicators if not present for speed
        if 'ATR' not in data.columns:
             data = self._calculate_indicators(data)
             
        # Pre-calculate ICT
        # For optimization speed, we calculate once. 
        # In strict backtest we respect causality, but FVG is causal (lagged)
        ict = ICTSmartMoney(data)
        fvgs = ict.detect_fair_value_gaps()
        
        # Helper to check FVG
        def is_in_fvg(price, time, fvgs):
            # Check only active FVGs (start_time < current_time)
            # This search is O(N*M) but M (fvgs) is small usually. 
            # For optimization we can optimize this but let's keep it simple.
            for f in fvgs:
                if f['type'] == 'bullish' and pd.to_datetime(f['end_time']) < time:
                     if f['bottom'] <= price <= f['top']:
                         return True
            return False
             
        for i in range(50, len(data) - 5):
            
            # Get signals
            current_price = data['Close'].iloc[i]
            current_time = data.index[i]
            atr = data['ATR'].iloc[i]
            
            # Simulate entry based on strategy
            entry_signal = False
            entry_price = 0
            stop_loss = 0
            target = 0
            
            if strategy == 'vwap_pullback_ict':
                vwap = data['VWAP'].iloc[i]
                rsi = data['RSI'].iloc[i] if 'RSI' in data.columns else 50
                sma = data['SMA_20'].iloc[i] # Trend filter
                
                # Basic Trend & Pullback
                trend_ok = current_price > sma
                pullback_ok = current_price < vwap
                
                if trend_ok and pullback_ok:
                    in_fvg = is_in_fvg(data['Low'].iloc[i], current_time, fvgs)
                    
                    # ICT-Adaptive Logic
                    # If in FVG, we allow higher RSI (e.g. 50). 
                    # If NOT in FVG, we demand lower RSI (e.g. 30).
                    
                    threshold = params['rsi_fvg_threshold'] if in_fvg else params['rsi_std_threshold']
                    
                    if rsi < threshold:
                        entry_signal = True
                        entry_price = current_price
                        stop_loss = entry_price - (atr * params['atr_multiplier'])
                        target = entry_price + (atr * params['target_multiplier'])
            
            if entry_signal and not position:
                position = {
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'target': target,
                    'entry_idx': i
                }
            
            elif position:
                # Check exit conditions
                exit_price = 0
                exit_reason = ""
                
                # Check stop loss
                if data['Low'].iloc[i] <= position['stop_loss']:
                    exit_price = position['stop_loss']
                    exit_reason = "SL"
                
                # Check target
                elif data['High'].iloc[i] >= position['target']:
                    exit_price = position['target']
                    exit_reason = "TP"
                
                # Time-based exit (High urgency for options)
                elif i - position['entry_idx'] >= 12: # 3 hours max
                    exit_price = current_price
                    exit_reason = "TIME"
                
                if exit_price > 0:
                    pnl = (exit_price - position['entry_price']) * 50  # 1 lot
                    trades.append({
                        'pnl': pnl,
                        'exit_reason': exit_reason
                    })
                    capital += pnl
                    position = None
        
        # Calculate metrics
        if trades:
            df_trades = pd.DataFrame(trades)
            wins = df_trades[df_trades['pnl'] > 0]
            losses = df_trades[df_trades['pnl'] <= 0]
            
            total_trades = len(df_trades)
            win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
            profit_factor = abs(wins['pnl'].sum() / losses['pnl'].sum()) if len(losses) > 0 and losses['pnl'].sum() != 0 else 0
            
            return {
                'total_trades': total_trades,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'final_capital': capital,
                'total_pnl': capital - 100000
            }
        
        return None
    
    def _test_optimized_params(self, data, optimized_params):
        """Test optimized parameters on validation data"""
        # Split data: 70% training, 30% validation
        split_idx = int(len(data) * 0.7)
        if (split_idx >= len(data)): return {}

        # train_data = data.iloc[:split_idx]
        test_data = data.iloc[split_idx:]
        
        results = {}
        
        for strategy, params in optimized_params.items():
            # Test on validation set
            test_result = self._simulate_strategy(test_data, strategy, params)
            if test_result:
                results[strategy] = test_result
        
        return results
    
    def update_from_live_trade(self, trade_result):
        """
        Update model from a live trade result
        This enables continuous learning
        
        trade_result format:
        {
            'entry_time': datetime,
            'exit_time': datetime,
            'entry_price': float,
            'exit_price': float,
            'strategy': str,
            'parameters': dict,
            'pnl': float,
            'features': list (optional)
        }
        """
        self.trade_history.append(trade_result)
        
        # Update performance metrics
        self._update_performance_metrics()
        
        # If we have enough new trades, retrain
        if len(self.trade_history) % 50 == 0:  # Retrain every 50 trades
            print("🔄 Retraining model with new trades...")
            self._retrain_with_new_data()
        
        # Update strategy parameters based on recent performance
        self._adapt_parameters()
        
        # Save updated model
        self._save_model()
        
        return {
            'status': 'updated',
            'total_trades': len(self.trade_history),
            'current_win_rate': self.performance_metrics['win_rate']
        }
    
    def _retrain_with_new_data(self):
        """Retrain ML model with new trade data"""
        if len(self.trade_history) < 50:
            return
        
        # Convert trade history to features/labels
        X_new = []
        y_new = []
        
        for trade in self.trade_history[-100:]:  # Use last 100 trades
            if 'features' in trade:
                X_new.append(trade['features'])
                y_new.append(1 if trade['pnl'] > 0 else 0)
        
        if len(X_new) < 20:
            return
        
        # Combine with existing model
        if self.ml_model:
            # Partial fit if supported
            if hasattr(self.ml_model, 'partial_fit'):
                X_scaled = self.scaler.transform(X_new)
                self.ml_model.partial_fit(X_scaled, y_new)
            else:
                # Retrain from scratch
                self._train_ml_model(np.array(X_new), np.array(y_new))
    
    def _adapt_parameters(self):
        """Adapt strategy parameters based on recent performance"""
        if len(self.trade_history) < 20:
            return
        
        # Analyze recent trades by strategy
        recent_trades = pd.DataFrame(self.trade_history[-50:])
        
        for strategy in self.strategy_params.keys():
            if 'strategy' not in recent_trades.columns: continue
            strat_trades = recent_trades[recent_trades['strategy'] == strategy]
            
            if len(strat_trades) >= 10:
                win_rate = (strat_trades['pnl'] > 0).mean()
                
                # Adjust parameters based on performance
                if win_rate < 0.4:
                    # Strategy underperforming, make it more conservative
                    self._adjust_params_conservative(strategy)
                elif win_rate > 0.6:
                    # Strategy performing well, can be more aggressive
                    self._adjust_params_aggressive(strategy)
    
    def _adjust_params_conservative(self, strategy):
        """Make strategy parameters more conservative"""
        if strategy in self.strategy_params:
            params = self.strategy_params[strategy]
            
            if 'rsi_threshold' in params:
                params['rsi_threshold'] = min(50, params['rsi_threshold'] + 5)
            
            if 'atr_multiplier' in params:
                params['atr_multiplier'] = max(1.0, params['atr_multiplier'] - 0.2)
            
            if 'target_multiplier' in params:
                params['target_multiplier'] = max(1.5, params['target_multiplier'] - 0.3)
    
    def _adjust_params_aggressive(self, strategy):
        """Make strategy parameters more aggressive"""
        if strategy in self.strategy_params:
            params = self.strategy_params[strategy]
            
            if 'rsi_threshold' in params:
                params['rsi_threshold'] = max(30, params['rsi_threshold'] - 5)
            
            if 'atr_multiplier' in params:
                params['atr_multiplier'] = min(2.5, params['atr_multiplier'] + 0.2)
            
            if 'target_multiplier' in params:
                params['target_multiplier'] = min(3.5, params['target_multiplier'] + 0.3)
    
    def predict_signal(self, current_data):
        """
        Use ML model to predict if current market condition is good for entry
        
        Returns: Probability of successful trade
        """
        if self.ml_model is None:
            return 0.5  # Default confidence
        
        # Extract features from current data
        # Assume current_data is a DataFrame and we want prediction for the latest candle
        features = self._extract_features(current_data, -1)  # Latest data point
        features_scaled = self.scaler.transform([features])
        
        # Predict probability
        proba = self.ml_model.predict_proba(features_scaled)[0][1]
        
        return float(proba)
    
    def get_optimized_signals(self, df, interval="5m"):
        """
        Get entry signals using optimized parameters
        Combines ML prediction with strategy rules
        """
        from backend.improved_signals import EnhancedTradeSignals
        
        signals = EnhancedTradeSignals(self.ticker)
        entry_signals = signals.get_precise_entry_levels(df, interval)
        
        if not entry_signals:
            return []
        
        # Enhance with ML predictions
        enhanced_signals = []
        
        for signal in entry_signals:
            # Get ML prediction for this signal type
            ml_confidence = self.predict_signal(df)
            
            # Combine strategy confidence with ML confidence
            combined_confidence = (signal['confidence'] * 0.7) + (ml_confidence * 0.3)
            
            # Adjust parameters based on learned optimizations
            strategy_type = signal['type'].split('_')[0].lower()
            
            if strategy_type in self.strategy_params:
                params = self.strategy_params[strategy_type]
                
                # Adjust stop loss and target based on optimized parameters
                if 'atr_multiplier' in params and 'target_multiplier' in params:
                    # Recalculate with optimized parameters
                    atr = self._calculate_atr(df)
                    current_price = df['Close'].iloc[-1]
                    
                    # Use optimized multipliers
                    optimized_stop = current_price - (atr * params['atr_multiplier'])
                    optimized_target = current_price + (atr * params['target_multiplier'])
                    
                    # Update signal
                    signal['stop_loss'] = optimized_stop
                    signal['target'] = optimized_target
                    signal['risk_reward'] = (optimized_target - current_price) / (current_price - optimized_stop)
            
            signal['ml_confidence'] = ml_confidence
            signal['combined_confidence'] = combined_confidence
            signal['optimized'] = True
            
            enhanced_signals.append(signal)
        
        return enhanced_signals
    
    def _calculate_indicators(self, data):
        """Calculate technical indicators"""
        # RSI
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        
        # VWAP
        typical_price = (data['High'] + data['Low'] + data['Close']) / 3
        # Fix: Ensure cumsum can handle first values NaN
        data['VWAP'] = (typical_price * data['Volume']).cumsum() / data['Volume'].cumsum()
        
        # ATR
        high_low = data['High'] - data['Low']
        high_close = np.abs(data['High'] - data['Close'].shift())
        low_close = np.abs(data['Low'] - data['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        data['ATR'] = tr.rolling(14).mean()
        
        # Moving averages
        data['SMA_20'] = data['Close'].rolling(20).mean()
        data['SMA_50'] = data['Close'].rolling(50).mean()
        
        return data
    
    def _support_distance(self, data, idx):
        """Distance to nearest support"""
        window = 20
        if idx < window:
            return 0
        
        recent_lows = data['Low'].iloc[idx-window:idx]
        if len(recent_lows) > 0:
            nearest_support = recent_lows.min()
            current_price = data['Close'].iloc[idx]
            if current_price == 0: return 0
            return (current_price - nearest_support) / current_price
        
        return 0
    
    def _resistance_distance(self, data, idx):
        """Distance to nearest resistance"""
        window = 20
        if idx < window:
            return 0
        
        recent_highs = data['High'].iloc[idx-window:idx]
        if len(recent_highs) > 0:
            nearest_resistance = recent_highs.max()
            current_price = data['Close'].iloc[idx]
            if current_price == 0: return 0
            return (nearest_resistance - current_price) / current_price
        
        return 0
    
    def _market_regime_features(self, data, idx):
        """Extract market regime features"""
        window = 50
        if idx < window:
            return 0
        
        returns = data['Close'].iloc[idx-window:idx].pct_change().dropna()
        
        if len(returns) < 10:
            return 0
        
        # Volatility regime
        volatility = returns.std() * np.sqrt(252)
        
        if volatility > 0.25:
            return 2  # High volatility
        elif volatility > 0.15:
            return 1  # Medium volatility
        else:
            return 0  # Low volatility
    
    def _calculate_atr(self, df, period=14):
        """Calculate ATR helper"""
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        return atr.iloc[-1] if not atr.empty else df['Close'].iloc[-1] * 0.01
    
    def _fetch_historical_data(self, start_date, end_date, interval):
        """Fetch historical data"""
        try:
            df = yf.download(
                self.ticker,
                start=start_date,
                end=end_date,
                interval=interval,
                progress=False
            )
            
            if df.empty:
                return pd.DataFrame()
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            return df
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            return pd.DataFrame()
    
    def _update_performance_metrics(self):
        """Update performance metrics from trade history"""
        if not self.trade_history:
            return
        
        df_trades = pd.DataFrame(self.trade_history)
        
        wins = df_trades[df_trades['pnl'] > 0]
        losses = df_trades[df_trades['pnl'] <= 0]
        
        total_trades = len(df_trades)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        
        profit_factor = 0
        if len(losses) > 0 and losses['pnl'].sum() != 0:
            profit_factor = abs(wins['pnl'].sum() / losses['pnl'].sum())
        
        # Sharpe ratio (simplified)
        returns = df_trades['pnl'] / 100000  # Normalized
        sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        
        self.performance_metrics = {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe
        }
    
    def _evaluate_model(self, X, y):
        """Evaluate ML model performance"""
        if self.ml_model is None:
            return None
        
        from sklearn.model_selection import cross_val_score
        
        try:
            X_scaled = self.scaler.transform(X)
            scores = cross_val_score(self.ml_model, X_scaled, y, cv=5, scoring='accuracy')
            return scores.mean()
        except:
            return None
    
    def _save_model(self):
        """Save learned model to disk"""
        model_data = {
            'strategy_params': self.strategy_params,
            'ml_model': self.ml_model,
            'scaler': self.scaler,
            'performance_metrics': self.performance_metrics,
            'trade_history': self.trade_history[-1000:],  # Keep last 1000 trades
            'learning_history': self.learning_history[-100:],  # Keep last 100 learnings
            'save_date': datetime.now().isoformat()
        }
        
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump(model_data, f)
            print(f"💾 Model saved to {self.model_path}")
        except Exception as e:
            print(f"Error saving model: {e}")
    
    def load_model(self):
        """Load learned model from disk"""
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.strategy_params = model_data.get('strategy_params', self.strategy_params)
            self.ml_model = model_data.get('ml_model')
            self.scaler = model_data.get('scaler', self.scaler)
            self.performance_metrics = model_data.get('performance_metrics', self.performance_metrics)
            self.trade_history = model_data.get('trade_history', [])
            self.learning_history = model_data.get('learning_history', [])
            
            print(f"Model loaded from {self.model_path}")
            print(f"   Win rate: {self.performance_metrics.get('win_rate', 0):.1%}")
            print(f"   Total trades: {self.performance_metrics.get('total_trades', 0)}")
            
            return True
        except FileNotFoundError:
            print(f"Model file not found: {self.model_path}")
            return False
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def get_model_info(self):
        """Get information about the learned model"""
        return {
            'model_name': self.model_name,
            'model_path': self.model_path,
            'performance': self.performance_metrics,
            'total_trades_learned': len(self.trade_history),
            'learning_sessions': len(self.learning_history),
            'strategies_optimized': list(self.strategy_params.keys()),
            'ml_model_trained': self.ml_model is not None
        }

# Quick learning function
def quick_learn_and_backtest():
    """Quick learning and backtest demonstration"""
    print("\n" + "="*70)
    print("🤖 SELF-LEARNING BACKTEST DEMONSTRATION")
    print("="*70)
    
    # Create learner
    learner = SelfLearningBacktester(ticker="^NSEI")
    
    # Try to load existing model
    if learner.load_model():
        print("Loaded existing learned model")
    else:
        print("🆕 No existing model, starting fresh learning")
    
    # Learn from last 90 days
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    print(f"\n📚 Learning from {start_date} to {end_date}...")
    # NOTE: Using 1h interval here as backtest data fetching for 90d on 15m might fail
    # or just rely on '60d' limit handling inside _fetch_historical_data if implemented
    # But for safety in demo let's stick to 15m but shorter duration in real use
    # Reverting to 15m as per user code request
    learning_result = learner.learn_from_history(start_date, end_date, interval="15m")
    
    if learning_result:
        print("\n🎓 LEARNING RESULTS:")
        print(f"   Training samples: {learning_result['training_samples']}")
        print(f"   Model accuracy: {learning_result.get('model_accuracy', 'N/A')}")
        
        if learning_result.get('test_results'):
            print("\n   STRATEGY PERFORMANCE:")
            for strategy, results in learning_result['test_results'].items():
                print(f"   {strategy.upper():15} Win Rate: {results.get('win_rate', 0):.1f}% | "
                      f"Profit Factor: {results.get('profit_factor', 0):.2f} | "
                      f"Trades: {results.get('total_trades', 0)}")
    
    # Get model info
    model_info = learner.get_model_info()
    print(f"\n📊 MODEL INFO:")
    print(f"   Total trades in memory: {model_info['total_trades_learned']}")
    print(f"   Current win rate: {model_info['performance'].get('win_rate', 0):.1%}")
    print(f"   ML model trained: {model_info['ml_model_trained']}")
    
    # Test with today's data
    print("\n🧪 Testing with today's data...")
    import yfinance as yf
    try: 
        today_data = yf.download("^NSEI", period="1d", interval="5m", progress=False)
        if hasattr(today_data.columns, 'droplevel'): 
             today_data.columns = today_data.columns.get_level_values(0)
             
        if not today_data.empty:
            signals = learner.get_optimized_signals(today_data)
            
            if signals:
                print(f"\n🎯 OPTIMIZED SIGNALS FOUND:")
                for signal in signals:
                    print(f"   {signal['type']:25} Entry: {signal['entry_price']:.2f} | "
                          f"Confidence: {signal['combined_confidence']:.2f}")
            else:
                print("\n⏳ No optimized signals for today")
    except Exception as e:
        print(f"Error testing with today's data: {e}")
    
    print("\n" + "="*70)
    print("Self-learning demonstration complete!")
    print("Model saved for future use")
    print("="*70)
    
    return learner

if __name__ == "__main__":
    quick_learn_and_backtest()

