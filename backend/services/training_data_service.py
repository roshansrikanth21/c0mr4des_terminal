from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from backend.market_data import calculate_atr, calculate_macd, calculate_rsi, calculate_sma
from backend.services.historical_data_service import historical_data_service
from backend.services.market_data_service import get_sync_market_data


@dataclass
class DatasetBuildConfig:
    ticker: str = "^NSEI"
    interval: str = "15m"
    period: str = "1y"
    horizon: int = 5
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    include_news: bool = True


class TrainingDataService:
    def __init__(self):
        root = Path(__file__).resolve().parents[2]
        self.output_dir = root / "data" / "training"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        local = df.copy()
        if isinstance(local.columns, pd.MultiIndex):
            local.columns = local.columns.get_level_values(0)
        local.columns = [str(c).capitalize() for c in local.columns]

        required = ["Open", "High", "Low", "Close", "Volume"]
        for col in required:
            if col not in local.columns:
                return pd.DataFrame()
            local[col] = pd.to_numeric(local[col], errors="coerce")

        local = local.dropna(subset=["Open", "High", "Low", "Close"])
        local["Volume"] = local["Volume"].fillna(0.0)
        local = local.sort_index()
        return local

    async def _build_news_features(self, index: pd.DatetimeIndex, ticker: str, interval: str) -> pd.DataFrame:
        try:
            from backend.services.news_ml_service import news_ml_service
            items = await news_ml_service.get_global_news_impact(benchmark_ticker=ticker, interval=interval)
        except Exception:
            items = []
        if not items:
            return pd.DataFrame(index=index, data={
                "news_affect": 0.0,
                "news_bias": 0.0,
                "news_crash_ratio": 0.0,
            })

        rows = []
        for item in items:
            ts = pd.to_datetime(item.get("published_at"), errors="coerce", utc=True)
            if pd.isna(ts):
                continue
            direction = str(item.get("market_direction", "NEUTRAL")).upper()
            bias = 1.0 if direction == "BULLISH" else (-1.0 if direction in {"BEARISH", "CRASH_WARNING"} else 0.0)
            rows.append(
                {
                    "date": ts.normalize(),
                    "news_affect": float(item.get("affect_rate", 0.0) or 0.0),
                    "news_bias": bias,
                    "news_crash": 1.0 if direction == "CRASH_WARNING" else 0.0,
                }
            )

        if not rows:
            return pd.DataFrame(index=index, data={
                "news_affect": 0.0,
                "news_bias": 0.0,
                "news_crash_ratio": 0.0,
            })

        frame = pd.DataFrame(rows)
        agg = frame.groupby("date", as_index=False).agg(
            news_affect=("news_affect", "mean"),
            news_bias=("news_bias", "mean"),
            news_crash_ratio=("news_crash", "mean"),
        )
        agg["date"] = pd.to_datetime(agg["date"], utc=True)

        out = pd.DataFrame(index=index)
        out["date"] = out.index.tz_convert("UTC").normalize() if out.index.tz is not None else out.index.tz_localize("UTC").normalize()
        out = out.reset_index().merge(agg, on="date", how="left").set_index("index")
        out = out[["news_affect", "news_bias", "news_crash_ratio"]].fillna(0.0)
        out.index.name = None
        return out

    def _fetch_base_data(self, cfg: DatasetBuildConfig) -> pd.DataFrame:
        if cfg.start_date or cfg.end_date:
            df = historical_data_service.load_range(
                ticker=cfg.ticker,
                interval=cfg.interval,
                start_date=cfg.start_date,
                end_date=cfg.end_date,
            )
            if df.empty:
                historical_data_service.backfill(ticker=cfg.ticker, period=cfg.period, interval=cfg.interval)
                df = historical_data_service.load_range(
                    ticker=cfg.ticker,
                    interval=cfg.interval,
                    start_date=cfg.start_date,
                    end_date=cfg.end_date,
                )
            return self._normalize_df(df)

        df = get_sync_market_data(cfg.ticker, period=cfg.period, interval=cfg.interval)
        if df.empty:
            historical_data_service.backfill(ticker=cfg.ticker, period=cfg.period, interval=cfg.interval)
            df = historical_data_service.load_dataframe(cfg.ticker, cfg.interval)
        return self._normalize_df(df)

    async def build_dataset(self, cfg: DatasetBuildConfig) -> Dict[str, Any]:
        df = self._fetch_base_data(cfg)
        if df.empty or len(df) < max(120, cfg.horizon + 50):
            return {
                "status": "error",
                "message": "Insufficient market data for training dataset",
                "rows": int(len(df)),
            }

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        f = pd.DataFrame(index=df.index)
        f["ret_1"] = close.pct_change(1)
        f["ret_3"] = close.pct_change(3)
        f["ret_5"] = close.pct_change(5)
        f["volatility_20"] = close.pct_change().rolling(20).std()

        sma_20 = calculate_sma(close, 20)
        sma_50 = calculate_sma(close, 50)
        rsi_14 = calculate_rsi(close, 14)
        atr_14 = calculate_atr(high, low, close, 14)
        macd, macd_signal = calculate_macd(close)

        f["sma20_dist"] = (close - sma_20) / sma_20.replace(0, np.nan)
        f["sma50_dist"] = (close - sma_50) / sma_50.replace(0, np.nan)
        f["sma_trend"] = (sma_20 - sma_50) / sma_50.replace(0, np.nan)
        f["rsi_14"] = rsi_14
        f["atr_norm"] = atr_14 / close.replace(0, np.nan)
        f["macd"] = macd
        f["macd_signal"] = macd_signal
        f["macd_hist"] = macd - macd_signal
        f["volume_z20"] = (volume - volume.rolling(20).mean()) / volume.rolling(20).std().replace(0, np.nan)

        if cfg.include_news:
            news_frame = await self._build_news_features(f.index, cfg.ticker, cfg.interval)
            f = f.join(news_frame, how="left")
        else:
            f["news_affect"] = 0.0
            f["news_bias"] = 0.0
            f["news_crash_ratio"] = 0.0

        future_return = close.shift(-cfg.horizon) / close - 1.0
        future_min = close.shift(-1).rolling(cfg.horizon).min()
        max_drawdown = (future_min / close) - 1.0

        f["target_return"] = future_return
        f["target_direction"] = (future_return > 0).astype(int)
        f["target_drawdown"] = max_drawdown

        f = f.replace([np.inf, -np.inf], np.nan).dropna().copy()
        if f.empty:
            return {
                "status": "error",
                "message": "Feature engineering produced empty dataset",
                "rows": 0,
            }

        safe_ticker = cfg.ticker.replace("^", "IDX_").replace(":", "_").replace("/", "_")
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_path = self.output_dir / f"{safe_ticker}__{cfg.interval}__h{cfg.horizon}__{stamp}.csv"
        f.to_csv(out_path, index_label="datetime")

        feature_cols = [
            c
            for c in f.columns
            if c not in {"target_return", "target_direction", "target_drawdown"}
        ]

        return {
            "status": "success",
            "path": str(out_path),
            "rows": int(len(f)),
            "ticker": cfg.ticker,
            "interval": cfg.interval,
            "horizon": int(cfg.horizon),
            "feature_count": int(len(feature_cols)),
            "feature_columns": feature_cols,
            "target_columns": ["target_return", "target_direction", "target_drawdown"],
            "date_range": {
                "start": f.index.min().isoformat(),
                "end": f.index.max().isoformat(),
            },
        }


training_data_service = TrainingDataService()
