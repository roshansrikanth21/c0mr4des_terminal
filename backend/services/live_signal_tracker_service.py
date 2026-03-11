from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.services.market_data_service import get_sync_market_data
from backend.services.memory_service import memory_service


class LiveSignalTrackerService:
    """
    Tracks live/exported signals and settles them against subsequent market data.
    This creates a real post-signal scorecard separate from backtests.
    """

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.data_dir = root / "data" / "signal_tracker"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.data_dir / "signals.json"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_ts(value: Any) -> Optional[pd.Timestamp]:
        try:
            ts = pd.Timestamp(value)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            return ts
        except Exception:
            return None

    def _load(self) -> Dict[str, Any]:
        if not self.store_path.exists():
            return {"signals": [], "created_at": self._utc_now()}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"signals": [], "created_at": self._utc_now()}

    def _save(self, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = self._utc_now()
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_signal(
        self,
        *,
        ticker: str,
        interval: str,
        source: str,
        action: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        raw_payload: Optional[Dict[str, Any]] = None,
        generated_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = self._load()
        signal_id = f"SIG_{uuid.uuid4().hex[:12].upper()}"
        signal = {
            "signal_id": signal_id,
            "created_at": generated_at or self._utc_now(),
            "ticker": ticker,
            "interval": interval,
            "source": source,
            "action": str(action).upper(),
            "entry": float(entry),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "confidence": float(confidence),
            "status": "open",
            "settled_at": None,
            "outcome": None,
            "bars_observed": 0,
            "realized_return_pct": 0.0,
            "realized_pnl_units": 0.0,
            "raw_payload": raw_payload or {},
            "feedback": [],
        }
        db["signals"].append(signal)
        self._save(db)
        return {"status": "success", "signal": signal}

    def save_execution_feedback(self, signal_id: str, feedback: Dict[str, Any]) -> Dict[str, Any]:
        db = self._load()
        for signal in db.get("signals", []):
            if signal.get("signal_id") == signal_id:
                signal.setdefault("feedback", []).append(
                    {
                        "received_at": self._utc_now(),
                        "payload": feedback,
                    }
                )
                self._save(db)
                return {"status": "success", "signal_id": signal_id}
        return {"status": "error", "message": f"Signal not found: {signal_id}"}

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
        return local.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()

    @staticmethod
    def _period_for_interval(interval: str) -> str:
        interval = str(interval or "15m").lower()
        if interval in {"1m", "5m", "15m"}:
            return "60d"
        if interval in {"30m", "1h", "60m"}:
            return "180d"
        return "2y"

    def _settle_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        if signal.get("status") != "open":
            return signal

        action = str(signal.get("action", "HOLD")).upper()
        if action not in {"BUY", "SELL", "BUY CALL", "BUY PUT"}:
            signal["status"] = "ignored"
            signal["outcome"] = "not_tradeable"
            signal["settled_at"] = self._utc_now()
            return signal

        interval = str(signal.get("interval", "15m"))
        ticker = str(signal.get("ticker", "^NSEI"))
        created_at = self._parse_ts(signal.get("created_at"))
        if created_at is None:
            return signal

        df = self._normalize_df(get_sync_market_data(ticker=ticker, period=self._period_for_interval(interval), interval=interval))
        if df.empty:
            return signal

        idx = int(df.index.searchsorted(created_at))
        if idx >= len(df):
            return signal

        future = df.iloc[idx:]
        if len(future) < 2:
            return signal

        entry = float(signal.get("entry", 0.0) or 0.0)
        stop_loss = float(signal.get("stop_loss", entry) or entry)
        take_profit = float(signal.get("take_profit", entry) or entry)
        is_buy = action in {"BUY", "BUY CALL"}

        horizon_bars = 24
        observed = future.iloc[:horizon_bars]
        if observed.empty:
            return signal

        outcome = "open"
        settle_price = float(observed["Close"].iloc[-1])
        bars_observed = len(observed)

        for row in observed.itertuples():
            low = float(row.Low)
            high = float(row.High)
            close = float(row.Close)
            stop_hit = low <= stop_loss if is_buy else high >= stop_loss
            target_hit = high >= take_profit if is_buy else low <= take_profit

            if target_hit and not stop_hit:
                outcome = "target_hit"
                settle_price = take_profit
                break
            if stop_hit and not target_hit:
                outcome = "stop_hit"
                settle_price = stop_loss
                break
            if stop_hit and target_hit:
                outcome = "mixed_bar"
                settle_price = close
                break

        if outcome == "open":
            outcome = "time_expired"

        signed_return = ((settle_price / max(entry, 1e-9)) - 1.0) * (1.0 if is_buy else -1.0)
        signal["status"] = "settled"
        signal["outcome"] = outcome
        signal["settled_at"] = self._utc_now()
        signal["bars_observed"] = int(bars_observed)
        signal["realized_return_pct"] = round(float(signed_return * 100.0), 4)
        signal["realized_pnl_units"] = round(float(settle_price - entry) * (1.0 if is_buy else -1.0), 6)
        return signal

    def settle_open_signals(self, ticker: Optional[str] = None) -> Dict[str, Any]:
        db = self._load()
        settled = 0
        for signal in db.get("signals", []):
            if ticker and str(signal.get("ticker")) != ticker:
                continue
            prev_status = signal.get("status")
            self._settle_signal(signal)
            if prev_status == "open" and signal.get("status") == "settled":
                settled += 1
                setup_family = self._derive_setup_family(signal)
                validation_outcome = "success" if float(signal.get("realized_return_pct", 0.0) or 0.0) > 0 else "failure"
                matched = memory_service.retrieve_memories(
                    query="",
                    limit=3,
                    memory_type="strategy",
                    ticker=signal.get("ticker"),
                    interval=signal.get("interval"),
                    setup_family=setup_family,
                    min_confidence=0.20,
                )
                for row in matched.get("memories", []) or []:
                    memory_id = row.get("memory_id")
                    if not memory_id:
                        continue
                    memory_service.record_validation(
                        memory_id=str(memory_id),
                        outcome=validation_outcome,
                        details={
                            "source_signal_id": signal.get("signal_id"),
                            "realized_return_pct": signal.get("realized_return_pct"),
                            "ticker": signal.get("ticker"),
                            "interval": signal.get("interval"),
                        },
                    )
                components = (((signal.get("raw_payload") or {}).get("decision") or {}).get("components")) or {}
                memory_service.add_memory(
                    content=(
                        f"Settled live signal {signal.get('action')} on {signal.get('ticker')} {signal.get('interval')}. "
                        f"Outcome: {signal.get('outcome')}. Return: {signal.get('realized_return_pct', 0.0)}%."
                    ),
                    source="live_signal_tracker",
                    metadata={
                        "memory_type": "strategy",
                        "ticker": signal.get("ticker"),
                        "interval": signal.get("interval"),
                        "setup_family": setup_family,
                        "confidence": max(float(signal.get("confidence", 0.0) or 0.0), 0.25),
                        "sample_count": 1,
                        "last_validated_at": signal.get("settled_at"),
                        "outcome": signal.get("outcome"),
                        "direction": signal.get("action"),
                        "realized_return_pct": signal.get("realized_return_pct"),
                        "component_snapshot": components,
                    },
                )
        self._save(db)
        return {"status": "success", "settled": settled}

    @staticmethod
    def _action_sign(action: str) -> int:
        upper = str(action or "HOLD").upper()
        if upper in {"BUY", "BUY CALL"}:
            return 1
        if upper in {"SELL", "BUY PUT"}:
            return -1
        return 0

    @staticmethod
    def _derive_setup_family(signal: Dict[str, Any]) -> Optional[str]:
        raw_payload = signal.get("raw_payload") or {}
        strategy_pack = raw_payload.get("strategy_pack") or {}
        signals = list(strategy_pack.get("signals", []) or [])
        if signals:
            pattern = str((signals[0] or {}).get("pattern") or (signals[0] or {}).get("strategy") or "").strip().lower()
            if "ifvg" in pattern:
                return "ifvg"
            if "fvg" in pattern:
                return "fvg"
            if "order block" in pattern or pattern == "ob":
                return "order_block"
            if "sweep" in pattern or "liquidity" in pattern or "stop hunt" in pattern:
                return "liquidity_sweep"
            if pattern:
                return pattern
        action = str(strategy_pack.get("action") or "").strip().lower()
        return action or None

    def _build_component_reliability(self, settled_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for row in settled_rows:
            action_sign = self._action_sign(str(row.get("action", "HOLD")))
            realized_sign = 0
            realized_return = float(row.get("realized_return_pct", 0.0) or 0.0)
            if action_sign != 0 and realized_return != 0:
                market_sign = 1 if (realized_return * action_sign) > 0 else -1
                realized_sign = market_sign

            raw_payload = row.get("raw_payload") or {}
            components = (
                (((raw_payload.get("decision") or {}).get("components")) or {})
                if row.get("source") == "fusion_decision"
                else (((raw_payload.get("meta") or {}).get("components")) or {})
            )
            if not isinstance(components, dict):
                continue

            for name, raw_val in components.items():
                try:
                    value = float(raw_val)
                except Exception:
                    continue
                if not np.isfinite(value) or abs(value) < 0.05:
                    continue

                comp_sign = 1 if value > 0 else -1
                bucket = buckets.setdefault(
                    name,
                    {"component": name, "samples": 0, "hits": 0, "weighted_abs": [], "avg_contribution": []},
                )
                bucket["samples"] += 1
                bucket["weighted_abs"].append(abs(value))
                bucket["avg_contribution"].append(value)
                if realized_sign != 0 and comp_sign == realized_sign:
                    bucket["hits"] += 1

        rows: List[Dict[str, Any]] = []
        for bucket in buckets.values():
            samples = int(bucket["samples"])
            rows.append(
                {
                    "component": bucket["component"],
                    "samples": samples,
                    "hit_rate": round((bucket["hits"] / max(samples, 1)) * 100.0, 2),
                    "avg_abs_weight": round(float(np.mean(bucket["weighted_abs"])) if bucket["weighted_abs"] else 0.0, 4),
                    "avg_component_value": round(float(np.mean(bucket["avg_contribution"])) if bucket["avg_contribution"] else 0.0, 4),
                }
            )
        rows.sort(key=lambda x: (-x["samples"], x["component"]))
        return rows

    def get_summary(self, ticker: Optional[str] = None) -> Dict[str, Any]:
        db = self._load()
        rows = db.get("signals", [])
        if ticker:
            rows = [row for row in rows if str(row.get("ticker")) == ticker]

        if not rows:
            return {
                "status": "success",
                "summary": {
                    "total_signals": 0,
                    "open_signals": 0,
                    "settled_signals": 0,
                    "win_rate": 0.0,
                    "avg_realized_return_pct": 0.0,
                },
                "component_reliability": [],
                "signals": [],
            }

        settled_rows = [row for row in rows if row.get("status") == "settled"]
        winning = [row for row in settled_rows if str(row.get("outcome")) in {"target_hit", "time_expired", "mixed_bar"} and float(row.get("realized_return_pct", 0.0)) > 0]
        win_rate = (len(winning) / len(settled_rows) * 100.0) if settled_rows else 0.0
        avg_ret = float(np.mean([float(row.get("realized_return_pct", 0.0)) for row in settled_rows])) if settled_rows else 0.0

        by_source: Dict[str, Dict[str, Any]] = {}
        for row in settled_rows:
            source = str(row.get("source", "unknown"))
            bucket = by_source.setdefault(source, {"signals": 0, "wins": 0, "avg_return_pct": []})
            bucket["signals"] += 1
            if float(row.get("realized_return_pct", 0.0)) > 0:
                bucket["wins"] += 1
            bucket["avg_return_pct"].append(float(row.get("realized_return_pct", 0.0)))

        source_rows = []
        for source, bucket in by_source.items():
            source_rows.append(
                {
                    "source": source,
                    "signals": int(bucket["signals"]),
                    "win_rate": round((bucket["wins"] / max(bucket["signals"], 1)) * 100.0, 2),
                    "avg_return_pct": round(float(np.mean(bucket["avg_return_pct"])) if bucket["avg_return_pct"] else 0.0, 4),
                }
            )
        source_rows.sort(key=lambda x: (-x["signals"], x["source"]))
        component_rows = self._build_component_reliability(settled_rows)

        return {
            "status": "success",
            "summary": {
                "total_signals": int(len(rows)),
                "open_signals": int(sum(1 for row in rows if row.get("status") == "open")),
                "settled_signals": int(len(settled_rows)),
                "win_rate": round(win_rate, 2),
                "avg_realized_return_pct": round(avg_ret, 4),
            },
            "by_source": source_rows,
            "component_reliability": component_rows,
            "signals": list(sorted(rows, key=lambda x: str(x.get("created_at")), reverse=True))[:100],
        }


live_signal_tracker_service = LiveSignalTrackerService()
