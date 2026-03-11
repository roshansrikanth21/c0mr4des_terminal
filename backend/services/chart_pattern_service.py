from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backend.ict_smart_money import ICTSmartMoney
from backend.market_data import calculate_atr
from backend.services.market_data_service import get_sync_market_data


class ChartPatternService:
    """
    Deterministic market-structure analyzer used to enrich chart-LLM output with
    live OHLC-based signals.
    """

    @staticmethod
    def _normalize_interval(timeframe: str | None) -> str:
        raw = str(timeframe or "15m").strip().lower()
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "60m": "1h",
            "4h": "1h",
            "1d": "1d",
            "d": "1d",
            "daily": "1d",
        }
        return mapping.get(raw, "15m")

    @staticmethod
    def _period_for_interval(interval: str) -> str:
        if interval in {"1m", "5m", "15m"}:
            return "30d"
        if interval in {"30m", "1h"}:
            return "90d"
        return "1y"

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        local = df.copy()
        if isinstance(local.columns, pd.MultiIndex):
            local.columns = local.columns.get_level_values(0)
        local.columns = [str(c).capitalize() for c in local.columns]
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in local.columns:
                return pd.DataFrame()
            local[col] = pd.to_numeric(local[col], errors="coerce")
        return local.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()

    def analyze(self, ticker: str, timeframe: str | None = "15m") -> Dict[str, Any]:
        interval = self._normalize_interval(timeframe)
        period = self._period_for_interval(interval)
        df = self._normalize_df(get_sync_market_data(ticker=ticker, period=period, interval=interval))
        if df.empty or len(df) < 50:
            return {"status": "error", "message": f"No deterministic chart context available for {ticker}"}

        if len(df) > 240:
            df = df.iloc[-240:].copy()

        ict = ICTSmartMoney(df)
        atr = calculate_atr(df["High"], df["Low"], df["Close"], 14).bfill().ffill()
        price = float(df["Close"].iloc[-1])
        atr_val = float(atr.iloc[-1]) if len(atr) else max(price * 0.01, 1e-6)

        patterns: List[str] = []
        notes: List[str] = []
        bias_score = 0.0

        latest_fvg = (ict.detect_fair_value_gaps() or [])[-3:]
        latest_ifvg = (ict.detect_inverse_fair_value_gaps() or [])[-3:]
        latest_obs = (ict.detect_order_blocks() or [])[-3:]
        latest_sweeps = (ict.detect_liquidity_sweeps() or [])[-2:]

        for item in latest_fvg:
            if str(item.get("type")) == "bullish":
                patterns.append("Bullish FVG")
                bias_score += 0.18
            else:
                patterns.append("Bearish FVG")
                bias_score -= 0.18

        for item in latest_ifvg:
            if "bullish" in str(item.get("type", "")).lower():
                patterns.append("Bullish IFVG")
                bias_score += 0.22
            else:
                patterns.append("Bearish IFVG")
                bias_score -= 0.22

        for item in latest_obs:
            if "bullish" in str(item.get("type", "")).lower():
                patterns.append("Bullish Order Block")
                bias_score += 0.12
            else:
                patterns.append("Bearish Order Block")
                bias_score -= 0.12

        for item in latest_sweeps:
            if "bullish" in str(item.get("type", "")).lower():
                patterns.append("Bullish Liquidity Sweep")
                bias_score += 0.16
            else:
                patterns.append("Bearish Liquidity Sweep")
                bias_score -= 0.16

        rolling_high = float(df["High"].rolling(20).max().iloc[-2])
        rolling_low = float(df["Low"].rolling(20).min().iloc[-2])
        if price > rolling_high:
            patterns.append("Bullish Breakout")
            notes.append("Price is trading above the recent 20-bar range high.")
            bias_score += 0.20
        elif price < rolling_low:
            patterns.append("Bearish Breakdown")
            notes.append("Price is trading below the recent 20-bar range low.")
            bias_score -= 0.20

        mean20 = float(df["Close"].rolling(20).mean().iloc[-1])
        if np.isfinite(mean20) and mean20 > 0:
            stretch = (price - mean20) / mean20
            if stretch > 0.015:
                notes.append("Price is extended above its 20-bar mean; chase risk is elevated.")
            elif stretch < -0.015:
                notes.append("Price is extended below its 20-bar mean; snapback risk is elevated.")

        unique_patterns: List[str] = []
        for item in patterns:
            if item not in unique_patterns:
                unique_patterns.append(item)

        if bias_score > 0.18:
            action = "BUY CALL"
            sentiment = "Bullish"
        elif bias_score < -0.18:
            action = "BUY PUT"
            sentiment = "Bearish"
        else:
            action = "WAIT"
            sentiment = "Neutral"

        confidence = float(np.clip(0.42 + abs(bias_score), 0.0, 0.9))
        return {
            "status": "success",
            "ticker": ticker,
            "interval": interval,
            "patterns": unique_patterns or ["No clear structure"],
            "sentiment": sentiment,
            "action_type": action,
            "confidence": round(confidence, 4),
            "entry_zone": f"{price - 0.35 * atr_val:.2f}-{price + 0.15 * atr_val:.2f}",
            "target": round(price + (1.8 * atr_val if action == 'BUY CALL' else (-1.8 * atr_val if action == 'BUY PUT' else 0.8 * atr_val)), 2),
            "stop_loss": round(price - (1.1 * atr_val if action == 'BUY CALL' else (-1.1 * atr_val if action == 'BUY PUT' else 0.8 * atr_val)), 2),
            "analysis": " ".join(notes) if notes else "Deterministic structure scan completed.",
            "bias_score": round(float(bias_score), 4),
        }


chart_pattern_service = ChartPatternService()
