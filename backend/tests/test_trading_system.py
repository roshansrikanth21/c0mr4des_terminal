"""
Comprehensive unit tests for the trading system.
Tests core functionality, error handling, and edge cases.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import json

# Import modules to test
from backend.config.secure_config import TradingConfig, SecureConfigManager
from backend.validation.input_validation import (
    TradingRequest, BacktestRequest, OrderRequest, ValidationError
)
from backend.exceptions import (
    TradingSystemError, InsufficientDataError, DataProviderError,
    ModelGenerationError, APIKeyMissingError
)
from backend.services.market_data_service import (
    AsyncMarketDataService, YahooFinanceProvider, SyntheticDataProvider
)
from backend.services.image_analysis_service import ImageAnalysisService

class TestTradingConfig:
    """Test trading configuration validation"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = TradingConfig()
        assert config.ou_entry_z == 1.5
        assert config.min_confidence == 0.6
        assert config.max_daily_loss_percent == 2.0
    
    def test_valid_config(self):
        """Test configuration with valid parameters"""
        config = TradingConfig(
            ou_entry_z=2.0,
            min_confidence=0.7,
            max_daily_loss_percent=3.0
        )
        config.validate()  # Should not raise
        assert config.ou_entry_z == 2.0
        assert config.min_confidence == 0.7
    
    def test_invalid_config_low_values(self):
        """Test configuration with values below minimum"""
        config = TradingConfig(min_confidence=0.05)  # Below 0.1 minimum
        with pytest.raises(ValueError, match="min_confidence.*below minimum"):
            config.validate()
    
    def test_invalid_config_high_values(self):
        """Test configuration with values above maximum"""
        config = TradingConfig(max_daily_loss_percent=15.0)  # Above 10.0 maximum
        with pytest.raises(ValueError, match="max_daily_loss_percent.*above maximum"):
            config.validate()

class TestSecureConfigManager:
    """Test secure configuration management"""
    
    def test_config_validation(self):
        """Test configuration validation through manager"""
        manager = SecureConfigManager()
        config = manager.get_config()
        
        # Test valid update
        manager.update_config(min_confidence=0.8)
        assert config.min_confidence == 0.8
        
        # Test invalid update
        with pytest.raises(ValueError):
            manager.update_config(min_confidence=0.05)  # Below minimum
    
    @patch('backend.config.secure_config.keyring')
    def test_api_key_storage(self, mock_keyring):
        """Test API key storage and retrieval"""
        mock_keyring.get_password.return_value = None
        mock_keyring.set_password = Mock()
        
        manager = SecureConfigManager()
        
        # Test storing API key
        manager.store_api_key("test_service", "test_key_123")
        mock_keyring.set_password.assert_called_once()
        
        # Test retrieving API key
        mock_keyring.get_password.return_value = "encrypted_key"
        with patch.object(manager.cipher_suite, 'decrypt') as mock_decrypt:
            mock_decrypt.return_value = b"test_key_123"
            key = manager.get_api_key("test_service")
            assert key == "test_key_123"
    
    def test_required_api_key_missing(self):
        """Test error when required API key is missing"""
        manager = SecureConfigManager()
        
        with pytest.raises(APIKeyMissingError):
            manager.get_required_api_key("missing_service")

class TestInputValidation:
    """Test input validation models"""
    
    def test_valid_trading_request(self):
        """Test valid trading request"""
        request = TradingRequest(ticker="^NSEI", interval="5m", period="1mo")
        assert request.ticker == "^NSEI"
        assert request.interval == "5m"
        assert request.period == "1mo"
    
    def test_invalid_ticker_format(self):
        """Test invalid ticker format"""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            TradingRequest(ticker="invalid@ticker")
    
    def test_invalid_interval(self):
        """Test invalid interval"""
        with pytest.raises(ValidationError, match="Invalid interval"):
            TradingRequest(ticker="^NSEI", interval="invalid_interval")
    
    def test_invalid_period(self):
        """Test invalid period"""
        with pytest.raises(ValidationError, match="Invalid period"):
            TradingRequest(ticker="^NSEI", period="invalid_period")
    
    def test_valid_order_request(self):
        """Test valid order request"""
        order = OrderRequest(
            symbol="RELIANCE.NS",
            action="BUY",
            quantity=10,
            order_type="MARKET"
        )
        assert order.symbol == "RELIANCE.NS"
        assert order.action == "BUY"
        assert order.quantity == 10
    
    def test_limit_order_requires_price(self):
        """Test that limit orders require a price"""
        with pytest.raises(ValidationError, match="Price is required"):
            OrderRequest(
                symbol="RELIANCE.NS",
                action="BUY",
                quantity=10,
                order_type="LIMIT"
                # Missing price
            )
    
    def test_negative_quantity(self):
        """Test that quantity must be positive"""
        with pytest.raises(ValidationError):
            OrderRequest(
                symbol="RELIANCE.NS",
                action="BUY",
                quantity=-5,
                order_type="MARKET"
            )

