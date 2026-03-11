from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from backend.services.memory_service import memory_service


class ExecutionQualityService:
    """
    Tracks realized execution quality from manual orders, strategy execution,
    and EA feedback so live execution friction can influence runtime risk.
    """

    SUCCESS_STATUSES = {"FILLED", "EXECUTED", "SUCCESS"}
    PENDING_STATUSES = {"SUBMITTED", "OPEN", "ACCEPTED", "PARTIAL"}
    FAILURE_STATUSES = {"REJECTED", "FAILED", "CANCELLED", "ERROR"}

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.data_dir = root / "data" / "execution_quality"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.data_dir / "events.json"
        self.model_path = self.data_dir / "models.json"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            parsed = float(value)
            if not np.isfinite(parsed):
                return None
            return parsed
        except Exception:
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(float(value))
        except Exception:
            return None

    @staticmethod
    def _normalize_status(value: Any) -> str:
        return str(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _normalize_side(value: Any) -> str:
        upper = str(value or "UNKNOWN").strip().upper()
        if upper in {"BUY CALL", "CALL"}:
            return "BUY"
        if upper in {"BUY PUT"}:
            return "SELL"
        return upper

    def _load(self) -> Dict[str, Any]:
        if not self.store_path.exists():
            return {"events": [], "created_at": self._utc_now()}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"events": [], "created_at": self._utc_now()}

    def _save(self, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = self._utc_now()
        self.store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_models(self) -> Dict[str, Any]:
        if not self.model_path.exists():
            return {"models": [], "updated_at": None}
        try:
            return json.loads(self.model_path.read_text(encoding="utf-8"))
        except Exception:
            return {"models": [], "updated_at": None}

    def _save_models(self, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = self._utc_now()
        self.model_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _session_bucket(value: Optional[Any] = None) -> str:
        try:
            ts = datetime.now(timezone.utc) if value is None else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            ts = datetime.now(timezone.utc)
        hour = ts.astimezone().hour
        if 9 <= hour < 11:
            return "open"
        if 11 <= hour < 14:
            return "midday"
        if 14 <= hour < 16:
            return "close"
        return "offhours"

    @staticmethod
    def _parse_ts(value: Any) -> Optional[datetime]:
        try:
            if value is None or value == "":
                return None
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _compute_metrics(self, event: Dict[str, Any]) -> Dict[str, Any]:
        expected = self._safe_float(event.get("expected_price"))
        executed = self._safe_float(event.get("executed_price"))
        latency_ms = self._safe_float(event.get("latency_ms"))
        status = self._normalize_status(event.get("status"))
        side = self._normalize_side(event.get("side"))
        requested_qty = max(self._safe_float(event.get("quantity")) or 0.0, 0.0)
        filled_qty = self._safe_float(event.get("filled_quantity"))
        if filled_qty is None:
            if status in self.SUCCESS_STATUSES:
                filled_qty = requested_qty
            elif status in self.FAILURE_STATUSES:
                filled_qty = 0.0
            else:
                filled_qty = 0.0
        fill_ratio = float(np.clip((filled_qty / requested_qty), 0.0, 1.0)) if requested_qty > 0 else 0.0

        created_at = self._parse_ts(event.get("created_at"))
        filled_at = self._parse_ts(event.get("filled_at"))
        time_to_fill_ms: Optional[float] = None
        if created_at and filled_at:
            time_to_fill_ms = max((filled_at - created_at).total_seconds() * 1000.0, 0.0)

        slippage_bps: Optional[float] = None
        if expected and expected > 0 and executed and executed > 0:
            if side == "SELL":
                slippage_bps = ((expected - executed) / expected) * 10000.0
            else:
                slippage_bps = ((executed - expected) / expected) * 10000.0
            slippage_bps = float(slippage_bps)

        score = 1.0
        if status in self.FAILURE_STATUSES:
            score = 0.0
        else:
            if status in self.PENDING_STATUSES:
                score -= 0.18
            score -= max(0.0, 1.0 - fill_ratio) * 0.28
            if slippage_bps is not None:
                score -= min(max(slippage_bps, 0.0) / 30.0, 0.55)
            if latency_ms is not None:
                score -= min(max(latency_ms, 0.0) / 6000.0, 0.22)
            if time_to_fill_ms is not None:
                score -= min(max(time_to_fill_ms, 0.0) / 180000.0, 0.20)
        score = float(np.clip(score, 0.0, 1.0))

        return {
            "slippage_bps": None if slippage_bps is None else round(slippage_bps, 4),
            "fill_ratio": round(fill_ratio, 4),
            "time_to_fill_ms": None if time_to_fill_ms is None else round(time_to_fill_ms, 2),
            "quality_score": round(score, 4),
            "is_rejected": status in self.FAILURE_STATUSES,
            "is_filled": status in self.SUCCESS_STATUSES,
            "is_pending": status in self.PENDING_STATUSES,
        }

    def _enrich_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        event.update(self._compute_metrics(event))
        return event

    @staticmethod
    def _memory_validation_outcome(event: Dict[str, Any]) -> Optional[str]:
        status = str(event.get("status") or "").upper()
        quality_score = float(event.get("quality_score", 0.0) or 0.0)
        fill_ratio = float(event.get("fill_ratio", 0.0) or 0.0)
        slippage_bps = float(event.get("slippage_bps", 0.0) or 0.0) if event.get("slippage_bps") is not None else 0.0

        if status in ExecutionQualityService.FAILURE_STATUSES:
            return "failure"
        if quality_score >= 0.82 and fill_ratio >= 0.95 and slippage_bps <= 8.0:
            return "success"
        if quality_score <= 0.42 or fill_ratio <= 0.70 or slippage_bps >= 15.0:
            return "failure"
        return None

    def _sync_execution_memory(self, event: Dict[str, Any]) -> None:
        symbol = str(event.get("symbol") or "UNKNOWN")
        broker = str(event.get("broker") or "unknown")
        order_type = str(event.get("order_type") or "MARKET")
        session_bucket = str(event.get("session_bucket") or "")
        execution_id = str(event.get("execution_id") or "")
        outcome = self._memory_validation_outcome(event)

        matched = memory_service.retrieve_memories(
            query=f"{execution_id} {broker} {order_type}".strip(),
            limit=4,
            memory_type="execution",
            ticker=symbol,
            session_bucket=session_bucket or None,
            min_confidence=0.18,
        )
        if outcome:
            for row in matched.get("memories", []) or []:
                memory_id = row.get("memory_id")
                metadata = row.get("metadata") or {}
                if not memory_id:
                    continue
                if str(metadata.get("broker") or "").strip() not in {"", broker}:
                    continue
                if str(metadata.get("order_type") or "").strip() not in {"", order_type}:
                    continue
                memory_service.record_validation(
                    memory_id=str(memory_id),
                    outcome=outcome,
                    details={
                        "execution_id": event.get("execution_id"),
                        "broker": broker,
                        "order_type": order_type,
                        "quality_score": event.get("quality_score"),
                        "fill_ratio": event.get("fill_ratio"),
                        "slippage_bps": event.get("slippage_bps"),
                    },
                )

        if execution_id:
            for row in matched.get("memories", []) or []:
                metadata = row.get("metadata") or {}
                if str(metadata.get("execution_id") or "") == execution_id:
                    return

        should_store = (
            str(event.get("status") or "").upper() in self.FAILURE_STATUSES
            or float(event.get("quality_score", 0.0) or 0.0) >= 0.82
            or float(event.get("quality_score", 0.0) or 0.0) <= 0.42
            or float(event.get("fill_ratio", 1.0) or 0.0) < 0.85
        )
        if not should_store:
            return

        descriptor = "high quality" if float(event.get("quality_score", 0.0) or 0.0) >= 0.82 else "degraded"
        memory_service.add_memory(
            content=(
                f"Execution {descriptor} on {symbol} via {broker} {order_type}. "
                f"Status {event.get('status')}, fill {float(event.get('fill_ratio', 0.0) or 0.0):.2f}, "
                f"slippage {float(event.get('slippage_bps', 0.0) or 0.0):.2f}bps."
            ),
            source="execution_quality_service",
            metadata={
                "memory_type": "execution",
                "ticker": symbol,
                "execution_id": execution_id or None,
                "broker": broker,
                "order_type": order_type,
                "session_bucket": session_bucket or None,
                "confidence": max(min(float(event.get("quality_score", 0.0) or 0.0), 0.95), 0.30),
                "sample_count": 1,
                "last_validated_at": event.get("filled_at") or event.get("created_at"),
                "execution_quality": float(event.get("quality_score", 0.0) or 0.0),
                "fill_ratio": event.get("fill_ratio"),
                "slippage_bps": event.get("slippage_bps"),
                "latency_ms": event.get("latency_ms"),
                "status": event.get("status"),
                "reason": event.get("reason"),
            },
        )

    @staticmethod
    def _build_model_key(parts: List[str]) -> str:
        return "|".join(parts)

    def rebuild_models(self) -> Dict[str, Any]:
        db = self._load()
        rows = list(db.get("events", []))
        if not rows:
            payload = {
                "status": "success",
                "model_count": 0,
                "events_used": 0,
                "models": [],
            }
            self._save_models(payload)
            return payload

        buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "dimensions": {},
                "samples": 0,
                "filled": 0,
                "rejected": 0,
                "pending": 0,
                "quality": [],
                "slippage": [],
                "latency": [],
                "fill_ratio": [],
                "time_to_fill": [],
            }
        )
        dimensions_list = [
            ("broker_order_type_session", ("broker", "order_type", "session_bucket"), 4),
            ("broker_order_type_symbol", ("broker", "order_type", "symbol"), 4),
            ("broker_order_type", ("broker", "order_type"), 5),
            ("broker", ("broker",), 6),
            ("symbol_order_type", ("symbol", "order_type"), 6),
            ("global_order_type", ("order_type",), 10),
        ]

        for row in rows:
            for model_type, dims, minimum_samples in dimensions_list:
                parts = [model_type]
                dim_map = {}
                valid = True
                for dim in dims:
                    value = str(row.get(dim) or "").strip()
                    if not value:
                        valid = False
                        break
                    dim_map[dim] = value
                    parts.append(value)
                if not valid:
                    continue
                key = self._build_model_key(parts)
                bucket = buckets[key]
                bucket["dimensions"] = {
                    "model_type": model_type,
                    "minimum_samples": minimum_samples,
                    **dim_map,
                }
                bucket["samples"] += 1
                bucket["filled"] += 1 if row.get("is_filled") else 0
                bucket["rejected"] += 1 if row.get("is_rejected") else 0
                bucket["pending"] += 1 if row.get("is_pending") else 0
                bucket["quality"].append(float(row.get("quality_score", 0.0) or 0.0))
                if row.get("slippage_bps") is not None:
                    bucket["slippage"].append(float(row.get("slippage_bps")))
                if row.get("latency_ms") is not None:
                    bucket["latency"].append(float(row.get("latency_ms")))
                if row.get("fill_ratio") is not None:
                    bucket["fill_ratio"].append(float(row.get("fill_ratio")))
                if row.get("time_to_fill_ms") is not None:
                    bucket["time_to_fill"].append(float(row.get("time_to_fill_ms")))

        models: List[Dict[str, Any]] = []
        for key, bucket in buckets.items():
            minimum_samples = int((bucket.get("dimensions") or {}).get("minimum_samples", 0) or 0)
            samples = int(bucket.get("samples", 0) or 0)
            if samples < minimum_samples:
                continue
            quality_score = float(np.mean(bucket["quality"])) if bucket["quality"] else 0.0
            reject_rate = bucket["rejected"] / max(samples, 1)
            pending_rate = bucket["pending"] / max(samples, 1)
            fill_rate = bucket["filled"] / max(samples, 1)
            avg_fill_ratio = float(np.mean(bucket["fill_ratio"])) if bucket["fill_ratio"] else 0.0
            confidence = float(
                np.clip(
                    (min(samples, 30) / 30.0) * (0.55 + max(quality_score, 0.0) * 0.45),
                    0.10,
                    1.0,
                )
            )
            models.append(
                {
                    "model_key": key,
                    "dimensions": bucket["dimensions"],
                    "sample_count": samples,
                    "fill_rate": round(fill_rate * 100.0, 2),
                    "reject_rate": round(reject_rate * 100.0, 2),
                    "pending_rate": round(pending_rate * 100.0, 2),
                    "avg_slippage_bps": round(float(np.mean(bucket["slippage"])) if bucket["slippage"] else 0.0, 4),
                    "avg_latency_ms": round(float(np.mean(bucket["latency"])) if bucket["latency"] else 0.0, 2),
                    "avg_fill_ratio": round(avg_fill_ratio, 4),
                    "avg_time_to_fill_ms": round(float(np.mean(bucket["time_to_fill"])) if bucket["time_to_fill"] else 0.0, 2),
                    "quality_score": round(quality_score, 4),
                    "confidence": round(confidence, 4),
                }
            )

        models.sort(
            key=lambda row: (
                -int(row.get("sample_count", 0) or 0),
                -float(row.get("confidence", 0.0) or 0.0),
                str((row.get("dimensions") or {}).get("model_type", "")),
            )
        )
        payload = {
            "status": "success",
            "model_count": len(models),
            "events_used": len(rows),
            "models": models,
        }
        self._save_models(payload)
        return payload

    def get_models(self, broker: Optional[str] = None, symbol: Optional[str] = None) -> Dict[str, Any]:
        payload = self._load_models()
        models = list(payload.get("models", []))
        if broker:
            models = [row for row in models if str((row.get("dimensions") or {}).get("broker", "")) == str(broker)]
        if symbol:
            models = [row for row in models if str((row.get("dimensions") or {}).get("symbol", "")) == str(symbol)]
        return {
            "status": "success",
            "updated_at": payload.get("updated_at"),
            "model_count": len(models),
            "models": models[:100],
        }

    def record_execution(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Any,
        status: str,
        source: str,
        broker: str,
        order_type: str = "MARKET",
        expected_price: Any = None,
        executed_price: Any = None,
        latency_ms: Any = None,
        filled_quantity: Any = None,
        filled_at: Optional[str] = None,
        signal_id: Optional[str] = None,
        broker_order_id: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = self._load()
        event = {
            "execution_id": f"EXE_{uuid.uuid4().hex[:12].upper()}",
            "created_at": created_at or self._utc_now(),
            "session_bucket": self._session_bucket(created_at),
            "symbol": str(symbol or "UNKNOWN"),
            "side": self._normalize_side(side),
            "quantity": self._safe_int(quantity) or 0,
            "status": self._normalize_status(status),
            "source": str(source or "unknown"),
            "broker": str(broker or "unknown"),
            "order_type": str(order_type or "MARKET").upper(),
            "expected_price": self._safe_float(expected_price),
            "executed_price": self._safe_float(executed_price),
            "latency_ms": self._safe_float(latency_ms),
            "filled_quantity": self._safe_float(filled_quantity),
            "filled_at": filled_at,
            "signal_id": str(signal_id) if signal_id else None,
            "broker_order_id": str(broker_order_id) if broker_order_id else None,
            "reason": str(reason) if reason else None,
            "metadata": metadata or {},
        }
        self._enrich_event(event)
        db["events"].append(event)
        self._save(db)
        self.rebuild_models()
        self._sync_execution_memory(event)
        return {"status": "success", "event": event}

    def save_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        db = self._load()
        signal_id = payload.get("signal_id")
        broker_order_id = payload.get("order_id") or payload.get("broker_order_id") or payload.get("execution_id")

        matched: Optional[Dict[str, Any]] = None
        for event in reversed(db.get("events", [])):
            if signal_id and str(event.get("signal_id")) == str(signal_id):
                matched = event
                break
            if broker_order_id and str(event.get("broker_order_id")) == str(broker_order_id):
                matched = event
                break

        if matched is None:
            result = self.record_execution(
                symbol=str(payload.get("symbol") or payload.get("ticker") or "UNKNOWN"),
                side=str(payload.get("side") or payload.get("action") or "UNKNOWN"),
                quantity=payload.get("quantity") or 0,
                status=str(payload.get("status") or "UNKNOWN"),
                source=str(payload.get("source") or "ea_feedback"),
                broker=str(payload.get("broker") or "external"),
                order_type=str(payload.get("order_type") or "MARKET"),
                expected_price=payload.get("expected_price") or payload.get("requested_price") or payload.get("entry"),
                executed_price=payload.get("executed_price") or payload.get("fill_price") or payload.get("price"),
                latency_ms=payload.get("latency_ms"),
                filled_quantity=payload.get("filled_quantity") or payload.get("filled_qty") or payload.get("quantity_filled") or payload.get("quantity"),
                filled_at=str(payload.get("filled_at") or payload.get("executed_at") or payload.get("timestamp") or self._utc_now()),
                signal_id=str(signal_id) if signal_id else None,
                broker_order_id=str(broker_order_id) if broker_order_id else None,
                reason=payload.get("reason") or payload.get("reject_reason") or payload.get("message"),
                metadata={"feedback_payload": payload},
                created_at=str(payload.get("executed_at") or payload.get("timestamp") or self._utc_now()),
            )
            return {"status": "success", "mode": "created", "event": result.get("event")}

        matched["status"] = self._normalize_status(payload.get("status") or matched.get("status"))
        matched["executed_price"] = self._safe_float(
            payload.get("executed_price") or payload.get("fill_price") or payload.get("price") or matched.get("executed_price")
        )
        matched["expected_price"] = self._safe_float(
            payload.get("expected_price") or payload.get("requested_price") or matched.get("expected_price")
        )
        matched["latency_ms"] = self._safe_float(payload.get("latency_ms") or matched.get("latency_ms"))
        matched["filled_quantity"] = self._safe_float(
            payload.get("filled_quantity") or payload.get("filled_qty") or payload.get("quantity_filled") or matched.get("filled_quantity")
        )
        matched["filled_at"] = str(
            payload.get("filled_at") or payload.get("executed_at") or payload.get("timestamp") or matched.get("filled_at") or ""
        ) or None
        matched["reason"] = str(
            payload.get("reason") or payload.get("reject_reason") or payload.get("message") or matched.get("reason") or ""
        ) or None
        matched["metadata"] = {**(matched.get("metadata") or {}), "feedback_payload": payload}
        self._enrich_event(matched)
        self._save(db)
        self.rebuild_models()
        self._sync_execution_memory(matched)
        return {"status": "success", "mode": "updated", "event": matched}

    def forecast_execution(
        self,
        *,
        symbol: str,
        side: str,
        broker: Optional[str] = None,
        order_type: str = "MARKET",
    ) -> Dict[str, Any]:
        db = self._load()
        rows = list(db.get("events", []))
        if not rows:
            return {
                "status": "success",
                "forecast": {
                    "sample_count": 0,
                    "basis": "none",
                    "session_bucket": self._session_bucket(),
                    "quality_score": 0.5,
                    "expected_slippage_bps": 0.0,
                    "expected_reject_rate": 0.0,
                    "expected_fill_ratio": 1.0,
                    "expected_time_to_fill_ms": 0.0,
                    "expected_latency_ms": 0.0,
                    "risk_multiplier": 1.0,
                    "recommendation": "no_history",
                },
            }

        symbol = str(symbol or "UNKNOWN")
        side = self._normalize_side(side)
        broker = str(broker or "").strip()
        order_type = str(order_type or "MARKET").upper()
        session_bucket = self._session_bucket()
        model_payload = self._load_models()
        model_rows = list(model_payload.get("models", []))

        model_filters = [
            ("broker_order_type_session", lambda r: (r.get("dimensions") or {}).get("broker") == broker and (r.get("dimensions") or {}).get("order_type") == order_type and (r.get("dimensions") or {}).get("session_bucket") == session_bucket),
            ("broker_order_type_symbol", lambda r: (r.get("dimensions") or {}).get("broker") == broker and (r.get("dimensions") or {}).get("order_type") == order_type and (r.get("dimensions") or {}).get("symbol") == symbol),
            ("broker_order_type", lambda r: (r.get("dimensions") or {}).get("broker") == broker and (r.get("dimensions") or {}).get("order_type") == order_type),
            ("broker", lambda r: (r.get("dimensions") or {}).get("broker") == broker),
            ("symbol_order_type", lambda r: (r.get("dimensions") or {}).get("symbol") == symbol and (r.get("dimensions") or {}).get("order_type") == order_type),
        ]
        selected_model = None
        selected_model_basis = None
        for basis, predicate in model_filters:
            subset = [row for row in model_rows if predicate(row)]
            if subset:
                subset.sort(key=lambda row: (-float(row.get("confidence", 0.0) or 0.0), -int(row.get("sample_count", 0) or 0)))
                selected_model = subset[0]
                selected_model_basis = basis
                break

        filters = [
            ("symbol+broker+session", lambda r: str(r.get("symbol")) == symbol and str(r.get("broker")) == broker and str(r.get("order_type")) == order_type and str(r.get("session_bucket")) == session_bucket, 4),
            ("symbol+broker", lambda r: str(r.get("symbol")) == symbol and str(r.get("broker")) == broker and str(r.get("order_type")) == order_type, 4),
            ("symbol+session", lambda r: str(r.get("symbol")) == symbol and str(r.get("order_type")) == order_type and str(r.get("session_bucket")) == session_bucket, 5),
            ("symbol", lambda r: str(r.get("symbol")) == symbol and str(r.get("order_type")) == order_type, 6),
            ("broker", lambda r: str(r.get("broker")) == broker and str(r.get("order_type")) == order_type, 8),
            ("global", lambda r: str(r.get("order_type")) == order_type, 10),
        ]

        selected_rows = rows
        selected_basis = "global_fallback"
        for basis, predicate, minimum in filters:
            subset = [row for row in rows if predicate(row)]
            if len(subset) >= minimum:
                selected_rows = subset
                selected_basis = basis
                break

        adverse_slippage = [
            max(float(row.get("slippage_bps", 0.0) or 0.0), 0.0)
            for row in selected_rows
            if row.get("slippage_bps") is not None
        ]
        reject_rate = sum(1 for row in selected_rows if bool(row.get("is_rejected"))) / max(len(selected_rows), 1)
        pending_rate = sum(1 for row in selected_rows if bool(row.get("is_pending"))) / max(len(selected_rows), 1)
        quality_score = float(np.mean([float(row.get("quality_score", 0.5) or 0.5) for row in selected_rows])) if selected_rows else 0.5
        latency_vals = [float(row.get("latency_ms")) for row in selected_rows if row.get("latency_ms") is not None]
        fill_ratio_vals = [float(row.get("fill_ratio", 1.0) or 0.0) for row in selected_rows if row.get("fill_ratio") is not None]
        time_to_fill_vals = [float(row.get("time_to_fill_ms")) for row in selected_rows if row.get("time_to_fill_ms") is not None]
        expected_slippage = float(np.mean(adverse_slippage)) if adverse_slippage else 0.0
        expected_latency = float(np.mean(latency_vals)) if latency_vals else 0.0
        expected_fill_ratio = float(np.mean(fill_ratio_vals)) if fill_ratio_vals else 1.0
        expected_time_to_fill = float(np.mean(time_to_fill_vals)) if time_to_fill_vals else 0.0

        model_confidence = float((selected_model or {}).get("confidence", 0.0) or 0.0)
        if selected_model:
            expected_slippage = expected_slippage * (1.0 - model_confidence) + float(selected_model.get("avg_slippage_bps", expected_slippage)) * model_confidence
            reject_rate = reject_rate * (1.0 - model_confidence) + (float(selected_model.get("reject_rate", reject_rate * 100.0)) / 100.0) * model_confidence
            pending_rate = pending_rate * (1.0 - model_confidence) + (float(selected_model.get("pending_rate", pending_rate * 100.0)) / 100.0) * model_confidence
            quality_score = quality_score * (1.0 - model_confidence) + float(selected_model.get("quality_score", quality_score)) * model_confidence
            expected_latency = expected_latency * (1.0 - model_confidence) + float(selected_model.get("avg_latency_ms", expected_latency)) * model_confidence
            expected_fill_ratio = expected_fill_ratio * (1.0 - model_confidence) + float(selected_model.get("avg_fill_ratio", expected_fill_ratio)) * model_confidence
            expected_time_to_fill = expected_time_to_fill * (1.0 - model_confidence) + float(selected_model.get("avg_time_to_fill_ms", expected_time_to_fill)) * model_confidence

        risk_multiplier = quality_score
        risk_multiplier *= max(0.35, 1.0 - reject_rate * 0.85)
        risk_multiplier *= max(0.45, 1.0 - pending_rate * 0.35)
        risk_multiplier *= max(0.40, expected_fill_ratio)
        risk_multiplier *= max(0.50, 1.0 - min(expected_slippage, 20.0) / 35.0)
        risk_multiplier *= max(0.55, 1.0 - min(expected_time_to_fill, 180000.0) / 240000.0)
        risk_multiplier = float(np.clip(risk_multiplier, 0.20, 1.0))

        recommendation = "normal"
        if reject_rate >= 0.30 or quality_score < 0.28:
            recommendation = "avoid"
        elif risk_multiplier < 0.72 or expected_slippage >= 8.0 or expected_fill_ratio < 0.85:
            recommendation = "reduce_size"

        return {
            "status": "success",
            "forecast": {
                "sample_count": int(len(selected_rows)),
                "basis": selected_basis,
                "model_basis": selected_model_basis,
                "model_confidence": round(model_confidence, 4),
                "session_bucket": session_bucket,
                "quality_score": round(quality_score, 4),
                "expected_slippage_bps": round(expected_slippage, 4),
                "expected_reject_rate": round(reject_rate * 100.0, 2),
                "expected_pending_rate": round(pending_rate * 100.0, 2),
                "expected_fill_ratio": round(expected_fill_ratio, 4),
                "expected_time_to_fill_ms": round(expected_time_to_fill, 2),
                "expected_latency_ms": round(expected_latency, 2),
                "risk_multiplier": round(risk_multiplier, 4),
                "recommendation": recommendation,
            },
        }

    def get_summary(self, ticker: Optional[str] = None) -> Dict[str, Any]:
        db = self._load()
        rows = db.get("events", [])
        if ticker:
            rows = [row for row in rows if str(row.get("symbol")) == str(ticker)]

        if not rows:
            return {
                "status": "success",
                "summary": {
                    "total_orders": 0,
                    "filled_orders": 0,
                    "pending_orders": 0,
                    "rejected_orders": 0,
                    "fill_rate": 0.0,
                    "reject_rate": 0.0,
                    "avg_slippage_bps": 0.0,
                    "avg_latency_ms": 0.0,
                    "avg_fill_ratio": 0.0,
                    "avg_time_to_fill_ms": 0.0,
                    "quality_score": 0.0,
                },
                "by_broker": [],
                "recent": [],
            }

        filled_rows = [row for row in rows if bool(row.get("is_filled"))]
        pending_rows = [row for row in rows if bool(row.get("is_pending"))]
        rejected_rows = [row for row in rows if bool(row.get("is_rejected"))]
        slippage_vals = [float(row["slippage_bps"]) for row in rows if row.get("slippage_bps") is not None]
        latency_vals = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
        fill_ratio_vals = [float(row["fill_ratio"]) for row in rows if row.get("fill_ratio") is not None]
        time_to_fill_vals = [float(row["time_to_fill_ms"]) for row in rows if row.get("time_to_fill_ms") is not None]
        quality_vals = [float(row.get("quality_score", 0.0) or 0.0) for row in rows]

        by_broker: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            broker = str(row.get("broker", "unknown"))
            bucket = by_broker.setdefault(
                broker,
                {"broker": broker, "orders": 0, "filled": 0, "rejected": 0, "slippage": [], "quality": [], "fill_ratio": [], "time_to_fill": []},
            )
            bucket["orders"] += 1
            bucket["filled"] += 1 if row.get("is_filled") else 0
            bucket["rejected"] += 1 if row.get("is_rejected") else 0
            if row.get("slippage_bps") is not None:
                bucket["slippage"].append(float(row["slippage_bps"]))
            if row.get("fill_ratio") is not None:
                bucket["fill_ratio"].append(float(row["fill_ratio"]))
            if row.get("time_to_fill_ms") is not None:
                bucket["time_to_fill"].append(float(row["time_to_fill_ms"]))
            bucket["quality"].append(float(row.get("quality_score", 0.0) or 0.0))

        broker_rows: List[Dict[str, Any]] = []
        for bucket in by_broker.values():
            orders = int(bucket["orders"])
            broker_rows.append(
                {
                    "broker": bucket["broker"],
                    "orders": orders,
                    "fill_rate": round((bucket["filled"] / max(orders, 1)) * 100.0, 2),
                    "reject_rate": round((bucket["rejected"] / max(orders, 1)) * 100.0, 2),
                    "avg_slippage_bps": round(float(np.mean(bucket["slippage"])) if bucket["slippage"] else 0.0, 4),
                    "avg_fill_ratio": round(float(np.mean(bucket["fill_ratio"])) if bucket["fill_ratio"] else 0.0, 4),
                    "avg_time_to_fill_ms": round(float(np.mean(bucket["time_to_fill"])) if bucket["time_to_fill"] else 0.0, 2),
                    "quality_score": round(float(np.mean(bucket["quality"])) if bucket["quality"] else 0.0, 4),
                }
            )
        broker_rows.sort(key=lambda x: (-x["orders"], x["broker"]))

        models_payload = self._load_models()
        return {
            "status": "success",
            "summary": {
                "total_orders": int(len(rows)),
                "filled_orders": int(len(filled_rows)),
                "pending_orders": int(len(pending_rows)),
                "rejected_orders": int(len(rejected_rows)),
                "fill_rate": round((len(filled_rows) / max(len(rows), 1)) * 100.0, 2),
                "reject_rate": round((len(rejected_rows) / max(len(rows), 1)) * 100.0, 2),
                "avg_slippage_bps": round(float(np.mean(slippage_vals)) if slippage_vals else 0.0, 4),
                "avg_latency_ms": round(float(np.mean(latency_vals)) if latency_vals else 0.0, 2),
                "avg_fill_ratio": round(float(np.mean(fill_ratio_vals)) if fill_ratio_vals else 0.0, 4),
                "avg_time_to_fill_ms": round(float(np.mean(time_to_fill_vals)) if time_to_fill_vals else 0.0, 2),
                "quality_score": round(float(np.mean(quality_vals)) if quality_vals else 0.0, 4),
            },
            "by_broker": broker_rows,
            "models": {
                "updated_at": models_payload.get("updated_at"),
                "model_count": int(len(models_payload.get("models", []))),
            },
            "recent": list(sorted(rows, key=lambda x: str(x.get("created_at")), reverse=True))[:100],
        }


execution_quality_service = ExecutionQualityService()
