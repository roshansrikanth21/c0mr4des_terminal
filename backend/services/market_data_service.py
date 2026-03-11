"""
Async market data service with provider fallbacks and caching.
Handles data fetching from multiple sources with proper error handling.
"""

import asyncio
import aiohttp
import yfinance as yf
import pandas as pd
import numpy as np
import os
from typing import Dict, Any, Optional, List, Set
import time
from datetime import datetime, timedelta

from backend.config.secure_config import config_manager
from backend.exceptions import DataProviderError, InsufficientDataError

# Backwards-compatible alias for legacy tests/patches.
yfinance = yf

# Import broker providers (optional - will fail gracefully if not configured)
try:
    from backend.services.broker_data_providers import (
        AngelOneDataProvider, ZerodhaKiteProvider, GrowwDataProvider, TrueDataProvider,
        ANGEL_ONE_AVAILABLE, ZERODHA_AVAILABLE
    )
    BROKER_PROVIDERS_AVAILABLE = True
except ImportError:
    BROKER_PROVIDERS_AVAILABLE = False
    AngelOneDataProvider = None
    ZerodhaKiteProvider = None
    GrowwDataProvider = None
    TrueDataProvider = None
    ANGEL_ONE_AVAILABLE = False
    ZERODHA_AVAILABLE = False

