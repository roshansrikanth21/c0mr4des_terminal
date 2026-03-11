import asyncio
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import time
from backend.services.market_data_service import get_sync_market_data

class AlphaScanner:
    """
    Proactive discovery engine for high-probability trade setups.
    Scans a curated list of high-profit/high-volatility tickers.
    Uses background caching to ensure instant UI responses.
    """
    
    CURATED_TICKERS = {
        "IN": ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS", "HINDUNILVR.NS", "ADANIENT.NS", "BAJFINANCE.NS", "TITAN.NS", "LT.NS"],
        "US": ["NVDA", "TSLA", "AAPL", "MSFT", "AMD", "META", "AMZN", "GOOGL", "NFLX", "AVGO"],
        "CRYPTO": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD"],
        "FX": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"]
    }

    _cache = {"results": [], "last_updated": 0}
    _scanning = False

    def __init__(self):
        self.last_scan_time = 0

    async def scan_ticker(self, ticker: str, region: str) -> Optional[Dict]:
        """Analyzes a single ticker and returns a score/signal."""
        try:
            from backend.services.market_data_service import get_sync_market_data
            # Use a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, get_sync_market_data, ticker, "1y", "1d")
            
            if df is None or df.empty:
                return None

            if 'Close' not in df.columns:
                df.columns = [c.capitalize() for c in df.columns]
            
            close = df['Close'].dropna()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
                
            if len(close) < 50:
                return None
            
            # Trend Analysis (EMA 20/50/200)
            close_values = close.values
            ema20_all = close.ewm(span=20, adjust=False).mean().values
            ema50_all = close.ewm(span=50, adjust=False).mean().values
            ema200_all = close.ewm(span=200, adjust=False).mean().values
            
            curr_price = float(close_values[-1])
            ema20 = float(ema20_all[-1])
            ema50 = float(ema50_all[-1])
            ema200 = float(ema200_all[-1])

            trend_score = 0
            if curr_price > ema200: trend_score += 30
            if ema20 > ema50: trend_score += 20
            if curr_price > ema20: trend_score += 10

            # Momentum (RSI)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            rsi = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50
            
            momentum_score = 0
            if 40 < rsi < 60: momentum_score = 10 # Consolidation
            elif 60 < rsi < 70: momentum_score = 30 # Bullish strength
            elif rsi > 70: momentum_score = 10 # Overbought
            elif 30 < rsi < 40: momentum_score = 30 # Bearish strength
            elif rsi < 30: momentum_score = 10 # Oversold

            # Decision
            signal = "WAIT"
            total_score = trend_score + momentum_score
            
            if total_score >= 50:
                signal = "BUY" if curr_price > ema200 else "RECOVERY"
            elif total_score <= 20:
                signal = "SELL" if curr_price < ema200 else "PULLBACK"

            return {
                "ticker": ticker,
                "name": ticker.split('.')[0].replace('^', ''),
                "region": region,
                "price": round(curr_price, 2),
                "signal": signal,
                "score": total_score,
                "rsi": round(rsi, 1),
                "trend": "BULLISH" if curr_price > ema200 else "BEARISH",
                "timestamp": time.time()
            }
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")
            return None

    async def discover_alpha(self, region_filter: str = None) -> List[Dict]:
        """Returns top opportunities (instant response from cache)."""
        # If cache is old (e.g., > 10 mins) or empty, trigger a background scan
        current_time = time.time()
        if (current_time - self._cache["last_updated"] > 600) and not self._scanning:
            asyncio.create_task(self._run_background_scan())

        results = self._cache["results"]
        if region_filter:
            results = [r for r in results if r['region'] == region_filter]
            
        return results[:10]

    async def _run_background_scan(self):
        """Internal method to update the cache without blocking the UI."""
        if self._scanning: return
        
        AlphaScanner._scanning = True
        print("🚀 AlphaScanner: Starting background market discovery...")
        
        tickers_to_scan = []
        for reg, t_list in self.CURATED_TICKERS.items():
            for t in t_list:
                tickers_to_scan.append((t, reg))

        tasks = [self.scan_ticker(t, r) for t, r in tickers_to_scan]
        raw_results = await asyncio.gather(*tasks)
        
        results = [r for r in raw_results if r is not None]
        results.sort(key=lambda x: x['score'], reverse=True)
        
        AlphaScanner._cache = {
            "results": results,
            "last_updated": time.time()
        }
        AlphaScanner._scanning = False
        print(f"✅ AlphaScanner: Background scan complete. {len(results)} opportunities found.")

if __name__ == "__main__":
    # For testing standalone
    async def main():
        scanner = AlphaScanner()
        print("Scanning for Alpha...")
        picks = await scanner.discover_alpha()
        for p in picks:
            print(f"[{p['signal']}] {p['ticker']} - Score: {p['score']} - Price: {p['price']}")
            
    asyncio.run(main())