class TestAsyncMarketDataService:
    """Test async market data service"""
    
    @pytest.fixture
    def service(self):
        """Create service instance for testing"""
        return AsyncMarketDataService()
    
    @pytest.fixture
    def sample_data(self):
        """Create sample market data"""
        dates = pd.date_range(start='2023-01-01', periods=100, freq='1D')
        return pd.DataFrame({
            'Open': np.random.uniform(100, 110, 100),
            'High': np.random.uniform(110, 120, 100),
            'Low': np.random.uniform(90, 100, 100),
            'Close': np.random.uniform(100, 110, 100),
            'Volume': np.random.randint(1000000, 10000000, 100)
        }, index=dates)
    
    def test_data_validation(self, service, sample_data):
        """Test data validation logic"""
        # Valid data should pass
        assert service._validate_data(sample_data) == True
        
        # Empty data should fail
        assert service._validate_data(pd.DataFrame()) == False
        
        # Missing columns should fail
        invalid_data = sample_data.drop('Volume', axis=1)
        assert service._validate_data(invalid_data) == False
        
        # Invalid price relationships should fail
        invalid_data = sample_data.copy()
        invalid_data.loc[invalid_data.index[0], 'High'] = 50  # High < Low
        assert service._validate_data(invalid_data) == False
    
    def test_cache_functionality(self, service):
        """Test caching mechanism"""
        cache_key = "TEST_1d_1d"
        
        # Cache should be invalid initially
        assert service._is_cache_valid(cache_key) == False
        
        # Add to cache
        test_data = pd.DataFrame({'test': [1, 2, 3]})
        service.cache[cache_key] = {
            'data': test_data,
            'timestamp': pd.Timestamp.now().timestamp()
        }
        
        # Cache should be valid now
        assert service._is_cache_valid(cache_key) == True
    
    @patch('yfinance.download')
    async def test_yahoo_finance_provider(self, mock_download, sample_data):
        """Test Yahoo Finance provider"""
        mock_download.return_value = sample_data
        
        provider = YahooFinanceProvider()
        data = await provider.fetch_data("^NSEI", "1y", "1d")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        assert 'Open' in data.columns
        mock_download.assert_called_once()
    
    async def test_synthetic_data_provider(self):
        """Test synthetic data provider"""
        provider = SyntheticDataProvider()
        data = await provider.fetch_data("TEST", "1y", "1d")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        assert len(data) >= 100  # Should generate at least 100 data points
        assert 'Open' in data.columns
        assert 'High' in data.columns
        assert 'Low' in data.columns
        assert 'Close' in data.columns
        assert 'Volume' in data.columns