class AsyncMarketDataService:
    """Async service for fetching market data with provider fallbacks"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.cache_max_entries = int(os.getenv("MARKET_CACHE_MAX_ENTRIES", "128"))
        self._inflight_requests: Dict[str, asyncio.Task] = {}
        # Keep provider attempts bounded so API calls do not hang.
        self.provider_timeout = float(os.getenv("MARKET_PROVIDER_TIMEOUT_SEC", "2.5"))
        self.fast_provider_timeout = float(os.getenv("MARKET_FAST_PROVIDER_TIMEOUT_SEC", "1.2"))
        self.order_book_timeout = float(os.getenv("ORDER_BOOK_TIMEOUT_SEC", "1.5"))
        self.option_chain_timeout = float(os.getenv("OPTION_CHAIN_TIMEOUT_SEC", "2.5"))
        self.provider_cooldown_sec = int(os.getenv("MARKET_PROVIDER_COOLDOWN_SEC", "90"))
        self.provider_fail_threshold = int(os.getenv("MARKET_PROVIDER_FAIL_THRESHOLD", "3"))
        self._provider_failure_state: Dict[str, Dict[str, float]] = {}
        
        # Build provider list: broker providers first (for Indian markets), then fallbacks
        self.providers = []
        
        # Add broker providers if available and configured
        if BROKER_PROVIDERS_AVAILABLE:
            # TrueData (Professional primary feed)
            allow_disconnected_truedata = os.getenv("TRUEDATA_ALLOW_DISCONNECTED", "0").strip().lower() in {"1", "true", "yes"}
            try:
                true_provider = TrueDataProvider()
                if true_provider.username and true_provider.password:
                    if getattr(true_provider, "connected", False):
                        self.providers.append(true_provider)
                        print("[OK] TrueData data provider enabled (Primary Feed)")
                    elif allow_disconnected_truedata:
                        self.providers.append(true_provider)
                        print("[WARN] TrueData connectivity test failed; provider enabled via TRUEDATA_ALLOW_DISCONNECTED.")
                    else:
                        print("[WARN] TrueData credentials detected, but connectivity test failed. Skipping provider for stability.")
                else:
                    print("[INFO] TrueData credentials incomplete, skipping provider")
            except Exception as e:
                print(f"[WARNING] TrueData provider not configured: {e}")

            # Angel One (preferred for Indian markets if configured)
            try:
                angel_provider = AngelOneDataProvider()
                if (
                    ANGEL_ONE_AVAILABLE
                    and angel_provider.api_key
                    and angel_provider.client_id
                    and angel_provider.password
                    and angel_provider.totp_key
                ):
                    self.providers.append(angel_provider)
                    print("[OK] Angel One data provider enabled")
                else:
                    print("[INFO] Angel One provider skipped (missing credentials or SmartAPI dependency)")
            except Exception as e:
                print(f"[WARNING] Angel One provider not configured: {e}")
            
            # Zerodha Kite (preferred for Indian markets if configured)
            try:
                zerodha_provider = ZerodhaKiteProvider()
                if ZERODHA_AVAILABLE and zerodha_provider.api_key and zerodha_provider.access_token:
                    self.providers.append(zerodha_provider)
                    print("[OK] Zerodha Kite data provider enabled")
                else:
                    print("[INFO] Zerodha provider skipped (missing credentials or Kite dependency)")
            except Exception as e:
                print(f"[WARNING] Zerodha provider not configured: {e}")
        
        # Fallback providers (always available)
        self.providers.extend([
            YahooFinanceProvider(),
            AlphaVantageProvider(),  # Backup provider
            SyntheticDataProvider()   # Last resort
        ])
    
    async def get_market_data(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get market data with provider fallbacks and caching.
        
        Args:
            ticker: Stock ticker symbol
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            
        Returns:
            pandas DataFrame with OHLCV data
        """
        period = normalize_period_for_interval(period, interval)

        # Check cache first
        cache_key = f"{ticker}_{period}_{interval}"
        self._prune_cache()
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['data']

        # De-duplicate concurrent requests for identical keys to reduce provider load.
        if cache_key in self._inflight_requests:
            return await self._inflight_requests[cache_key]

        task = asyncio.create_task(self._fetch_from_providers(ticker, period, interval, cache_key))
        self._inflight_requests[cache_key] = task
        try:
            return await task
        finally:
            self._inflight_requests.pop(cache_key, None)

    async def _fetch_from_providers(self, ticker: str, period: str, interval: str, cache_key: str) -> pd.DataFrame:
        """Internal provider fallback loop."""
        errors: List[str] = []

        candidates = [p for p in self.providers if not self._is_provider_cooled_down(p)]
        if not candidates:
            # Reset cooldown state if everything is cooled down.
            self._provider_failure_state.clear()
            candidates = list(self.providers)

        priorities = sorted({self._provider_priority(p) for p in candidates})

        for priority in priorities:
            tier = [p for p in candidates if self._provider_priority(p) == priority]
            if not tier:
                continue

            tasks: Dict[asyncio.Task, Any] = {}
            pending: Set[asyncio.Task] = set()

            for provider in tier:
                timeout_sec = self._provider_timeout_for(provider)

                async def _run_fetch(p=provider, timeout=timeout_sec):
                    return await asyncio.wait_for(
                        p.fetch_data(ticker, period, interval),
                        timeout=timeout,
                    )

                task = asyncio.create_task(_run_fetch())
                tasks[task] = provider
                pending.add(task)
                print(
                    f"Trying provider: {provider.__class__.__name__} "
                    f"(priority={priority}, timeout={timeout_sec:.1f}s)"
                )

            try:
                while pending:
                    done, pending = await asyncio.wait(
                        pending,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in done:
                        provider = tasks[task]
                        provider_name = provider.__class__.__name__
                        try:
                            data = task.result()
                            if self._validate_data(data):
                                self._mark_provider_success(provider)
                                self.cache[cache_key] = {
                                    'data': data,
                                    'timestamp': time.time()
                                }
                                for ptask in pending:
                                    ptask.cancel()
                                if pending:
                                    asyncio.create_task(self._cleanup_pending_tasks(pending))
                                return data

                            self._mark_provider_failure(provider)
                            msg = f"{provider_name} returned invalid data"
                            errors.append(msg)
                            print(msg)
                        except Exception as e:
                            self._mark_provider_failure(provider)
                            msg = f"{provider_name} failed: {e}"
                            errors.append(msg)
                            print(msg)
            finally:
                if pending:
                    for ptask in pending:
                        ptask.cancel()
                    asyncio.create_task(self._cleanup_pending_tasks(pending))

        tail_errors = "; ".join(errors[-5:]) if errors else "No providers available."
        raise DataProviderError(f"All data providers failed for {ticker}. {tail_errors}")
    
    async def get_order_book(self, ticker: str) -> Dict:
        """
        Get Level 2 order book data from broker providers
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with bid/ask depth, LTP, volume
        """
        # Try broker providers first (they have order book data)
        for provider in self.providers:
            if hasattr(provider, 'get_order_book'):
                try:
                    order_book = await asyncio.wait_for(
                        provider.get_order_book(ticker),
                        timeout=self.order_book_timeout
                    )
                    if order_book and order_book.get('bid') and order_book.get('ask'):
                        return order_book
                except Exception as e:
                    print(f"Order book fetch failed from {provider.__class__.__name__}: {e}")
                    continue
        
        # Fallback: return empty order book
        return {'bid': [], 'ask': [], 'ltp': 0, 'volume': 0, 'timestamp': datetime.now().isoformat()}
    
    async def get_option_chain(self, ticker: str, expiry: Optional[str] = None) -> pd.DataFrame:
        """
        Get option chain data from broker providers
        
        Args:
            ticker: Underlying symbol (e.g., "^NSEI" for Nifty)
            expiry: Optional expiry date (YYYY-MM-DD format)
            
        Returns:
            DataFrame with option chain data
        """
        # Try broker providers first
        for provider in self.providers:
            if hasattr(provider, 'get_option_chain'):
                try:
                    chain = await asyncio.wait_for(
                        provider.get_option_chain(ticker, expiry),
                        timeout=self.option_chain_timeout
                    )
                    if not chain.empty:
                        return chain
                except Exception as e:
                    print(f"Option chain fetch failed from {provider.__class__.__name__}: {e}")
                    continue
        
        # Fallback: return empty DataFrame
        return pd.DataFrame()

    def get_provider_status(self) -> List[Dict[str, Any]]:
        """Return sanitized provider configuration/connection status."""
        providers = []
        for provider in self.providers:
            info: Dict[str, Any] = {"provider": provider.__class__.__name__}
            for attr in ("api_key", "client_id", "password", "totp_key", "access_token", "username"):
                if hasattr(provider, attr):
                    info[f"has_{attr}"] = bool(getattr(provider, attr))
            if hasattr(provider, "connected"):
                info["connected"] = bool(getattr(provider, "connected"))
            info["priority"] = self._provider_priority(provider)
            info["cooled_down"] = self._is_provider_cooled_down(provider)
            fail_state = self._provider_failure_state.get(self._provider_key(provider), {})
            info["recent_failures"] = int(fail_state.get("failures", 0.0) or 0)
            info["cooldown_until"] = fail_state.get("cooldown_until")
            score = 1.0
            if info.get("cooled_down"):
                score -= 0.45
            score -= min(float(info["priority"]) * 0.12, 0.36)
            if "connected" in info and not info.get("connected", False):
                score -= 0.12
            score -= min(float(info.get("recent_failures", 0)) * 0.08, 0.24)
            info["route_score"] = round(float(np.clip(score, 0.0, 1.0)), 4)
            providers.append(info)
        return providers
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self.cache:
            return False
        
        cache_time = self.cache[cache_key]['timestamp']
        return (time.time() - cache_time) < self.cache_ttl

    def _prune_cache(self) -> None:
        if not self.cache:
            return

        now = time.time()
        expired = [
            key
            for key, value in self.cache.items()
            if (now - float(value.get("timestamp", 0.0) or 0.0)) >= self.cache_ttl
        ]
        for key in expired:
            self.cache.pop(key, None)

        if len(self.cache) <= self.cache_max_entries:
            return

        ordered = sorted(
            self.cache.items(),
            key=lambda item: float((item[1] or {}).get("timestamp", 0.0) or 0.0),
        )
        for key, _ in ordered[: max(0, len(self.cache) - self.cache_max_entries)]:
            self.cache.pop(key, None)

    async def _cleanup_pending_tasks(self, tasks: Set[asyncio.Task]) -> None:
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)

    def _provider_key(self, provider) -> str:
        return provider.__class__.__name__

    def _provider_priority(self, provider) -> int:
        name = self._provider_key(provider)
        if name in {"TrueDataProvider", "AngelOneDataProvider", "ZerodhaKiteProvider", "GrowwDataProvider"}:
            return 0
        if name == "YahooFinanceProvider":
            return 1
        if name == "AlphaVantageProvider":
            return 2
        return 3

    def _provider_timeout_for(self, provider) -> float:
        if self._provider_priority(provider) == 0:
            return self.fast_provider_timeout
        return self.provider_timeout

    def _is_provider_cooled_down(self, provider) -> bool:
        state = self._provider_failure_state.get(self._provider_key(provider), {})
        return state.get("cooldown_until", 0.0) > time.time()

    def _mark_provider_success(self, provider) -> None:
        self._provider_failure_state.pop(self._provider_key(provider), None)

    def _mark_provider_failure(self, provider) -> None:
        key = self._provider_key(provider)
        state = self._provider_failure_state.get(
            key,
            {"failures": 0.0, "cooldown_until": 0.0},
        )
        state["failures"] = float(state.get("failures", 0.0)) + 1.0
        if state["failures"] >= float(self.provider_fail_threshold):
            state["cooldown_until"] = time.time() + float(self.provider_cooldown_sec)
            state["failures"] = 0.0
        self._provider_failure_state[key] = state
    
    def _validate_data(self, data: pd.DataFrame) -> bool:
        """Validate that data is usable"""
        if data is None or data.empty:
            return False
        
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in data.columns for col in required_columns):
            return False
        
        # Check for reasonable data ranges
        if (data['High'] < data['Low']).any():
            return False
        
        if (data['Close'] <= 0).any():
            return False
        
        return len(data) >= 10  # Minimum data points


