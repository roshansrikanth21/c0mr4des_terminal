"""
Input validation for all API endpoints using Pydantic models.
Ensures data integrity and prevents injection attacks.
"""

import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
from backend.exceptions import ValidationError

class TradingRequest(BaseModel):
    """Base model for trading-related requests"""
    ticker: str = Field(..., description="Stock ticker symbol (e.g., ^NSEI, RELIANCE.NS)")
    interval: str = Field(default="1d", description="Data interval")
    period: str = Field(default="1y", description="Data period")
    
    @field_validator('ticker')
    @classmethod
    def validate_ticker(cls, v):
        # Allow valid ticker formats: ^INDEX, SYMBOL.NS, or plain symbol
        if not re.match(r'^\^?[A-Z]{1,5}(\.NS)?$', v.upper()):
            raise ValidationError(f'Invalid ticker format: {v}. Use format like ^NSEI, RELIANCE.NS, or SBIN')
        return v.upper()
    
    @field_validator('interval')
    @classmethod
    def validate_interval(cls, v):
        valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
        if v not in valid_intervals:
            raise ValidationError(f'Invalid interval. Must be one of: {valid_intervals}')
        return v
    
    @field_validator('period')
    @classmethod
    def validate_period(cls, v):
        valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
        if v not in valid_periods:
            raise ValidationError(f'Invalid period. Must be one of: {valid_periods}')
        return v

class RegimeAnalysisRequest(TradingRequest):
    """Request for market regime analysis"""
    pass

class HistoryRequest(TradingRequest):
    """Request for historical data"""
    include_indicators: bool = Field(default=True, description="Include technical indicators")

class BacktestRequest(BaseModel):
    """Request for backtesting"""
    ticker: str = Field(default="^NSEI", description="Ticker to backtest")
    interval: str = Field(default="15m", description="Data interval")
    period: str = Field(default="60d", description="Backtest period")
    strategy: str = Field(default="default", description="Strategy to test")
    
    @field_validator('strategy')
    @classmethod
    def validate_strategy(cls, v):
        valid_strategies = ['default', 'vwap_pullback', 'mean_reversion', 'momentum', 'ict']
        if v not in valid_strategies:
            raise ValidationError(f'Invalid strategy. Must be one of: {valid_strategies}')
        return v

class ICTAnalysisRequest(TradingRequest):
    """Request for ICT Smart Money analysis"""
    period: str = Field(default="60d", description="Analysis period")

class QuantAnalysisRequest(TradingRequest):
    """Request for quantitative analysis"""
    analysis_type: str = Field(default="comprehensive", description="Type of analysis")
    
    @field_validator('analysis_type')
    @classmethod
    def validate_analysis_type(cls, v):
        valid_types = ['comprehensive', 'regime', 'volatility', 'correlation', 'statistical']
        if v not in valid_types:
            raise ValidationError(f'Invalid analysis type. Must be one of: {valid_types}')
        return v

class IntradayRequest(TradingRequest):
    """Request for intraday analysis"""
    interval: str = Field(default="5m", description="Intraday interval")
    
    @field_validator('interval')
    @classmethod
    def validate_intraday_interval(cls, v):
        intraday_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m']
        if v not in intraday_intervals:
            raise ValidationError(f'Invalid intraday interval. Must be one of: {intraday_intervals}')
        return v

class OrderRequest(BaseModel):
    """Request for placing orders"""
    symbol: str = Field(..., description="Trading symbol")
    action: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., description="Order quantity")
    order_type: str = Field(default="MARKET", description="Order type")
    price: Optional[float] = Field(None, description="Limit price (required for LIMIT orders)")
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v):
        if v.upper() not in ['BUY', 'SELL']:
            raise ValidationError('Action must be BUY or SELL')
        return v.upper()
    
    @field_validator('order_type')
    @classmethod
    def validate_order_type(cls, v):
        if v.upper() not in ['MARKET', 'LIMIT', 'SL', 'SLM']:
            raise ValidationError('Order type must be MARKET, LIMIT, SL, or SLM')
        return v.upper()

    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValidationError('Quantity must be positive')
        return v

    @model_validator(mode='after')
    def validate_price(self):
        if self.order_type in ['LIMIT', 'SL', 'SLM'] and self.price is None:
            raise ValidationError('Price is required for LIMIT/SL/SLM orders')
        if self.price is not None and self.price <= 0:
            raise ValidationError('Price must be positive')
        return self

class BrokerConnectionRequest(BaseModel):
    """Request for broker connection"""
    mode: str = Field(..., description="Broker mode")
    api_key: Optional[str] = Field(None, description="API key (if not using stored key)")
    api_secret: Optional[str] = Field(None, description="API secret (if not using stored key)")
    
    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v):
        if v.upper() not in ['PAPER', 'ANGEL_ONE', 'ZERODHA', 'UPSTOX']:
            raise ValidationError('Mode must be PAPER, ANGEL_ONE, ZERODHA, or UPSTOX')
        return v.upper()

class LearningRequest(BaseModel):
    """Request for learning system"""
    days: int = Field(default=30, ge=1, le=365, description="Number of days for analysis")
    
class ChatRequest(BaseModel):
    """Request for chat with analysis"""
    context: str = Field(..., description="Previous analysis context")
    question: str = Field(..., description="User question")
    
    @field_validator('context', 'question')
    @classmethod
    def validate_no_injection(cls, v):
        # Basic validation to prevent injection attempts
        dangerous_patterns = [
            r'<script.*?>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'eval\s*\(',
            r'exec\s*\('
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValidationError('Invalid characters detected in input')
        return v.strip()

class ImageAnalysisRequest(BaseModel):
    """Request for image analysis"""
    max_files: int = Field(default=5, ge=1, le=10, description="Maximum number of images")
    
    @field_validator('max_files')
    @classmethod
    def validate_max_files(cls, v):
        if v > 10:
            raise ValidationError('Cannot process more than 10 images at once')
        return v