class TestImageAnalysisService:
    """Test image analysis service"""
    
    @pytest.fixture
    def service(self):
        """Create service instance for testing"""
        return ImageAnalysisService()
    
    @patch('backend.services.image_analysis_service.config_manager')
    def test_initialization_with_api_key(self, mock_config):
        """Test service initialization with API key"""
        mock_config.get_required_api_key.return_value = "test_api_key"
        
        service = ImageAnalysisService()
        assert service.api_key == "test_api_key"
        assert service.client is not None
    
    @patch('backend.services.image_analysis_service.config_manager')
    def test_initialization_without_api_key(self, mock_config):
        """Test service initialization without API key"""
        mock_config.get_required_api_key.side_effect = APIKeyMissingError("gemini")
        
        service = ImageAnalysisService()
        assert service.api_key is None
        assert service.client is None
    
    def test_create_analysis_prompt(self, service):
        """Test prompt creation for different image counts"""
        # Single image prompt
        prompt_single = service._create_analysis_prompt(1)
        assert "the provided chart" in prompt_single
        
        # Multiple image prompt
        prompt_multi = service._create_analysis_prompt(3)
        assert "CROSS-TIMEFRAME context" in prompt_multi
    
    def test_parse_response_valid_json(self, service):
        """Test parsing valid JSON response"""
        response_text = '{"ticker_detected": "^NSEI", "confidence": 0.85}'
        result = service._parse_response(response_text)
        
        assert result['ticker_detected'] == "^NSEI"
        assert result['confidence'] == 0.85
    
    def test_parse_response_json_with_extra_text(self, service):
        """Test parsing JSON response with extra text"""
        response_text = 'Here is the analysis: {"ticker_detected": "^NSEI", "confidence": 0.85} End of analysis.'
        result = service._parse_response(response_text)
        
        assert result['ticker_detected'] == "^NSEI"
        assert result['confidence'] == 0.85
    
    def test_parse_response_invalid_json(self, service):
        """Test parsing invalid JSON response"""
        response_text = 'This is not valid JSON'
        
        with pytest.raises(ModelGenerationError, match="Failed to parse JSON"):
            service._parse_response(response_text)
    
    def test_create_error_response(self, service):
        """Test error response creation"""
        error_msg = "Test error message"
        response = service._create_error_response(error_msg)
        
        assert response['is_chart'] == False
        assert response['patterns'] == ["System Error"]
        assert response['sentiment'] == "Neutral"
        assert response['confidence'] == 0.0
        assert response['action_type'] == "WAIT"
        assert response['error'] == error_msg

class TestTradingStrategies:
    """Test trading strategy logic"""
    
    @pytest.fixture
    def sample_ohlcv(self):
        """Create sample OHLCV data for strategy testing"""
        dates = pd.date_range(start='2023-01-01', periods=200, freq='5min')
        
        # Create realistic price data with trend
        np.random.seed(42)
        base_price = 100
        returns = np.random.normal(0.0001, 0.002, 200)  # Small positive drift
        prices = base_price * np.exp(np.cumsum(returns))
        
        return pd.DataFrame({
            'Open': np.roll(prices, 1),
            'High': prices * (1 + np.abs(np.random.normal(0, 0.001, 200))),
            'Low': prices * (1 - np.abs(np.random.normal(0, 0.001, 200))),
            'Close': prices,
            'Volume': np.random.randint(100000, 1000000, 200)
        }, index=dates)
    
    def test_vwap_calculation(self, sample_ohlcv):
        """Test VWAP calculation"""
        # Import VWAP calculation function
        from backend.intraday_utils import calculate_vwap
        
        vwap = calculate_vwap(
            sample_ohlcv['High'],
            sample_ohlcv['Low'],
            sample_ohlcv['Close'],
            sample_ohlcv['Volume']
        )
        
        assert len(vwap) == len(sample_ohlcv)
        assert not vwap.isna().all()  # Should have some valid values
        
        # VWAP should be between high and low (approximately)
        for i in range(10, len(vwap)):  # Skip initial values
            if not pd.isna(vwap.iloc[i]):
                assert sample_ohlcv['Low'].iloc[i] <= vwap.iloc[i] <= sample_ohlcv['High'].iloc[i]
    
    def test_sma_calculation(self, sample_ohlcv):
        """Test SMA calculation"""
        from backend.market_data import calculate_sma
        
        sma_9 = calculate_sma(sample_ohlcv['Close'], 9)
        sma_21 = calculate_sma(sample_ohlcv['Close'], 21)
        
        assert len(sma_9) == len(sample_ohlcv)
        assert len(sma_21) == len(sample_ohlcv)
        
        # SMA should be close to price (within reasonable range)
        for i in range(21, len(sma_21)):  # Skip initial values
            if not pd.isna(sma_21.iloc[i]):
                price = sample_ohlcv['Close'].iloc[i]
                assert abs(price - sma_21.iloc[i]) < price * 0.1  # Within 10%
    
    def test_rsi_calculation(self, sample_ohlcv):
        """Test RSI calculation"""
        from backend.market_data import calculate_rsi
        
        rsi = calculate_rsi(sample_ohlcv['Close'], 14)
        
        assert len(rsi) == len(sample_ohlcv)
        
        # RSI should be between 0 and 100
        for i in range(14, len(rsi)):  # Skip initial values
            if not pd.isna(rsi.iloc[i]):
                assert 0 <= rsi.iloc[i] <= 100
    
    def test_atr_calculation(self, sample_ohlcv):
        """Test ATR calculation"""
        from backend.market_data import calculate_atr
        
        atr = calculate_atr(
            sample_ohlcv['High'],
            sample_ohlcv['Low'],
            sample_ohlcv['Close'],
            14
        )
        
        assert len(atr) == len(sample_ohlcv)
        
        # ATR should be positive
        for i in range(14, len(atr)):  # Skip initial values
            if not pd.isna(atr.iloc[i]):
                assert atr.iloc[i] > 0

