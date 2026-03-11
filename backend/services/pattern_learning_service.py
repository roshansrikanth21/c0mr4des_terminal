from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.ict_smart_money import ICTSmartMoney
from backend.market_data import calculate_atr
from backend.services.historical_data_service import historical_data_service
from backend.services.market_data_service import get_sync_market_data
from backend.services.memory_service import memory_service


@dataclass
class PatternTrainingConfig:
    ticker: str = "^NSEI"
    interval: str = "15m"
    period: str = "1y"
    min_samples: int = 12
    min_win_rate: float = 0.80
    horizon_bars: int = 12
    stop_atr: float = 1.0
    target_atr: float = 1.5
    auto_backfill: bool = True


class PatternLearningService:
    def __init__(self):
        root = Path(__file__).resolve().parents[2]
        self.output_dir = root / "data" / "pattern_quality"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_ticker(ticker: str) -> str:
        safe = (ticker or "").strip().replace("^", "IDX_").replace(":", "_")
        safe = safe.replace("/", "_").replace("\\", "_")
        return "".join(ch if (ch.isalnum() or ch in {"_", "-", "."}) else "_" for ch in safe)

    def _artifact_path(self, ticker: str, interval: str) -> Path:
        return self.output_dir / f"{self._safe_ticker(ticker)}__{interval}.json"

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

        if not isinstance(local.index, pd.DatetimeIndex):
            local.index = pd.to_datetime(local.index, errors="coerce", utc=True)
        elif local.index.tz is None:
            local.index = local.index.tz_localize("UTC")
        else:
            local.index = local.index.tz_convert("UTC")

        local = local.dropna(subset=["Open", "High", "Low", "Close"])
        local["Volume"] = local["Volume"].fillna(0.0)
        local = local.sort_index()
        local = local[~local.index.duplicated(keep="last")]
        return local

    def _load_training_data(self, cfg: PatternTrainingConfig) -> pd.DataFrame:
        df = historical_data_service.load_dataframe(cfg.ticker, cfg.interval)
        if df.empty and cfg.auto_backfill:
            historical_data_service.backfill(cfg.ticker, cfg.period, cfg.interval, force_refresh=False)
            df = historical_data_service.load_dataframe(cfg.ticker, cfg.interval)
        if df.empty:
            df = get_sync_market_data(cfg.ticker, period=cfg.period, interval=cfg.interval)
        return self._normalize_df(df)

    @staticmethod
    def _parse_ts(value: object) -> Optional[pd.Timestamp]:
        try:
            ts = pd.Timestamp(value)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            return ts
        except Exception:
            return None

    @staticmethod
    def _find_event_index(df: pd.DataFrame, event_ts: Optional[pd.Timestamp]) -> Optional[int]:
        if event_ts is None or df.empty:
            return None
        idx = int(df.index.searchsorted(event_ts))
        if idx >= len(df):
            return None
        return idx

    @staticmethod
    def _evaluate_trade(
        df: pd.DataFrame,
        idx: int,
        direction: str,
        atr_value: float,
        stop_atr: float,
        target_atr: float,
        horizon_bars: int,
    ) -> Optional[str]:
        if idx is None or idx >= len(df) - 2:
            return None

        entry = float(df["Close"].iloc[idx])
        if not np.isfinite(entry) or entry <= 0:
            return None

        atr_value = float(atr_value)
        if not np.isfinite(atr_value) or atr_value <= 0:
            atr_value = entry * 0.01

        future = df.iloc[idx + 1: idx + 1 + horizon_bars]
        if future.empty:
            return None

        is_buy = direction.upper() == "BUY"
        stop = entry - stop_atr * atr_value if is_buy else entry + stop_atr * atr_value
        target = entry + target_atr * atr_value if is_buy else entry - target_atr * atr_value

        for row in future.itertuples():
            low = float(row.Low)
            high = float(row.High)
            close = float(row.Close)

            stop_hit = low <= stop if is_buy else high >= stop
            target_hit = high >= target if is_buy else low <= target

            if target_hit and not stop_hit:
                return "win"
            if stop_hit and not target_hit:
                return "loss"
            if stop_hit and target_hit:
                if is_buy:
                    return "win" if close >= entry else "loss"
                return "win" if close <= entry else "loss"

        last_close = float(future["Close"].iloc[-1])
        if is_buy and last_close > entry:
            return "win"
        if (not is_buy) and last_close < entry:
            return "win"
        return "loss"

    @staticmethod
    def match_detected_patterns(patterns: List[str]) -> List[str]:
        matched: List[str] = []
        for pattern in patterns or []:
            upper = str(pattern).upper()
            if "IFVG" in upper:
                if "BULL" in upper:
                    matched.append("bullish_ifvg")
                elif "BEAR" in upper:
                    matched.append("bearish_ifvg")
                else:
                    matched.extend(["bullish_ifvg", "bearish_ifvg"])
            elif "FVG" in upper:
                if "BULL" in upper:
                    matched.append("bullish_fvg")
                elif "BEAR" in upper:
                    matched.append("bearish_fvg")
                else:
                    matched.extend(["bullish_fvg", "bearish_fvg"])
            elif "ORDER BLOCK" in upper or upper == "OB":
                if "BULL" in upper:
                    matched.append("bullish_ob")
                elif "BEAR" in upper:
                    matched.append("bearish_ob")
                else:
                    matched.extend(["bullish_ob", "bearish_ob"])
            elif "SWEEP" in upper or "LIQUIDITY" in upper or "STOP HUNT" in upper:
                if "BULL" in upper:
                    matched.append("bullish_sweep")
                elif "BEAR" in upper:
                    matched.append("bearish_sweep")
                else:
                    matched.extend(["bullish_sweep", "bearish_sweep"])

        # Preserve order while removing duplicates.
        out: List[str] = []
        for item in matched:
            if item not in out:
                out.append(item)
        return out

    def train(self, cfg: PatternTrainingConfig) -> Dict[str, Any]:
        df = self._load_training_data(cfg)
        if df.empty or len(df) < max(cfg.horizon_bars + 50, 120):
            return {
                "status": "error",
                "message": "Insufficient historical data to train pattern quality model",
                "rows": int(len(df)),
            }

        atr = calculate_atr(df["High"], df["Low"], df["Close"], 14).bfill().ffill()
        ict = ICTSmartMoney(df)

        stats: Dict[str, Dict[str, Any]] = {}

        def ensure(pattern_id: str) -> Dict[str, Any]:
            if pattern_id not in stats:
                stats[pattern_id] = {
                    "pattern_id": pattern_id,
                    "samples": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "avg_atr": 0.0,
                }
            return stats[pattern_id]

        def record(pattern_id: str, direction: str, event_ts: object) -> None:
            ts = self._parse_ts(event_ts)
            idx = self._find_event_index(df, ts)
            if idx is None or idx >= len(df):
                return
            outcome = self._evaluate_trade(
                df=df,
                idx=idx,
                direction=direction,
                atr_value=float(atr.iloc[idx]) if idx < len(atr) else 0.0,
                stop_atr=cfg.stop_atr,
                target_atr=cfg.target_atr,
                horizon_bars=cfg.horizon_bars,
            )
            if outcome is None:
                return

            item = ensure(pattern_id)
            item["samples"] += 1
            item["avg_atr"] += float(atr.iloc[idx]) if idx < len(atr) else 0.0
            if outcome == "win":
                item["wins"] += 1
            else:
                item["losses"] += 1

        for fvg in ict.detect_fair_value_gaps():
            record(
                "bullish_fvg" if fvg.get("type") == "bullish" else "bearish_fvg",
                "BUY" if fvg.get("type") == "bullish" else "SELL",
                fvg.get("end_time"),
            )

        for ifvg in ict.detect_inverse_fair_value_gaps():
            pattern_id = "bullish_ifvg" if "bullish" in str(ifvg.get("type", "")).lower() else "bearish_ifvg"
            record(pattern_id, "BUY" if pattern_id == "bullish_ifvg" else "SELL", ifvg.get("flipped_at") or ifvg.get("end_time"))

        for ob in ict.detect_order_blocks():
            pattern_id = "bullish_ob" if str(ob.get("type")) == "bullish_ob" else "bearish_ob"
            record(pattern_id, "BUY" if pattern_id == "bullish_ob" else "SELL", ob.get("time"))

        for sweep in ict.detect_liquidity_sweeps():
            pattern_id = "bullish_sweep" if "bullish" in str(sweep.get("type", "")).lower() else "bearish_sweep"
            record(pattern_id, "BUY" if pattern_id == "bullish_sweep" else "SELL", sweep.get("time"))

        pattern_stats: List[Dict[str, Any]] = []
        approved_patterns: List[Dict[str, Any]] = []
        for item in stats.values():
            samples = max(int(item["samples"]), 1)
            avg_atr = float(item["avg_atr"]) / samples
            win_rate = float(item["wins"]) / samples
            row = {
                "pattern_id": item["pattern_id"],
                "samples": int(item["samples"]),
                "wins": int(item["wins"]),
                "losses": int(item["losses"]),
                "win_rate": round(win_rate, 4),
                "avg_atr": round(avg_atr, 6),
                "approved": bool(item["samples"] >= cfg.min_samples and win_rate >= cfg.min_win_rate),
            }
            pattern_stats.append(row)
            if row["approved"]:
                approved_patterns.append(row)

        pattern_stats.sort(key=lambda x: (-x["win_rate"], -x["samples"], x["pattern_id"]))
        approved_patterns.sort(key=lambda x: (-x["win_rate"], -x["samples"], x["pattern_id"]))

        artifact = {
            "status": "success",
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "ticker": cfg.ticker,
            "interval": cfg.interval,
            "rows": int(len(df)),
            "date_range": {
                "start": df.index.min().isoformat(),
                "end": df.index.max().isoformat(),
            },
            "thresholds": {
                "min_samples": int(cfg.min_samples),
                "min_win_rate": float(cfg.min_win_rate),
                "horizon_bars": int(cfg.horizon_bars),
                "stop_atr": float(cfg.stop_atr),
                "target_atr": float(cfg.target_atr),
            },
            "config": asdict(cfg),
            "pattern_stats": pattern_stats,
            "approved_patterns": approved_patterns,
            "approved_pattern_ids": [row["pattern_id"] for row in approved_patterns],
        }

        self._artifact_path(cfg.ticker, cfg.interval).write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        for row in approved_patterns[:8]:
            memory_service.add_memory(
                content=(
                    f"Approved pattern {row['pattern_id']} on {cfg.ticker} {cfg.interval}. "
                    f"Win rate {row['win_rate']:.2%} across {row['samples']} samples."
                ),
                source="pattern_learning_service",
                metadata={
                    "memory_type": "strategy",
                    "ticker": cfg.ticker,
                    "interval": cfg.interval,
                    "setup_family": row["pattern_id"],
                    "confidence": min(max(float(row["win_rate"]), 0.35), 0.98),
                    "sample_count": int(row["samples"]),
                    "last_validated_at": artifact["trained_at"],
                },
            )
        return artifact

    def get_latest(self, ticker: str, interval: str = "15m") -> Dict[str, Any]:
        path = self._artifact_path(ticker, interval)
        if not path.exists():
            return {
                "status": "error",
                "message": "No trained pattern artifact found",
                "ticker": ticker,
                "interval": interval,
                "approved_patterns": [],
                "approved_pattern_ids": [],
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to read pattern artifact: {exc}",
                "ticker": ticker,
                "interval": interval,
                "approved_patterns": [],
                "approved_pattern_ids": [],
            }


pattern_learning_service = PatternLearningService()
