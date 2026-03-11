from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.services.historical_data_service import historical_data_service
from backend.services.memory_service import memory_service


@dataclass
class NewsEventStudyConfig:
    benchmark_ticker: str = "^NSEI"
    interval: str = "15m"
    horizon_bars: int = 12
    min_samples: int = 10
    period: str = "60d"
    auto_backfill: bool = True


class NewsEventStudyService:
    """
    Stores analyzed news events and calibrates predicted headline impact against
    realized forward market moves on a benchmark ticker.
    """

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.data_dir = root / "data" / "news_event_study"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.data_dir / "events.jsonl"

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = (value or "").strip().replace("^", "IDX_").replace(":", "_")
        return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in safe)

    def _artifact_path(self, benchmark_ticker: str, interval: str) -> Path:
        return self.data_dir / f"{self._safe_name(benchmark_ticker)}__{interval}.json"

    @staticmethod
    def _event_id(item: Dict[str, Any], benchmark_ticker: str) -> str:
        title = str(item.get("title") or "").strip().lower()
        published_at = str(item.get("published_at") or item.get("publishedAt") or "").strip()
        source = str(item.get("source") or "").strip().lower()
        raw = f"{benchmark_ticker}|{published_at}|{source}|{title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def record_items(self, items: List[Dict[str, Any]], benchmark_ticker: str = "^NSEI") -> Dict[str, Any]:
        if not items:
            return {"status": "success", "recorded": 0}

        existing_ids = set()
        if self.events_path.exists():
            try:
                for line in self.events_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    existing_ids.add(str(payload.get("event_id")))
            except Exception:
                existing_ids = set()

        recorded = 0
        with self.events_path.open("a", encoding="utf-8") as fh:
            for item in items:
                event_id = self._event_id(item, benchmark_ticker)
                if event_id in existing_ids:
                    continue
                payload = {
                    "event_id": event_id,
                    "recorded_at": datetime.utcnow().isoformat() + "Z",
                    "benchmark_ticker": benchmark_ticker,
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "published_at": item.get("published_at") or item.get("publishedAt"),
                    "url": item.get("url"),
                    "affect_rate": float(item.get("affect_rate", 0.0) or 0.0),
                    "market_direction": item.get("market_direction", "NEUTRAL"),
                    "keyword_severity": float(((item.get("nlp_metrics") or {}).get("keyword_severity", 0.0)) or 0.0),
                }
                fh.write(json.dumps(payload) + "\n")
                existing_ids.add(event_id)
                recorded += 1
        return {"status": "success", "recorded": recorded}

    def _load_events(self, benchmark_ticker: str) -> List[Dict[str, Any]]:
        if not self.events_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if str(payload.get("benchmark_ticker")) == benchmark_ticker:
                    rows.append(payload)
            except Exception:
                continue
        return rows

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
        if not isinstance(local.index, pd.DatetimeIndex):
            local.index = pd.to_datetime(local.index, errors="coerce", utc=True)
        elif local.index.tz is None:
            local.index = local.index.tz_localize("UTC")
        else:
            local.index = local.index.tz_convert("UTC")
        local = local.dropna(subset=["Close"]).sort_index()
        local = local[~local.index.duplicated(keep="last")]
        return local

    def _load_benchmark_df(self, cfg: NewsEventStudyConfig) -> pd.DataFrame:
        df = historical_data_service.load_dataframe(cfg.benchmark_ticker, cfg.interval)
        if df.empty and cfg.auto_backfill:
            historical_data_service.backfill(cfg.benchmark_ticker, cfg.period, cfg.interval, force_refresh=False)
            df = historical_data_service.load_dataframe(cfg.benchmark_ticker, cfg.interval)
        return self._normalize_df(df)

    def _validate_news_memories(self, samples: List[Dict[str, Any]], benchmark_ticker: str, interval: str) -> None:
        for sample in samples:
            title = str(sample.get("title") or "").strip()
            event_id = str(sample.get("event_id") or "").strip()
            if not title and not event_id:
                continue

            outcome = "success" if bool(sample.get("direction_hit")) else "failure"
            matched = memory_service.retrieve_memories(
                query=title or event_id,
                limit=4,
                memory_type="news",
                ticker=benchmark_ticker,
                interval=interval,
                min_confidence=0.15,
            )
            for row in matched.get("memories", []) or []:
                memory_id = row.get("memory_id")
                metadata = row.get("metadata") or {}
                if not memory_id:
                    continue
                memory_title = str(metadata.get("title") or "").strip().lower()
                sample_title = title.lower()
                if memory_title and sample_title and memory_title != sample_title:
                    continue
                memory_service.record_validation(
                    memory_id=str(memory_id),
                    outcome=outcome,
                    details={
                        "event_id": sample.get("event_id"),
                        "realized_move_pct": sample.get("realized_move_pct"),
                        "direction_hit": sample.get("direction_hit"),
                        "benchmark_ticker": benchmark_ticker,
                        "interval": interval,
                    },
                )

    def train(self, cfg: NewsEventStudyConfig) -> Dict[str, Any]:
        events = self._load_events(cfg.benchmark_ticker)
        if not events:
            return {
                "status": "error",
                "message": "No recorded news events available for calibration",
                "benchmark_ticker": cfg.benchmark_ticker,
            }

        df = self._load_benchmark_df(cfg)
        if df.empty or len(df) < max(cfg.horizon_bars + 20, 60):
            return {
                "status": "error",
                "message": "Insufficient benchmark market data for event study",
                "benchmark_ticker": cfg.benchmark_ticker,
                "rows": int(len(df)),
            }

        samples: List[Dict[str, Any]] = []
        for item in events:
            ts = pd.to_datetime(item.get("published_at"), errors="coerce", utc=True)
            if pd.isna(ts):
                continue
            idx = int(df.index.searchsorted(ts))
            if idx >= len(df) - cfg.horizon_bars:
                continue
            entry = float(df["Close"].iloc[idx])
            future = float(df["Close"].iloc[idx + cfg.horizon_bars])
            if not np.isfinite(entry) or entry <= 0 or not np.isfinite(future):
                continue
            realized_return = (future / entry) - 1.0
            realized_move_pct = abs(realized_return) * 100.0
            direction = str(item.get("market_direction", "NEUTRAL")).upper()
            predicted_sign = 1 if direction == "BULLISH" else (-1 if direction in {"BEARISH", "CRASH_WARNING"} else 0)
            realized_sign = 1 if realized_return > 0.001 else (-1 if realized_return < -0.001 else 0)
            hit = bool(predicted_sign == 0 or predicted_sign == realized_sign)
            severity = float(item.get("keyword_severity", 0.0) or 0.0)
            affect_rate = float(item.get("affect_rate", 0.0) or 0.0)
            samples.append(
                {
                    "event_id": item.get("event_id"),
                    "title": item.get("title"),
                    "published_at": ts.isoformat(),
                    "direction": direction,
                    "predicted_sign": predicted_sign,
                    "realized_sign": realized_sign,
                    "direction_hit": hit,
                    "affect_rate": affect_rate,
                    "keyword_severity": severity,
                    "realized_return": realized_return,
                    "realized_move_pct": realized_move_pct,
                    "impact_ratio": realized_move_pct / max(affect_rate, 1.0),
                }
            )

        if len(samples) < cfg.min_samples:
            return {
                "status": "error",
                "message": "Not enough matured news events to train event study",
                "benchmark_ticker": cfg.benchmark_ticker,
                "samples": len(samples),
            }

        sample_df = pd.DataFrame(samples)
        overall_hit = float(sample_df["direction_hit"].mean())
        impact_corr = float(sample_df["affect_rate"].corr(sample_df["realized_move_pct"])) if len(sample_df) > 1 else 0.0
        base_multiplier = float(sample_df["impact_ratio"].median())

        buckets: List[Dict[str, Any]] = []
        for bucket_name, bucket_df in {
            "bullish": sample_df[sample_df["direction"] == "BULLISH"],
            "bearish": sample_df[sample_df["direction"].isin(["BEARISH", "CRASH_WARNING"])],
            "neutral": sample_df[sample_df["direction"] == "NEUTRAL"],
            "high_severity": sample_df[sample_df["keyword_severity"] >= 0.6],
        }.items():
            if bucket_df.empty:
                continue
            buckets.append(
                {
                    "bucket": bucket_name,
                    "samples": int(len(bucket_df)),
                    "direction_hit_rate": round(float(bucket_df["direction_hit"].mean()), 4),
                    "median_impact_multiplier": round(float(bucket_df["impact_ratio"].median()), 4),
                    "avg_realized_move_pct": round(float(bucket_df["realized_move_pct"].mean()), 4),
                }
            )

        artifact = {
            "status": "success",
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "benchmark_ticker": cfg.benchmark_ticker,
            "interval": cfg.interval,
            "horizon_bars": int(cfg.horizon_bars),
            "samples": int(len(sample_df)),
            "metrics": {
                "direction_hit_rate": round(overall_hit, 4),
                "impact_correlation": round(impact_corr if np.isfinite(impact_corr) else 0.0, 4),
                "base_multiplier": round(base_multiplier if np.isfinite(base_multiplier) else 1.0, 4),
            },
            "buckets": buckets,
        }
        self._artifact_path(cfg.benchmark_ticker, cfg.interval).write_text(
            json.dumps(artifact, indent=2),
            encoding="utf-8",
        )
        self._validate_news_memories(samples, cfg.benchmark_ticker, cfg.interval)
        memory_service.add_memory(
            content=(
                f"News event-study trained for {cfg.benchmark_ticker} {cfg.interval}. "
                f"Hit rate {overall_hit:.2%}, samples {len(sample_df)}, impact corr {impact_corr:.2f}."
            ),
            source="news_event_study_service",
            metadata={
                "memory_type": "news",
                "ticker": cfg.benchmark_ticker,
                "interval": cfg.interval,
                "confidence": min(max(float(overall_hit), 0.35), 0.95),
                "sample_count": int(len(sample_df)),
                "last_validated_at": artifact["trained_at"],
                "impact_correlation": round(impact_corr if np.isfinite(impact_corr) else 0.0, 4),
                "direction_hit_rate": round(overall_hit, 4),
                "setup_family": "event_study",
            },
        )
        return artifact

    def get_latest(self, benchmark_ticker: str = "^NSEI", interval: str = "15m") -> Dict[str, Any]:
        path = self._artifact_path(benchmark_ticker, interval)
        if not path.exists():
            return {
                "status": "error",
                "message": "No news event-study artifact found",
                "benchmark_ticker": benchmark_ticker,
                "interval": interval,
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to read event-study artifact: {exc}",
                "benchmark_ticker": benchmark_ticker,
                "interval": interval,
            }

    def calibrate_items(self, items: List[Dict[str, Any]], benchmark_ticker: str = "^NSEI", interval: str = "15m") -> List[Dict[str, Any]]:
        artifact = self.get_latest(benchmark_ticker=benchmark_ticker, interval=interval)
        if artifact.get("status") != "success":
            return items

        base_multiplier = float(((artifact.get("metrics") or {}).get("base_multiplier", 1.0)) or 1.0)
        reliability = float(((artifact.get("metrics") or {}).get("direction_hit_rate", 0.5)) or 0.5)
        bucket_map = {row["bucket"]: row for row in artifact.get("buckets", [])}

        calibrated: List[Dict[str, Any]] = []
        for item in items:
            local = dict(item)
            direction = str(local.get("market_direction", "NEUTRAL")).upper()
            severity = float(((local.get("nlp_metrics") or {}).get("keyword_severity", 0.0)) or 0.0)

            bucket_key = "neutral"
            if severity >= 0.6 and "high_severity" in bucket_map:
                bucket_key = "high_severity"
            elif direction == "BULLISH" and "bullish" in bucket_map:
                bucket_key = "bullish"
            elif direction in {"BEARISH", "CRASH_WARNING"} and "bearish" in bucket_map:
                bucket_key = "bearish"

            bucket = bucket_map.get(bucket_key, {})
            multiplier = float(bucket.get("median_impact_multiplier", base_multiplier) or base_multiplier)
            bucket_hit = float(bucket.get("direction_hit_rate", reliability) or reliability)
            affect_rate = float(local.get("affect_rate", 0.0) or 0.0)
            calibrated_rate = float(np.clip(affect_rate * multiplier, 0.0, 100.0))

            local["raw_affect_rate"] = affect_rate
            local["calibrated_affect_rate"] = round(calibrated_rate, 1)
            local["affect_rate"] = round((affect_rate * 0.45) + (calibrated_rate * 0.55), 1)
            local["empirical_reliability"] = round(bucket_hit, 4)
            calibrated.append(local)
        return calibrated


news_event_study_service = NewsEventStudyService()
