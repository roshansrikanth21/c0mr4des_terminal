"""
Service Manager for AI Trading System
Handles lazy initialization and singleton management for all heavy components.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ServiceManager:
    """Registry for all trading system services with lazy initialization."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance._services = {}
        return cls._instance

    @property
    def market_data(self):
        """Lazy-loaded Market Data Service"""
        if 'market_data' not in self._services:
            from backend.services.market_data_service import async_market_data_service
            self._services['market_data'] = async_market_data_service
            logger.info("✓ Market Data Service registered")
        return self._services['market_data']

    @property
    def advanced_trading_system(self):
        """Lazy-loaded Advanced Trading System (Master Controller)"""
        if 'advanced_trading_system' not in self._services:
            from backend.advanced_analysis import AdvancedTradingSystem
            # Initialize with default ticker, but can be updated later
            self._services['advanced_trading_system'] = AdvancedTradingSystem(ticker="^NSEI")
            logger.info("✓ Advanced Trading System initialized (Lazy)")
        return self._services['advanced_trading_system']

    @property
    def execution_engine(self):
        """Lazy-loaded Execution Engine"""
        if 'execution_engine' not in self._services:
            from backend.execution_engine import ExecutionEngine
            self._services['execution_engine'] = ExecutionEngine()
            logger.info("✓ Execution Engine initialized (Lazy)")
        return self._services['execution_engine']

    @property
    def learning_manager(self):
        """Lazy-loaded Continuous Learning Manager"""
        if 'learning_manager' not in self._services:
            try:
                from backend.learning_tracker import ContinuousLearningManager
                self._services['learning_manager'] = ContinuousLearningManager()
                logger.info("✓ Learning Manager initialized (Lazy)")
            except Exception as e:
                logger.warning(f"⚠ Could not initialize Learning Manager: {e}")
                self._services['learning_manager'] = None
        return self._services['learning_manager']

    @property
    def bayesian_model(self):
        """Lazy-loaded Bayesian Inference Model"""
        if 'bayesian_model' not in self._services:
            from backend.bayesian_inference import BayesianTradingModel
            self._services['bayesian_model'] = BayesianTradingModel(prior_alpha=5, prior_beta=3)
            logger.info("✓ Bayesian Trading Model initialized (Lazy)")
        return self._services['bayesian_model']

    @property
    def market_timing(self):
        """Lazy-loaded Market Timing Service"""
        if 'market_timing' not in self._services:
            from backend.nifty_timing import IndianMarketTiming
            self._services['market_timing'] = IndianMarketTiming()
            logger.info("✓ Indian Market Timing initialized (Lazy)")
        return self._services['market_timing']

    @property
    def risk_analyzer(self):
        """Lazy-loaded Monte Carlo Risk Analyzer"""
        if 'risk_analyzer' not in self._services:
            from backend.monte_carlo import MonteCarloRiskAnalyzer
            self._services['risk_analyzer'] = MonteCarloRiskAnalyzer(ticker="^NSEI")
            logger.info("✓ Risk Analyzer initialized (Lazy)")
        return self._services['risk_analyzer']

    @property
    def memory_service(self):
        """Lazy-loaded Supermemory AI Service"""
        if 'memory_service' not in self._services:
            from backend.services.memory_service import memory_service
            self._services['memory_service'] = memory_service
            logger.info("✓ Memory Service initialized (Lazy)")
        return self._services['memory_service']

    def initialize_all_background(self):
        """
        Safety method to pre-warm all services in background threads if needed.
        Doesn't block the main event loop.
        """
        import threading
        
        def _warm_up():
            logger.info("Pre-warming services in background...")
            _ = self.advanced_trading_system
            _ = self.learning_manager
            if self.learning_manager:
                try:
                    self.learning_manager.initialize()
                except:
                    pass
            logger.info("Background service warming complete.")
            
        threading.Thread(target=_warm_up, daemon=True).start()

# Global Instance
service_manager = ServiceManager()