class TestErrorHandling:
    """Test error handling throughout the system"""
    
    def test_trading_system_error_hierarchy(self):
        """Test that custom exceptions inherit properly"""
        assert issubclass(InsufficientDataError, TradingSystemError)
        assert issubclass(DataProviderError, TradingSystemError)
        assert issubclass(ModelGenerationError, TradingSystemError)
        assert issubclass(APIKeyMissingError, TradingSystemError)
        assert issubclass(ValidationError, TradingSystemError)
    
    def test_exception_messages(self):
        """Test exception messages are descriptive"""
        error = InsufficientDataError("Not enough data")
        assert str(error) == "Not enough data"
        
        error = APIKeyMissingError("gemini")
        assert "gemini" in str(error)
        
        error = ValidationError("Invalid input")
        assert str(error) == "Invalid input"

class TestIntegrationScenarios:
    """Test integration scenarios and end-to-end workflows"""
    
    @patch('backend.services.market_data_service.yfinance.download')
    async def test_market_data_to_analysis_workflow(self, mock_download):
        """Test complete workflow from data fetch to analysis"""
        # Create sample data
        dates = pd.date_range(start='2023-01-01', periods=100, freq='1D')
        sample_data = pd.DataFrame({
            'Open': np.random.uniform(100, 110, 100),
            'High': np.random.uniform(110, 120, 100),
            'Low': np.random.uniform(90, 100, 100),
            'Close': np.random.uniform(100, 110, 100),
            'Volume': np.random.randint(1000000, 10000000, 100)
        }, index=dates)
        
        mock_download.return_value = sample_data
        
        # Test async data service
        service = AsyncMarketDataService()
        data = await service.get_market_data("^NSEI", "1y", "1d")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        
        # Test that data can be used for indicators
        from backend.market_data import calculate_sma
        sma = calculate_sma(data['Close'], 20)
        assert len(sma) == len(data)
    
    def test_configuration_to_validation_workflow(self):
        """Test workflow from configuration to input validation"""
        # Create custom configuration
        manager = SecureConfigManager()
        manager.update_config(
            min_confidence=0.8,
            max_daily_loss_percent=3.0
        )
        
        # Test that validation respects configuration
        config = manager.get_config()
        assert config.min_confidence == 0.8
        
        # This should pass validation
        request = TradingRequest(ticker="^NSEI", confidence=0.85)
        assert request.ticker == "^NSEI"

# Performance tests
class TestPerformance:
    """Test performance characteristics"""
    
    def test_data_processing_performance(self):
        """Test performance with large datasets"""
        # Create large dataset
        dates = pd.date_range(start='2022-01-01', periods=10000, freq='1min')
        large_data = pd.DataFrame({
            'Open': np.random.uniform(100, 110, 10000),
            'High': np.random.uniform(110, 120, 10000),
            'Low': np.random.uniform(90, 100, 10000),
            'Close': np.random.uniform(100, 110, 10000),
            'Volume': np.random.randint(100000, 1000000, 10000)
        }, index=dates)
        
        import time
        start_time = time.time()
        
        # Calculate indicators
        from backend.market_data import calculate_sma, calculate_rsi, calculate_atr
        sma = calculate_sma(large_data['Close'], 20)
        rsi = calculate_rsi(large_data['Close'], 14)
        atr = calculate_atr(large_data['High'], large_data['Low'], large_data['Close'], 14)
        
        processing_time = time.time() - start_time
        
        # Should process 10k data points in under 2 seconds
        assert processing_time < 2.0
        assert len(sma) == len(large_data)
        assert len(rsi) == len(large_data)
        assert len(atr) == len(large_data)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])