def get_sync_market_data(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Convenience wrapper to use AsyncMarketDataService from synchronous code.
    
    This is intended for CLI scripts and background jobs. It first tries to
    call the async service via asyncio.run (which also gives you provider
    fallbacks and caching). If an event loop is already running (e.g. inside
    an async web handler), asyncio.run() will raise RuntimeError; in that
    case we fall back to a direct yfinance download with the same
    normalization logic as YahooFinanceProvider.
    """
    try:
        period = normalize_period_for_interval(period, interval)

        def _safe_yf_download():
            try:
                data = yf.download(
                    ticker,
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=True
                )
                return data
            except Exception as e:
                print(f"[YFINANCE ERROR] Critical failure downloading {ticker}: {e}")
                return pd.DataFrame()

        # Try async first
        try:
            return asyncio.run(async_market_data_service.get_market_data(ticker, period, interval))
        except RuntimeError:
            # Fallback to safe sync download if loop running
            data = _safe_yf_download()
            if data.empty:
                return pd.DataFrame()
            
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            data.columns = [col.capitalize() for col in data.columns]
            if 'Adj close' in data.columns:
                data['Close'] = data['Adj close']
            return data.ffill().bfill()
    except Exception as e:
        print(f"[ERROR] Market data sync fetch failed for {ticker}: {e}")
        return pd.DataFrame()

class YahooFinanceProvider:
    """Yahoo Finance data provider with async wrapper"""
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch data from Yahoo Finance"""
        
        # Run yfinance in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def _fetch_sync():
            return yf.download(
                ticker, 
                period=period, 
                interval=interval, 
                progress=False,
                auto_adjust=True
            )
        
        try:
            data = await loop.run_in_executor(None, _fetch_sync)
            
            if data is None or data.empty:
                raise InsufficientDataError(f"No data returned from Yahoo Finance for {ticker}")
            
            # Normalize columns if MultiIndex
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            # Standardize column names
            data.columns = [col.capitalize() for col in data.columns]
            
            # Handle Adj Close if present
            if 'Adj close' in data.columns:
                data['Close'] = data['Adj close']
            
            # Forward fill and backward fill missing data
            data = data.ffill().bfill()
            
            return data
            
        except Exception as e:
            raise DataProviderError(f"Yahoo Finance provider failed: {e}")

class AlphaVantageProvider:
    """Alpha Vantage backup data provider (API key required)"""
    
    def __init__(self):
        self.api_key = config_manager.get_api_key("alpha_vantage")
        self.base_url = "https://www.alphavantage.co/query"
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch data from Alpha Vantage"""
        
        if not self.api_key:
            raise DataProviderError("Alpha Vantage API key not configured")
        
        # Map intervals to Alpha Vantage function names
        function_map = {
            '1m': 'TIME_SERIES_INTRADAY',
            '5m': 'TIME_SERIES_INTRADAY',
            '15m': 'TIME_SERIES_INTRADAY',
            '30m': 'TIME_SERIES_INTRADAY',
            '60m': 'TIME_SERIES_INTRADAY',
            '1d': 'TIME_SERIES_DAILY',
            '5d': 'TIME_SERIES_DAILY',
            '1wk': 'TIME_SERIES_WEEKLY',
            '1mo': 'TIME_SERIES_MONTHLY'
        }
        
        function = function_map.get(interval, 'TIME_SERIES_DAILY')
        
        params = {
            'function': function,
            'symbol': ticker,
            'apikey': self.api_key,
            'outputsize': 'full'
        }
        
        if interval in ['1m', '5m', '15m', '30m', '60m']:
            params['interval'] = interval
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        raise DataProviderError(f"Alpha Vantage HTTP error: {response.status}")
                    
                    data = await response.json()
                    
                    # Parse Alpha Vantage response format
                    if function == 'TIME_SERIES_INTRADAY':
                        time_key = f"Time Series ({interval})"
                    elif function == 'TIME_SERIES_DAILY':
                        time_key = "Time Series (Daily)"
                    elif function == 'TIME_SERIES_WEEKLY':
                        time_key = "Weekly Time Series"
                    else:
                        time_key = "Monthly Time Series"
                    
                    if time_key not in data:
                        raise DataProviderError(f"Invalid Alpha Vantage response format")
                    
                    # Convert to DataFrame
                    ts_data = data[time_key]
                    df = pd.DataFrame.from_dict(ts_data, orient='index')
                    df.index = pd.to_datetime(df.index)
                    
                    # Rename columns to standard format
                    column_map = {
                        '1. open': 'Open',
                        '2. high': 'High', 
                        '3. low': 'Low',
                        '4. close': 'Close',
                        '5. volume': 'Volume'
                    }
                    df = df.rename(columns=column_map)
                    
                    # Convert to numeric
                    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    # Sort by date (newest first, reverse to oldest)
                    df = df.sort_index()
                    
                    return df
                    
            except aiohttp.ClientError as e:
                raise DataProviderError(f"Alpha Vantage network error: {e}")

class SyntheticDataProvider:
    """Last resort synthetic data provider for testing"""
    
    async def fetch_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Generate synthetic data for testing purposes"""
        print("WARNING: Using synthetic data provider - this is for testing only!")
        
        # Determine number of data points to generate
        interval_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30, '60m': 60,
            '1d': 1440, '5d': 7200, '1wk': 10080, '1mo': 43200
        }
        
        minutes = interval_minutes.get(interval, 1440)
        
        # Determine date range
        period_days = {
            '1d': 1, '5d': 5, '1mo': 30, '3mo': 90, '6mo': 180,
            '1y': 365, '2y': 730, '5y': 1825, '10y': 3650
        }
        
        days = period_days.get(period, 365)
        num_points = max(100, (days * 24 * 60) // minutes)
        
        # Generate synthetic price data
        np.random.seed(42)  # For reproducibility
        
        dates = pd.date_range(
            end=datetime.now(),
            periods=num_points,
            freq=f"{minutes}min"
        )
        
        # Random walk with trend
        base_price = 100.0
        returns = np.random.normal(0.0001, 0.02, num_points)  # Small positive drift
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Generate OHLC from close prices
        high = prices * (1 + np.abs(np.random.normal(0, 0.01, num_points)))
        low = prices * (1 - np.abs(np.random.normal(0, 0.01, num_points)))
        open_price = np.roll(prices, 1)
        open_price[0] = base_price
        
        volume = np.random.randint(1000000, 10000000, num_points)
        
        df = pd.DataFrame({
            'Open': open_price,
            'High': high,
            'Low': low,
            'Close': prices,
            'Volume': volume
        }, index=dates)
        
        return df

# Global service instance
async_market_data_service = AsyncMarketDataService()


def normalize_period_for_interval(period: str, interval: str) -> str:
    interval = str(interval or "1d").lower()
    period = str(period or "1y")
    intraday_caps = {
        "1m": "7d",
        "2m": "60d",
        "5m": "60d",
        "15m": "60d",
        "30m": "60d",
        "60m": "730d",
        "90m": "60d",
        "1h": "730d",
    }
    max_period = intraday_caps.get(interval)
    if not max_period:
        return period

    order = {
        "1d": 1,
        "5d": 5,
        "7d": 7,
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
        "10y": 3650,
        "ytd": 365,
        "max": 99999,
    }
    requested_days = order.get(period, 365)
    max_days = order.get(max_period, requested_days)
    return max_period if requested_days > max_days else period
