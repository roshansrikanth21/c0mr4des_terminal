"""
Persistent historical dataset service for backtesting and ML training.
Stores normalized OHLCV data per ticker/interval under data/historical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import logging

import numpy as np
import pandas as pd

from backend.services.market_data_service import get_sync_market_data

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class HistoricalDataService:
    def __init__(self, data_dir: Optional[Path] = None):
        repo_root = Path(__file__).resolve().parents[2]
        self.data_dir = data_dir or (repo_root / "data" / "historical")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_ticker(ticker: str) -> str:
        safe = (ticker or "").strip().replace("^", "IDX_").replace(":", "_")
        safe = safe.replace("/", "_").replace("\\", "_")
        return "".join(ch if (ch.isalnum() or ch in {"_", "-", "."}) else "_" for ch in safe)

    @staticmethod
    def _expected_delta(interval: str) -> Optional[pd.Timedelta]:
        mapping = {
            "1m": pd.Timedelta(minutes=1),
            "2m": pd.Timedelta(minutes=2),
            "5m": pd.Timedelta(minutes=5),
            "15m": pd.Timedelta(minutes=15),
            "30m": pd.Timedelta(minutes=30),
            "60m": pd.Timedelta(minutes=60),
            "90m": pd.Timedelta(minutes=90),
            "1h": pd.Timedelta(hours=1),
            "1d": pd.Timedelta(days=1),
            "1wk": pd.Timedelta(days=7),
            "1mo": pd.Timedelta(days=30),
        }
        return mapping.get(interval)

    def _dataset_path(self, ticker: str, interval: str) -> Path:
        return self.data_dir / f"{self._sanitize_ticker(ticker)}__{interval}.csv"

    @staticmethod
    def _align_index_to_interval(df: pd.DataFrame, interval: str) -> pd.DataFrame:
        if df.empty:
            return df

        local = df.copy()
        if interval == "1d":
            local.index = local.index.normalize()
        elif interval == "1wk":
            base = local.index.normalize()
            local.index = base - pd.to_timedelta(base.dayofweek, unit="D")
        elif interval == "1mo":
            # Month start bucket.
            if local.index.tz is None:
                local.index = local.index.to_period("M").to_timestamp()
            else:
                tz = local.index.tz
                local.index = local.index.tz_localize(None).to_period("M").to_timestamp().tz_localize(tz)
        return local

    def _normalize_dataframe(self, df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)

        local = df.copy()

        if isinstance(local.columns, pd.MultiIndex):
            local.columns = local.columns.get_level_values(0)
        local.columns = [str(col).strip().capitalize() for col in local.columns]
        if "Adj close" in local.columns and "Close" not in local.columns:
            local["Close"] = local["Adj close"]

        if "Date" in local.columns and not isinstance(local.index, pd.DatetimeIndex):
            local["Date"] = pd.to_datetime(local["Date"], errors="coerce", utc=True)
            local = local.set_index("Date")
        elif not isinstance(local.index, pd.DatetimeIndex):
            local.index = pd.to_datetime(local.index, errors="coerce", utc=True)
        elif local.index.tz is None:
            local.index = local.index.tz_localize("UTC")
        else:
            local.index = local.index.tz_convert("UTC")

        local = local[~local.index.isna()]

        for col in REQUIRED_COLUMNS:
            if col not in local.columns:
                local[col] = np.nan
            local[col] = pd.to_numeric(local[col], errors="coerce")

        local = local[REQUIRED_COLUMNS]
        local = local.sort_index()
        local = local[~local.index.duplicated(keep="last")]

        # Enforce basic OHLC sanity and keep non-negative volume.
        local = local.dropna(subset=["Open", "High", "Low", "Close"])
        local = local[(local["Open"] > 0) & (local["High"] > 0) & (local["Low"] > 0) & (local["Close"] > 0)]
        local["Volume"] = local["Volume"].fillna(0.0).clip(lower=0.0)

        return local

    def load_dataframe(self, ticker: str, interval: str) -> pd.DataFrame:
        path = self._dataset_path(ticker, interval)
        if not path.exists():
            return pd.DataFrame(columns=REQUIRED_COLUMNS)

        try:
            df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index, errors="coerce", utc=True)
            elif df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            return self._normalize_dataframe(df)
        except Exception as e:
            logger.error("Failed to load historical dataset %s: %s", path, e)
            return pd.DataFrame(columns=REQUIRED_COLUMNS)

    def save_dataframe(self, ticker: str, interval: str, df: pd.DataFrame, merge: bool = True) -> pd.DataFrame:
        path = self._dataset_path(ticker, interval)
        normalized = self._normalize_dataframe(df)
        normalized = self._align_index_to_interval(normalized, interval)

        if merge and path.exists():
            existing = self.load_dataframe(ticker, interval)
            normalized = pd.concat([existing, normalized]).sort_index()
            normalized = normalized[~normalized.index.duplicated(keep="last")]
            normalized = self._normalize_dataframe(normalized)
            normalized = self._align_index_to_interval(normalized, interval)
            normalized = normalized[~normalized.index.duplicated(keep="last")]

        normalized.to_csv(path, index_label="datetime")
        return normalized

    def load_range(
        self,
        ticker: str,
        interval: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self.load_dataframe(ticker, interval)
        if df.empty:
            return df

        if start_date:
            start_ts = pd.Timestamp(start_date, tz="UTC")
            df = df[df.index >= start_ts]
        if end_date:
            end_ts = pd.Timestamp(end_date, tz="UTC")
            df = df[df.index <= end_ts]
        return df

    def quality_report(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        if df is None or df.empty:
            return {
                "is_empty": True,
                "row_count": 0,
                "missing_required_columns": REQUIRED_COLUMNS,
            }

        normalized = self._normalize_dataframe(df)
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in normalized.columns]

        invalid_prices = int(
            ((normalized["Open"] <= 0) | (normalized["High"] <= 0) | (normalized["Low"] <= 0) | (normalized["Close"] <= 0)).sum()
        )
        high_low_inversion = int((normalized["High"] < normalized["Low"]).sum())
        negative_volume = int((normalized["Volume"] < 0).sum())
        duplicate_index_rows = int(normalized.index.duplicated().sum())

        missing_intervals_est = 0
        large_gap_count = 0
        expected = self._expected_delta(interval)
        if expected is not None and len(normalized.index) > 1:
            diffs = normalized.index.to_series().diff().dropna()
            # Ignore multi-day market closures; only estimate missing candles in near-term gaps.
            bounded = diffs[(diffs > expected * 1.5) & (diffs < pd.Timedelta(days=3))]
            large_gap_count = int(len(bounded))
            if len(bounded) > 0:
                missing_intervals_est = int(sum(max(int(round(gap / expected)) - 1, 0) for gap in bounded))

        return {
            "is_empty": False,
            "row_count": int(len(normalized)),
            "start": normalized.index.min().isoformat(),
            "end": normalized.index.max().isoformat(),
            "missing_required_columns": missing_cols,
            "duplicate_index_rows": duplicate_index_rows,
            "invalid_price_rows": invalid_prices,
            "high_low_inversion_rows": high_low_inversion,
            "negative_volume_rows": negative_volume,
            "large_gap_count": large_gap_count,
            "missing_intervals_est": missing_intervals_est,
        }

    def backfill(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        existing = self.load_dataframe(ticker, interval)
        previous_rows = len(existing)

        fetched = get_sync_market_data(ticker, period=period, interval=interval)
        if fetched is None or fetched.empty:
            return {
                "status": "error",
                "message": f"No data fetched for {ticker}",
                "ticker": ticker,
                "interval": interval,
                "period": period,
            }

        saved = self.save_dataframe(ticker, interval, fetched, merge=not force_refresh)
        current_rows = len(saved)
        path = self._dataset_path(ticker, interval)

        return {
            "status": "success",
            "ticker": ticker,
            "interval": interval,
            "period": period,
            "file_path": str(path),
            "rows_before": int(previous_rows),
            "rows_after": int(current_rows),
            "rows_added": int(max(current_rows - previous_rows, 0)),
            "data_start": saved.index.min().isoformat() if not saved.empty else None,
            "data_end": saved.index.max().isoformat() if not saved.empty else None,
            "first_close": float(saved["Close"].iloc[0]) if not saved.empty else None,
            "last_close": float(saved["Close"].iloc[-1]) if not saved.empty else None,
            "quality": self.quality_report(saved, interval),
        }


historical_data_service = HistoricalDataService()
