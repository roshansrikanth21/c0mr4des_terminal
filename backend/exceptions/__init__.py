"""
Custom exceptions for the trading system.
Provides specific error types for better error handling and debugging.
"""

class TradingSystemError(Exception):
    """Base class for all trading system errors"""
    pass

class InsufficientDataError(TradingSystemError):
    """Raised when not enough data for analysis"""
    def __init__(self, message="Insufficient data available for analysis"):
        super().__init__(message)

class RiskLimitExceededError(TradingSystemError):
    """Raised when trade exceeds risk limits"""
    def __init__(self, message="Trade exceeds risk limits"):
        super().__init__(message)

class DataProviderError(TradingSystemError):
    """Raised when all data providers fail"""
    def __init__(self, message="All data providers failed"):
        super().__init__(message)

class APIKeyMissingError(TradingSystemError):
    """Raised when required API key is missing"""
    def __init__(self, service="API"):
        super().__init__(f"API key for {service} is missing or invalid")

class ModelGenerationError(TradingSystemError):
    """Raised when AI model generation fails"""
    def __init__(self, message="AI model generation failed"):
        super().__init__(message)

class ValidationError(TradingSystemError):
    """Raised when input validation fails"""
    def __init__(self, message="Input validation failed"):
        super().__init__(message)

class BrokerConnectionError(TradingSystemError):
    """Raised when broker connection fails"""
    def __init__(self, message="Failed to connect to broker"):
        super().__init__(message)

class OrderExecutionError(TradingSystemError):
    """Raised when order execution fails"""
    def __init__(self, message="Order execution failed"):
        super().__init__(message)