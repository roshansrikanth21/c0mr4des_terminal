"""
Configuration for the quantitative trading system
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration settings"""
    
    # Trading parameters
    INITIAL_CAPITAL = 1000000
    RISK_PER_TRADE = 0.01  # 1% per trade
    MAX_POSITION_SIZE = 0.1  # Max 10% of capital in one trade
    
    # Market hours (IST)
    MARKET_OPEN = "09:15"
    MARKET_CLOSE = "15:30"
    
    # Email configuration
    EMAIL_CONFIG = {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': os.getenv('EMAIL_USERNAME'),
        'password': os.getenv('EMAIL_PASSWORD'),
        'from_email': os.getenv('FROM_EMAIL'),
        'to_emails': os.getenv('TO_EMAILS', '').split(','),
        'alert_emails': os.getenv('ALERT_EMAILS', '').split(',')
    }
    
    # Trading thresholds
    OU_ENTRY_Z = 1.5
    OU_EXIT_Z = 0.5
    MIN_CONFIDENCE = 0.6
    
    # Data settings
    DATA_CACHE_DIR = "data/cache"
    REPORTS_DIR = "reports"
    BACKTEST_RESULTS_DIR = "backtest_results"
    
    @classmethod
    def setup_directories(cls):
        """Create necessary directories"""
        os.makedirs(cls.DATA_CACHE_DIR, exist_ok=True)
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
        os.makedirs(cls.BACKTEST_RESULTS_DIR, exist_ok=True)
