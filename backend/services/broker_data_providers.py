"""
Broker-based Market Data Providers
Provides real-time, accurate data from Indian brokers with order flow depth
"""

import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import os
import logging

from backend.config.secure_config import config_manager
from backend.exceptions import DataProviderError, BrokerConnectionError

try:
    import logzero
    logzero.loglevel(logging.CRITICAL)
except Exception:
    pass

try:
    from SmartApi import SmartConnect
    ANGEL_ONE_AVAILABLE = True
except ImportError:
    ANGEL_ONE_AVAILABLE = False

try:
    from kiteconnect import KiteConnect
    ZERODHA_AVAILABLE = True
except ImportError:
    ZERODHA_AVAILABLE = False

# from exceptions import DataProviderError (Already imported from backend.exceptions above)

logger = logging.getLogger(__name__)
# Suppress SmartAPI verbose request logging to avoid leaking credential fields in error traces.
logging.getLogger("smartConnect").setLevel(logging.CRITICAL)
logging.getLogger("SmartApi").setLevel(logging.CRITICAL)


class BrokerDataProvider:
    """Base class for broker-based data providers"""
    
    def __init__(self):
        self.connected = False
        self.token_map = {}
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch OHLCV data - to be implemented by subclasses"""
        raise NotImplementedError
    
    async def get_order_book(self, symbol: str) -> Dict:
        """Get Level 2 order book with bid/ask depth"""
        raise NotImplementedError
    

    async def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> pd.DataFrame:
        """Get option chain data"""
        raise NotImplementedError


class TrueDataProvider(BrokerDataProvider):
    """
    TrueData (GDFL) Velocity 2.0 Data Provider
    Professional grade data feed for Indian markets.
    """
    
    def __init__(self):
        super().__init__()
        self.username = config_manager.get_secret("TRUEDATA_USER")
        self.password = config_manager.get_secret("TRUEDATA_PASS")
        self.base_url = "https://history.truedata.in/gethistory"
        self.connected = False
        
        if self.username and self.password:
            self._test_connection()
            
    def _test_connection(self):
        import requests
        from datetime import datetime, timedelta
        try:
            params = {
                "symbol": "NIFTY 50",
                "from": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "to": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "interval": "D",
                "user": self.username,
                "password": self.password,
                "csv": "1"
            }
            res = requests.get(self.base_url, params=params, timeout=5)
            if res.status_code == 200 and "Invalid user" not in res.text and "Error" not in res.text:
                self.connected = True
                logger.info("[OK] TrueData API connectivity verified via test fetch.")
            else:
                logger.warning(f"TrueData test fetch failed or returned error: {res.text[:100]}")
        except Exception as e:
            logger.warning(f"TrueData connection test exception: {e}")

    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch historical data from TrueData REST API"""
        if not self.username or not self.password:
            raise DataProviderError("TrueData credentials not configured")
        if not self.connected:
            raise DataProviderError("TrueData not connected")

        # Map ticker (TrueData expects symbols without symbols like ^)
        symbol = ticker.replace("^", "")
        if symbol == "NSEI": symbol = "NIFTY 50"
        if symbol == "NSEBANK": symbol = "NIFTY BANK"
        
        # Map interval
        interval_map = {
            "1m": "1", "5m": "5", "15m": "15",
            "30m": "30", "1h": "60", "1d": "D"
        }
        td_interval = interval_map.get(interval, "D")
        
        # Calculate date range
        end_date = datetime.now()
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730
        }
        days = period_days.get(period, 365)
        start_date = end_date - timedelta(days=days)

        params = {
            "symbol": symbol,
            "from": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "to": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "interval": td_interval,
            "user": self.username,
            "password": self.password,
            "csv": "1"
        }

        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.base_url, params=params, timeout=10) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "Invalid" in text or "Error" in text:
                            raise DataProviderError(f"TrueData API Error: {text[:100]}")
                        
                        from io import StringIO
                        # TrueData CSV usually: Date,Time,Open,High,Low,Close,Volume
                        df = pd.read_csv(StringIO(text))
                        
                        if df.empty:
                            return pd.DataFrame()

                        # Standardize columns
                        # Expected format check
                        if 'Date' in df.columns and 'Time' in df.columns:
                            df['datetime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
                            df.set_index('datetime', inplace=True)
                        elif 'Date' in df.columns:
                            df['Date'] = pd.to_datetime(df['Date'])
                            df.set_index('Date', inplace=True)

                        column_map = {
                            'Open': 'Open', 'High': 'High', 'Low': 'Low',
                            'Close': 'Close', 'Volume': 'Volume'
                        }
                        # Ensure we pick standard names regardless of case
                        lower_cols = {c.lower(): c for c in df.columns}
                        final_cols = {}
                        for std in ['Open', 'High', 'Low', 'Close', 'Volume']:
                            if std.lower() in lower_cols:
                                final_cols[lower_cols[std.lower()]] = std
                        
                        df.rename(columns=final_cols, inplace=True)
                        return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
                    else:
                        raise DataProviderError(f"TrueData HTTP {response.status}")
            except Exception as e:
                raise DataProviderError(f"TrueData request failed: {e}")


class AngelOneDataProvider(BrokerDataProvider):
    """
    Angel One SmartAPI Data Provider
    Provides real-time data with order book depth
    """
    
    def __init__(self):
        super().__init__()
        self.api_key = config_manager.get_secret("ANGEL_API_KEY") or config_manager.get_api_key("angel")
        self.client_id = config_manager.get_secret("ANGEL_CLIENT_ID")
        self.password = config_manager.get_secret("ANGEL_PASSWORD")
        self.totp_key = config_manager.get_secret("ANGEL_TOTP_KEY")
        self.smart_api = None
        self._last_connect_attempt: Optional[datetime] = None
        self._connect_cooldown_sec = int(os.getenv("BROKER_CONNECT_COOLDOWN_SEC", "60"))
        
        if not ANGEL_ONE_AVAILABLE:
            logger.warning("SmartAPI not installed. Install with: pip install smartapi-python")
    
    def _connect(self) -> bool:
        """Connect to Angel One API"""
        if self.connected and self.smart_api:
            return True

        if self._last_connect_attempt:
            elapsed = (datetime.now() - self._last_connect_attempt).total_seconds()
            if elapsed < self._connect_cooldown_sec:
                return False
        
        if not all([self.api_key, self.client_id, self.password, self.totp_key]):
            logger.warning("Angel One credentials not configured")
            return False
        
        if not ANGEL_ONE_AVAILABLE:
            return False
        
        try:
            self._last_connect_attempt = datetime.now()
            import pyotp
            self.smart_api = SmartConnect(api_key=self.api_key)
            totp = pyotp.TOTP(self.totp_key).now()
            session = self.smart_api.generateSession(self.client_id, self.password, totp)
            
            if session.get('status'):
                self.connected = True
                logger.info("Connected to Angel One for market data")
                return True
            else:
                logger.error(f"Angel One connection failed: {session.get('message')}")
                return False
        except Exception as e:
            logger.error(f"Angel One connection error: {e}")
            return False
    
    def _get_token(self, symbol: str) -> Optional[Dict]:
        """Get token info for symbol"""
        # Load token map if not loaded
        if not self.token_map:
            self._load_token_map()
        
        lookup = symbol.upper().replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY")
        
        # Try various formats
        for key in [lookup, f"{lookup}-EQ", f"{lookup}-NSE", f"NSE:{lookup}"]:
            if key in self.token_map:
                return self.token_map[key]
        
        return None
    
    def _load_token_map(self):
        """Load instrument token map"""
        import requests
        import json
        
        token_path = os.path.join(os.path.dirname(__file__), '..', 'broker', 'angel_tokens.json')
        
        try:
            if os.path.exists(token_path):
                with open(token_path, 'r') as f:
                    raw_tokens = json.load(f)
                    self.token_map = {t.get('symbol', ''): t for t in raw_tokens if t.get('symbol')}
        except Exception as e:
            logger.warning(f"Could not load Angel token map: {e}")
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch historical OHLCV data from Angel One"""
        if not self._connect():
            raise DataProviderError("Angel One not connected")
        
        token_info = self._get_token(ticker)
        if not token_info:
            raise DataProviderError(f"Symbol {ticker} not found in Angel One token map")
        
        try:
            # Map interval to Angel One format
            interval_map = {
                "1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE",
                "30m": "THIRTY_MINUTE", "1h": "ONE_HOUR", "1d": "ONE_DAY"
            }
            angel_interval = interval_map.get(interval, "ONE_DAY")
            
            # Calculate date range from period
            end_date = datetime.now()
            period_days = {
                "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
                "1y": 365, "2y": 730
            }
            days = period_days.get(period, 365)
            start_date = end_date - timedelta(days=days)
            
            # Fetch historical data
            historical_data = self.smart_api.getCandleData({
                "exchange": token_info.get('exch_seg', 'NSE'),
                "symboltoken": token_info.get('token'),
                "interval": angel_interval,
                "fromdate": start_date.strftime("%Y-%m-%d %H:%M"),
                "todate": end_date.strftime("%Y-%m-%d %H:%M")
            })
            
            if historical_data.get('status') and historical_data.get('data'):
                df = pd.DataFrame(historical_data['data'])
                
                # Standardize column names
                column_map = {
                    'open': 'Open', 'high': 'High', 'low': 'Low',
                    'close': 'Close', 'volume': 'Volume'
                }
                df.rename(columns=column_map, inplace=True)
                
                # Convert timestamp
                if 'datetime' in df.columns:
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                
                # Ensure numeric columns
                for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            else:
                raise DataProviderError(f"Angel One returned no data: {historical_data.get('message')}")
                
        except Exception as e:
            raise DataProviderError(f"Angel One fetch error: {e}")
    
    async def get_order_book(self, symbol: str) -> Dict:
        """Get Level 2 order book with bid/ask depth"""
        if not self._connect():
            raise DataProviderError("Angel One not connected")
        
        token_info = self._get_token(symbol)
        if not token_info:
            raise DataProviderError(f"Symbol {symbol} not found")
        
        try:
            # Get market depth
            market_depth = self.smart_api.marketData(
                token_info.get('exch_seg', 'NSE'),
                token_info.get('token')
            )
            
            if market_depth.get('status') and market_depth.get('data'):
                data = market_depth['data']
                return {
                    'bid': data.get('bid', []),
                    'ask': data.get('ask', []),
                    'ltp': float(data.get('ltp', 0)),
                    'volume': float(data.get('volume', 0)),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {'bid': [], 'ask': [], 'ltp': 0, 'volume': 0}
                
        except Exception as e:
            logger.error(f"Angel One order book error: {e}")
            return {'bid': [], 'ask': [], 'ltp': 0, 'volume': 0}


class ZerodhaKiteProvider(BrokerDataProvider):
    """
    Zerodha Kite Connect Data Provider
    Provides real-time data with excellent order flow depth
    """
    
    def __init__(self):
        super().__init__()
        self.api_key = config_manager.get_secret("ZERODHA_API_KEY") or config_manager.get_api_key("zerodha")
        self.api_secret = config_manager.get_secret("ZERODHA_API_SECRET")
        self.access_token = config_manager.get_secret("ZERODHA_ACCESS_TOKEN")
        self.kite = None
        self._last_connect_attempt: Optional[datetime] = None
        self._connect_cooldown_sec = int(os.getenv("BROKER_CONNECT_COOLDOWN_SEC", "60"))
        
        if not ZERODHA_AVAILABLE:
            logger.warning("KiteConnect not installed. Install with: pip install kiteconnect")
    
    def _connect(self) -> bool:
        """Connect to Zerodha Kite with session validation"""
        if self.connected and self.kite:
            try:
                self.kite.profile()
                return True
            except:
                self.connected = False

        if self._last_connect_attempt:
            elapsed = (datetime.now() - self._last_connect_attempt).total_seconds()
            if elapsed < self._connect_cooldown_sec:
                return False
        
        if not self.api_key:
            logger.warning("Zerodha API Key not configured")
            return False
            
        if not self.access_token:
            logger.warning("Zerodha Access Token missing. Interactive login required.")
            return False
        
        if not ZERODHA_AVAILABLE:
            return False
        
        try:
            self._last_connect_attempt = datetime.now()
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Test connection
            profile = self.kite.profile()
            if profile:
                self.connected = True
                logger.info("Connected to Zerodha Kite")
                return True
            return False
        except Exception as e:
            logger.error(f"Zerodha connection error: {e}. Token may be expired.")
            self.connected = False
            return False
    
    def _get_instrument_token(self, symbol: str) -> Optional[str]:
        """Get instrument token for symbol"""
        if not self.kite:
            return None
        
        try:
            # Map common symbols
            symbol_map = {
                "^NSEI": "NSE:NIFTY 50",
                "^NSEBANK": "NSE:NIFTY BANK",
                "^BSESN": "BSE:SENSEX"
            }
            
            kite_symbol = symbol_map.get(symbol, f"NSE:{symbol.replace('^', '')}")
            
            # Get instruments list
            instruments = self.kite.instruments("NSE")
            for inst in instruments:
                if inst['tradingsymbol'] == symbol.replace('^', '') or \
                   inst['name'] == symbol.replace('^', ''):
                    return f"NSE:{inst['instrument_token']}"
            
            return kite_symbol
        except Exception as e:
            logger.error(f"Zerodha token lookup error: {e}")
            return None
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch historical OHLCV data from Zerodha"""
        if not self._connect():
            raise DataProviderError("Zerodha not connected")
        
        instrument_token = self._get_instrument_token(ticker)
        if not instrument_token:
            raise DataProviderError(f"Symbol {ticker} not found")
        
        try:
            # Map interval to Kite format
            interval_map = {
                "1m": "minute", "5m": "5minute", "15m": "15minute",
                "30m": "30minute", "1h": "60minute", "1d": "day"
            }
            kite_interval = interval_map.get(interval, "day")
            
            # Calculate date range
            end_date = datetime.now()
            period_days = {
                "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
                "1y": 365, "2y": 730
            }
            days = period_days.get(period, 365)
            start_date = end_date - timedelta(days=days)
            
            # Fetch historical data
            historical_data = self.kite.historical_data(
                instrument_token,
                start_date,
                end_date,
                kite_interval
            )
            
            if historical_data:
                df = pd.DataFrame(historical_data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                # Standardize column names
                column_map = {
                    'open': 'Open', 'high': 'High', 'low': 'Low',
                    'close': 'Close', 'volume': 'Volume'
                }
                df.rename(columns=column_map, inplace=True)
                
                return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            else:
                raise DataProviderError("Zerodha returned no data")
                
        except Exception as e:
            raise DataProviderError(f"Zerodha fetch error: {e}")
    
    async def get_order_book(self, symbol: str) -> Dict:
        """Get Level 2 order book with bid/ask depth"""
        if not self._connect():
            raise DataProviderError("Zerodha not connected")
        
        instrument_token = self._get_instrument_token(symbol)
        if not instrument_token:
            raise DataProviderError(f"Symbol {symbol} not found")
        
        try:
            # Get market depth (Level 2 data)
            quote = self.kite.quote([instrument_token])
            
            if instrument_token in quote:
                depth = quote[instrument_token].get('depth', {})
                return {
                    'bid': depth.get('buy', []),
                    'ask': depth.get('sell', []),
                    'ltp': float(quote[instrument_token].get('last_price', 0)),
                    'volume': float(quote[instrument_token].get('volume', 0)),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {'bid': [], 'ask': [], 'ltp': 0, 'volume': 0}
                
        except Exception as e:
            logger.error(f"Zerodha order book error: {e}")
            return {'bid': [], 'ask': [], 'ltp': 0, 'volume': 0}
    
    async def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> pd.DataFrame:
        """Get option chain data"""
        if not self._connect():
            raise DataProviderError("Zerodha not connected")
        
        try:
            # Get instruments for options
            instruments = self.kite.instruments("NFO")
            
            # Filter for options of the symbol
            base_symbol = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY")
            option_instruments = [
                inst for inst in instruments
                if inst['name'] == base_symbol and inst['instrument_type'] in ['CE', 'PE']
            ]
            
            if option_instruments:
                df = pd.DataFrame(option_instruments)
                return df
            else:
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Zerodha option chain error: {e}")
            return pd.DataFrame()


class GrowwDataProvider(BrokerDataProvider):
    """
    Groww Data Provider
    Note: Groww doesn't have a public API yet, so this is a placeholder
    that can be extended when API becomes available
    """
    
    def __init__(self):
        super().__init__()
        logger.warning("Groww API not publicly available yet. This provider is a placeholder.")
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Placeholder - Groww API not available"""
        raise DataProviderError("Groww API is not publicly available yet. Integration is pending official SDK release.")
    
    async def get_order_book(self, symbol: str) -> Dict:
        """Placeholder"""
        raise DataProviderError("Groww Order Depth is currently unavailable (Waiting for official API).")
