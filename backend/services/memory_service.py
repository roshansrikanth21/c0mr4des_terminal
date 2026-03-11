from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Typed long-term memory with trust, drift, and maintenance controls.
    Local memory is primary. Remote memory is optional sync only.
    """

    VALID_TYPES = {"market", "strategy", "execution", "operator", "news"}
    HIGH_TRUST_SOURCES = {
        "pattern_learning_service",
        "live_signal_tracker",
        "execution_quality_service",
        "news_event_study_service",
    }
    MEDIUM_TRUST_SOURCES = {
        "news_ml_service",
        "regime_detector",
        "api_manual_write",
    }
    BUY_HINTS = {"buy", "bullish", "risk_on", "long", "target_hit", "win", "uptrend"}
    SELL_HINTS = {"sell", "bearish", "risk_off", "short", "stop_hit", "loss", "crash_warning", "downtrend"}

    def __init__(self) -> None:
        self.api_key = os.getenv("SUPERMEMORY_API_KEY")
        self.base_url = "https://api.supermemory.ai/v4"
        self.remote_enabled = bool(self.api_key)
        self.remote_search_enabled = os.getenv("MEMORY_REMOTE_SEARCH_ENABLED", "false").lower() == "true"
        self.container_tag = os.getenv("MEMORY_CONTAINER_TAG", "c0mr4de_terminal_v2")

        root = Path(__file__).resolve().parents[2]
        self.data_dir = root / "data" / "memory"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.data_dir / "memories.jsonl"
        self.max_local_records = max(int(os.getenv("MEMORY_MAX_LOCAL_RECORDS", "4000")), 250)
        self.maintenance_interval_sec = max(int(os.getenv("MEMORY_MAINTENANCE_INTERVAL_SEC", "600")), 60)
        self._last_maintenance_at: Optional[datetime] = None

        if not self.remote_enabled:
            logger.warning("SUPERMEMORY_API_KEY not found. MemoryService will use local memory only.")

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _utc_now_iso(cls) -> str:
        return cls._utc_now().isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
            if parsed != parsed:
                return float(default)
            return float(parsed)
        except Exception:
            return float(default)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return int(default)

    @staticmethod
    def _parse_ts(value: Any) -> Optional[datetime]:
        try:
            if value in {None, ""}:
                return None
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _default_expiry_days(memory_type: str) -> int:
        return {
            "market": 30,
            "strategy": 120,
            "execution": 90,
            "operator": 365,
            "news": 21,
        }.get(memory_type, 90)

    def _infer_memory_type(self, source: str, metadata: Dict[str, Any]) -> str:
        explicit = str(metadata.get("memory_type") or "").strip().lower()
        if explicit in self.VALID_TYPES:
            return explicit

        source_lower = str(source or "").strip().lower()
        if "regime" in source_lower or "market" in source_lower:
            return "market"
        if "news" in source_lower:
            return "news"
        if "execution" in source_lower or "broker" in source_lower:
            return "execution"
        if "operator" in source_lower or "auth" in source_lower:
            return "operator"
        return "strategy"

    def _base_trust_tier(self, source: str, memory_type: str, sample_count: int, metadata: Dict[str, Any]) -> str:
        explicit = str(metadata.get("trust_tier") or "").strip().lower()
        if explicit in {"low", "medium", "high"}:
            return explicit
        if source in self.HIGH_TRUST_SOURCES or sample_count >= 20:
            return "high"
        if source in self.MEDIUM_TRUST_SOURCES or memory_type in {"market", "news", "operator"}:
            return "medium"
        return "low"

    @staticmethod
    def _confidence_cap_for_tier(trust_tier: str) -> float:
        return {"low": 0.68, "medium": 0.82, "high": 0.98}.get(trust_tier, 0.68)

    @staticmethod
    def _validation_state(successes: int, failures: int) -> str:
        total = successes + failures
        if total <= 0:
            return "unvalidated"
        hit_rate = successes / max(total, 1)
        if hit_rate >= 0.7:
            return "verified"
        if hit_rate <= 0.4:
            return "drifting"
        return "mixed"

    @classmethod
    def _compute_freshness(
        cls,
        created_at: Optional[datetime],
        expires_at: Optional[datetime],
        last_validated_at: Optional[datetime],
    ) -> float:
        now = cls._utc_now()
        created = created_at or now
        if expires_at and expires_at <= now:
            return 0.0

        age_days = max((now - created).total_seconds() / 86400.0, 0.0)
        freshness = max(0.12, 1.0 - min(age_days / 160.0, 0.88))

        if last_validated_at:
            validated_age_days = max((now - last_validated_at).total_seconds() / 86400.0, 0.0)
            freshness *= max(0.48, 1.0 - min(validated_age_days / 90.0, 0.52))

        if expires_at:
            remaining = max((expires_at - now).total_seconds(), 0.0)
            total = max((expires_at - created).total_seconds(), 1.0)
            freshness *= max(0.20, min(1.0, remaining / total))

        return float(min(max(freshness, 0.0), 1.0))

    def _compute_trust_score(self, metadata: Dict[str, Any]) -> float:
        confidence = self._safe_float(metadata.get("confidence"), 0.0)
        freshness = self._safe_float(metadata.get("freshness_score"), 0.0)
        sample_count = min(self._safe_int(metadata.get("sample_count"), 1), 25) / 25.0
        success_count = self._safe_int(metadata.get("validation_success_count"), 0)
        failure_count = self._safe_int(metadata.get("validation_failure_count"), 0)
        validation_total = success_count + failure_count
        validation_quality = (success_count / max(validation_total, 1)) if validation_total > 0 else 0.35
        drift_score = self._safe_float(metadata.get("drift_score"), 0.0)
        trust_tier = str(metadata.get("trust_tier") or "low")
        tier_factor = {"low": 0.48, "medium": 0.70, "high": 0.88}.get(trust_tier, 0.48)

        trust_score = (
            confidence * 0.32
            + freshness * 0.24
            + sample_count * 0.14
            + validation_quality * 0.16
            + tier_factor * 0.14
            - drift_score * 0.28
        )
        return float(min(max(trust_score, 0.0), 1.0))

    @staticmethod
    def _memory_id(content: str, metadata: Dict[str, Any]) -> str:
        basis = json.dumps(
            {
                "content": content,
                "source": metadata.get("source"),
                "memory_type": metadata.get("memory_type"),
                "ticker": metadata.get("ticker"),
                "interval": metadata.get("interval"),
                "created_at": metadata.get("created_at"),
            },
            sort_keys=True,
        )
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]

    def _refresh_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        local = dict(metadata or {})
        created_at = self._parse_ts(local.get("created_at")) or self._utc_now()
        expires_at = self._parse_ts(local.get("expires_at")) or (created_at + timedelta(days=self._default_expiry_days(str(local.get("memory_type") or "strategy"))))
        last_validated_at = self._parse_ts(local.get("last_validated_at"))
        success_count = max(self._safe_int(local.get("validation_success_count"), 0), 0)
        failure_count = max(self._safe_int(local.get("validation_failure_count"), 0), 0)
        validation_count = max(self._safe_int(local.get("validation_count"), success_count + failure_count), success_count + failure_count)
        trust_tier = str(local.get("trust_tier") or "low").lower()
        if trust_tier not in {"low", "medium", "high"}:
            trust_tier = "low"

        freshness_score = self._compute_freshness(created_at, expires_at, last_validated_at)
        drift_score = float(min(max(failure_count / max(validation_count, 1), 0.0), 1.0)) if validation_count else 0.08
        validation_state = self._validation_state(success_count, failure_count)
        confidence_cap = self._confidence_cap_for_tier(trust_tier)
        confidence = min(max(self._safe_float(local.get("confidence"), 0.55), 0.0), confidence_cap)

        refreshed = {
            **local,
            "confidence": round(confidence, 4),
            "sample_count": max(self._safe_int(local.get("sample_count"), 1), 1),
            "validation_count": validation_count,
            "validation_success_count": success_count,
            "validation_failure_count": failure_count,
            "validation_state": validation_state,
            "trust_tier": trust_tier,
            "freshness_score": round(freshness_score, 4),
            "drift_score": round(drift_score, 4),
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "last_validated_at": last_validated_at.isoformat().replace("+00:00", "Z") if last_validated_at else None,
        }
        refreshed["trust_score"] = round(self._compute_trust_score(refreshed), 4)
        return refreshed

    def _normalize_metadata(self, source: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        local = dict(metadata or {})
        memory_type = self._infer_memory_type(source, local)
        sample_count = max(self._safe_int(local.get("sample_count"), 1), 1)
        trust_tier = self._base_trust_tier(source, memory_type, sample_count, local)
        confidence_cap = self._confidence_cap_for_tier(trust_tier)
        confidence = min(max(self._safe_float(local.get("confidence"), 0.55), 0.0), confidence_cap)

        created_at = self._parse_ts(local.get("created_at")) or self._utc_now()
        expires_at = self._parse_ts(local.get("expires_at")) or (created_at + timedelta(days=self._default_expiry_days(memory_type)))
        last_validated_at = self._parse_ts(local.get("last_validated_at"))
        if last_validated_at is None and memory_type in {"strategy", "execution", "news"} and trust_tier != "low":
            last_validated_at = created_at

        normalized = {
            **local,
            "source": source,
            "memory_type": memory_type,
            "ticker": str(local.get("ticker") or "").strip() or None,
            "interval": str(local.get("interval") or "").strip() or None,
            "regime": str(local.get("regime") or local.get("primary_regime") or "").strip() or None,
            "session_bucket": str(local.get("session_bucket") or "").strip() or None,
            "setup_family": str(local.get("setup_family") or "").strip() or None,
            "confidence": round(confidence, 4),
            "sample_count": sample_count,
            "trust_tier": trust_tier,
            "validation_count": max(self._safe_int(local.get("validation_count"), 0), 0),
            "validation_success_count": max(self._safe_int(local.get("validation_success_count"), 0), 0),
            "validation_failure_count": max(self._safe_int(local.get("validation_failure_count"), 0), 0),
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "last_validated_at": last_validated_at.isoformat().replace("+00:00", "Z") if last_validated_at else None,
        }
        return self._refresh_metadata(normalized)

    def _load_local_memories(self) -> List[Dict[str, Any]]:
        if not self.store_path.exists():
            return []

        rows: List[Dict[str, Any]] = []
        try:
            for line in self.store_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                payload["metadata"] = self._refresh_metadata(payload.get("metadata") or {})
                rows.append(payload)
        except Exception as exc:
            logger.error("Failed to load memory store: %s", exc)
            return []
        return rows

    def _rewrite_store(self, rows: List[Dict[str, Any]]) -> None:
        serialized = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
        if serialized:
            serialized += "\n"
        self.store_path.write_text(serialized, encoding="utf-8")

    def _prune_if_needed(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        local_rows = rows if rows is not None else self._load_local_memories()
        if len(local_rows) <= self.max_local_records:
            return

        def score(row: Dict[str, Any]) -> float:
            metadata = row.get("metadata") or {}
            return (
                self._safe_float(metadata.get("trust_score"), 0.5) * 0.55
                + self._safe_float(metadata.get("freshness_score"), 0.5) * 0.25
                + min(self._safe_int(metadata.get("sample_count"), 1), 25) / 25.0 * 0.20
            )

        local_rows.sort(key=score, reverse=True)
        self._rewrite_store(local_rows[: self.max_local_records])

    def _append_local(self, payload: Dict[str, Any]) -> None:
        with self.store_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")

        if sum(1 for _ in self.store_path.open("r", encoding="utf-8")) > self.max_local_records + 100:
            self._prune_if_needed()

    def _sync_remote(self, content: str, metadata: Dict[str, Any]) -> bool:
        if not self.remote_enabled:
            return False

        try:
            payload = {
                "memories": [
                    {
                        "content": content,
                        "metadata": metadata,
                    }
                ],
                "containerTag": self.container_tag,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            response = requests.post(f"{self.base_url}/memories", json=payload, headers=headers, timeout=6)
            return response.status_code in {200, 201}
        except Exception as exc:
            logger.warning("Remote memory sync failed: %s", exc)
            return False

    def _maybe_run_maintenance(self) -> None:
        now = self._utc_now()
        if self._last_maintenance_at and (now - self._last_maintenance_at).total_seconds() < self.maintenance_interval_sec:
            return
        try:
            self.run_maintenance()
        except Exception as exc:
            logger.warning("Memory maintenance skipped after failure: %s", exc)

    @staticmethod
    def _tokenize(value: str) -> List[str]:
        return [token for token in re.split(r"[^a-z0-9_]+", str(value or "").lower()) if token]

    def _record_search_text(self, row: Dict[str, Any]) -> str:
        metadata = row.get("metadata") or {}
        parts = [
            row.get("content") or "",
            metadata.get("memory_type") or "",
            metadata.get("ticker") or "",
            metadata.get("interval") or "",
            metadata.get("title") or "",
            metadata.get("event_id") or "",
            metadata.get("execution_id") or "",
            metadata.get("url") or "",
            metadata.get("broker") or "",
            metadata.get("order_type") or "",
            metadata.get("regime") or "",
            metadata.get("session_bucket") or "",
            metadata.get("setup_family") or "",
            metadata.get("market_direction") or "",
            metadata.get("primary_regime") or "",
            metadata.get("secondary_regime") or "",
            metadata.get("validation_state") or "",
        ]
        return " ".join(str(part) for part in parts if part)

    def _scope_match_score(
        self,
        metadata: Dict[str, Any],
        *,
        memory_type: Optional[str],
        ticker: Optional[str],
        interval: Optional[str],
        regime: Optional[str],
        session_bucket: Optional[str],
        setup_family: Optional[str],
    ) -> float:
        score = 0.0
        if memory_type and str(metadata.get("memory_type")) == memory_type:
            score += 0.16
        if ticker and str(metadata.get("ticker")) == ticker:
            score += 0.22
        if interval and str(metadata.get("interval")) == interval:
            score += 0.10
        if regime and str(metadata.get("regime") or "").lower() == regime.lower():
            score += 0.12
        if session_bucket and str(metadata.get("session_bucket") or "").lower() == session_bucket.lower():
            score += 0.08
        if setup_family and str(metadata.get("setup_family") or "").lower() == setup_family.lower():
            score += 0.16
        return score

    def _query_similarity(self, query_terms: List[str], search_text: str) -> float:
        if not query_terms:
            return 0.0
        tokens = set(self._tokenize(search_text))
        if not tokens:
            return 0.0
        hits = sum(1 for term in query_terms if term in tokens)
        return hits / max(len(set(query_terms)), 1)

    @classmethod
    def _directional_hint(cls, row: Dict[str, Any]) -> float:
        metadata = row.get("metadata") or {}
        hints = [
            str(metadata.get("direction") or ""),
            str(metadata.get("market_direction") or ""),
            str(metadata.get("primary_regime") or ""),
            str(metadata.get("outcome") or ""),
            row.get("content") or "",
        ]
        net = 0.0
        for hint in hints:
            tokens = set(cls._tokenize(hint))
            if tokens & cls.BUY_HINTS:
                net += 1.0
            if tokens & cls.SELL_HINTS:
                net -= 1.0
        return float(max(min(net / 3.0, 1.0), -1.0))

    def add_memory(
        self,
        content: str,
        source: str = "c0mr4de_terminal",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not content or not str(content).strip():
            return False

        self._maybe_run_maintenance()
        normalized = self._normalize_metadata(source, metadata)
        payload = {
            "memory_id": self._memory_id(content, normalized),
            "content": str(content).strip(),
            "source": source,
            "created_at": normalized.get("created_at"),
            "metadata": normalized,
        }

        try:
            self._append_local(payload)
        except Exception as exc:
            logger.error("Failed to write local memory: %s", exc)
            return False

        self._sync_remote(payload["content"], normalized)
        return True

    def record_validation(
        self,
        *,
        memory_id: str,
        outcome: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rows = self._load_local_memories()
        normalized_outcome = str(outcome or "failure").strip().lower()
        if normalized_outcome not in {"success", "failure"}:
            normalized_outcome = "failure"

        for row in rows:
            if str(row.get("memory_id")) != str(memory_id):
                continue
            metadata = row.get("metadata") or {}
            if normalized_outcome == "success":
                metadata["validation_success_count"] = self._safe_int(metadata.get("validation_success_count"), 0) + 1
            else:
                metadata["validation_failure_count"] = self._safe_int(metadata.get("validation_failure_count"), 0) + 1
            metadata["validation_count"] = (
                self._safe_int(metadata.get("validation_success_count"), 0)
                + self._safe_int(metadata.get("validation_failure_count"), 0)
            )
            metadata["last_validated_at"] = self._utc_now_iso()
            if details:
                metadata["last_validation"] = details
            row["metadata"] = self._refresh_metadata(metadata)
            self._rewrite_store(rows)
            return {"status": "success", "memory": row}

        return {"status": "error", "message": f"Memory not found: {memory_id}"}

    def retrieve_memories(
        self,
        *,
        query: str = "",
        limit: int = 5,
        memory_type: Optional[str] = None,
        ticker: Optional[str] = None,
        interval: Optional[str] = None,
        regime: Optional[str] = None,
        session_bucket: Optional[str] = None,
        setup_family: Optional[str] = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> Dict[str, Any]:
        self._maybe_run_maintenance()
        query_terms = self._tokenize(query)
        rows = self._load_local_memories()
        now = self._utc_now()
        results: List[Dict[str, Any]] = []

        for row in rows:
            metadata = row.get("metadata") or {}
            effective_confidence = self._safe_float(metadata.get("trust_score"), 0.0)
            if effective_confidence < min_confidence:
                continue
            if memory_type and str(metadata.get("memory_type")) != memory_type:
                continue
            if ticker and str(metadata.get("ticker") or "") not in {"", ticker}:
                continue
            if interval and str(metadata.get("interval") or "") not in {"", interval}:
                continue
            if regime and str(metadata.get("regime") or "").lower() not in {"", regime.lower()}:
                continue
            if session_bucket and str(metadata.get("session_bucket") or "").lower() not in {"", session_bucket.lower()}:
                continue
            if setup_family and str(metadata.get("setup_family") or "").lower() not in {"", setup_family.lower()}:
                continue

            expires_at = self._parse_ts(metadata.get("expires_at"))
            if not include_expired and expires_at and expires_at <= now:
                continue

            search_text = self._record_search_text(row)
            score = (
                self._query_similarity(query_terms, search_text) * 0.26
                + self._scope_match_score(
                    metadata,
                    memory_type=memory_type,
                    ticker=ticker,
                    interval=interval,
                    regime=regime,
                    session_bucket=session_bucket,
                    setup_family=setup_family,
                )
                + self._safe_float(metadata.get("trust_score"), 0.55) * 0.26
                + self._safe_float(metadata.get("freshness_score"), 0.55) * 0.14
                + min(self._safe_int(metadata.get("sample_count"), 1), 25) / 25.0 * 0.08
                - self._safe_float(metadata.get("drift_score"), 0.0) * 0.12
            )

            results.append(
                {
                    "memory_id": row.get("memory_id"),
                    "content": row.get("content"),
                    "source": row.get("source"),
                    "created_at": row.get("created_at"),
                    "metadata": metadata,
                    "similarity": round(score, 4),
                    "directional_hint": round(self._directional_hint(row), 4),
                }
            )

        results.sort(key=lambda item: item.get("similarity", 0.0), reverse=True)
        limited = results[: max(int(limit), 1)]
        return {"status": "success", "query": query, "count": len(limited), "memories": limited}

    def build_context(
        self,
        *,
        ticker: str,
        interval: str,
        regime: Optional[str] = None,
        session_bucket: Optional[str] = None,
        setup_family: Optional[str] = None,
        query: str = "",
        limit: int = 6,
    ) -> Dict[str, Any]:
        result = self.retrieve_memories(
            query=query,
            limit=limit,
            ticker=ticker,
            interval=interval,
            regime=regime,
            session_bucket=session_bucket,
            setup_family=setup_family,
            min_confidence=0.12,
        )
        memories = list(result.get("memories", []) or [])

        if not memories:
            return {
                "status": "success",
                "query": query,
                "retrieved": [],
                "influence": {
                    "memory_count": 0,
                    "alignment_bias": 0.0,
                    "risk_bias": 0.0,
                    "average_confidence": 0.0,
                    "average_freshness": 0.0,
                    "average_trust": 0.0,
                    "average_drift": 0.0,
                    "component_hints": {},
                    "notes": ["No scoped memory matches were available."],
                },
            }

        avg_confidence = sum(self._safe_float((item.get("metadata") or {}).get("confidence"), 0.0) for item in memories) / max(len(memories), 1)
        avg_freshness = sum(self._safe_float((item.get("metadata") or {}).get("freshness_score"), 0.0) for item in memories) / max(len(memories), 1)
        avg_trust = sum(self._safe_float((item.get("metadata") or {}).get("trust_score"), 0.0) for item in memories) / max(len(memories), 1)
        avg_drift = sum(self._safe_float((item.get("metadata") or {}).get("drift_score"), 0.0) for item in memories) / max(len(memories), 1)
        alignment_bias = sum(
            self._safe_float(item.get("directional_hint"), 0.0) * self._safe_float((item.get("metadata") or {}).get("trust_score"), 0.0)
            for item in memories
        )
        weight_norm = sum(self._safe_float((item.get("metadata") or {}).get("trust_score"), 0.0) for item in memories) or 1.0
        alignment_bias = float(max(min(alignment_bias / weight_norm, 1.0), -1.0))

        by_type: Dict[str, int] = {}
        by_trust: Dict[str, int] = {}
        component_hints = {
            "strategy": 1.0,
            "news": 1.0,
            "regime": 1.0,
            "quant": 1.0,
            "ml_confirmation": 1.0,
        }
        notes: List[str] = []
        risk_bias = 0.0

        for item in memories:
            metadata = item.get("metadata") or {}
            mtype = str(metadata.get("memory_type") or "strategy")
            trust_tier = str(metadata.get("trust_tier") or "low")
            by_type[mtype] = by_type.get(mtype, 0) + 1
            by_trust[trust_tier] = by_trust.get(trust_tier, 0) + 1
            directional_hint = self._safe_float(item.get("directional_hint"), 0.0)
            trust_score = self._safe_float(metadata.get("trust_score"), 0.0)
            drift_score = self._safe_float(metadata.get("drift_score"), 0.0)

            if mtype == "strategy":
                component_hints["strategy"] *= 1.0 + min(0.08, abs(directional_hint) * trust_score * 0.08)
            elif mtype == "news":
                component_hints["news"] *= 1.0 + min(0.06, abs(directional_hint) * trust_score * 0.06)
                risk_bias += self._safe_float(metadata.get("affect_rate"), 0.0) / 1000.0
            elif mtype == "market":
                component_hints["regime"] *= 1.0 + min(0.05, trust_score * 0.05)
            elif mtype == "execution":
                component_hints["strategy"] *= 0.98
                risk_bias += (1.0 - self._safe_float(metadata.get("execution_quality"), trust_score)) * 0.08

            risk_bias += drift_score * 0.04

        if by_type.get("strategy", 0) >= 2:
            notes.append("Strategy memory found multiple scoped historical setup references.")
        if by_type.get("news", 0) >= 1:
            notes.append("News memory contributed event context for the current ticker scope.")
        if by_type.get("market", 0) >= 1:
            notes.append("Market memory contributed prior regime context.")
        if by_trust.get("high", 0) == 0 and memories:
            notes.append("No high-trust memories matched; context should be treated as secondary.")
        if avg_drift >= 0.35:
            notes.append("Matched memories show drift and were downranked.")

        return {
            "status": "success",
            "query": query,
            "retrieved": memories,
            "influence": {
                "memory_count": len(memories),
                "average_confidence": round(avg_confidence, 4),
                "average_freshness": round(avg_freshness, 4),
                "average_trust": round(avg_trust, 4),
                "average_drift": round(avg_drift, 4),
                "alignment_bias": round(alignment_bias, 4),
                "risk_bias": round(max(min(risk_bias, 0.18), -0.18), 4),
                "memory_type_counts": by_type,
                "trust_tier_counts": by_trust,
                "component_hints": {key: round(value, 4) for key, value in component_hints.items()},
                "notes": notes or ["Scoped memories were retrieved and attached as advisory context."],
            },
        }

    def query_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        local = self.retrieve_memories(query=query, limit=limit)
        results = list(local.get("memories", []) or [])
        if results or not (self.remote_enabled and self.remote_search_enabled):
            return results

        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"q": query, "containerTag": self.container_tag, "limit": limit}
            response = requests.post(f"{self.base_url}/search", json=payload, headers=headers, timeout=6)
            if response.status_code != 200:
                return results
            data = response.json()
            raw_results = data if isinstance(data, list) else data.get("memories", data.get("results", []))
            for item in raw_results or []:
                if not isinstance(item, dict):
                    continue
                results.append(
                    {
                        "memory_id": item.get("id"),
                        "content": item.get("content") or item.get("text"),
                        "source": "supermemory_remote",
                        "created_at": None,
                        "metadata": item.get("metadata", {}),
                        "similarity": self._safe_float(item.get("similarity"), 0.5),
                        "directional_hint": 0.0,
                    }
                )
        except Exception as exc:
            logger.warning("Remote memory search failed: %s", exc)
        return results[: max(int(limit), 1)]

    def run_maintenance(self) -> Dict[str, Any]:
        rows = self._load_local_memories()
        if not rows:
            self._last_maintenance_at = self._utc_now()
            return {"status": "success", "updated": 0, "pruned": 0, "remaining": 0}

        now = self._utc_now()
        refreshed_rows: List[Dict[str, Any]] = []
        pruned = 0
        for row in rows:
            metadata = self._refresh_metadata(row.get("metadata") or {})
            expires_at = self._parse_ts(metadata.get("expires_at"))
            trust_score = self._safe_float(metadata.get("trust_score"), 0.0)
            age_validated = self._parse_ts(metadata.get("last_validated_at"))

            should_prune = False
            if expires_at and expires_at <= now and trust_score < 0.35:
                should_prune = True
            if age_validated and (now - age_validated).days > 180 and trust_score < 0.28:
                should_prune = True
            if should_prune:
                pruned += 1
                continue

            refreshed_rows.append({**row, "metadata": metadata})

        refreshed_rows.sort(
            key=lambda row: (
                -self._safe_float((row.get("metadata") or {}).get("trust_score"), 0.0),
                -self._safe_float((row.get("metadata") or {}).get("freshness_score"), 0.0),
                -self._safe_int((row.get("metadata") or {}).get("sample_count"), 0),
            )
        )
        if len(refreshed_rows) > self.max_local_records:
            pruned += max(len(refreshed_rows) - self.max_local_records, 0)
            refreshed_rows = refreshed_rows[: self.max_local_records]

        self._rewrite_store(refreshed_rows)
        self._last_maintenance_at = self._utc_now()
        return {
            "status": "success",
            "updated": len(refreshed_rows),
            "pruned": pruned,
            "remaining": len(refreshed_rows),
            "last_maintenance_at": self._utc_now_iso(),
        }

    def get_research_snapshot(self, ticker: Optional[str] = None, interval: Optional[str] = None) -> Dict[str, Any]:
        rows = self._load_local_memories()
        filtered: List[Dict[str, Any]] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            if ticker and str(metadata.get("ticker") or "") not in {"", ticker}:
                continue
            if interval and str(metadata.get("interval") or "") not in {"", interval}:
                continue
            filtered.append(row)

        trust_buckets = {"high": 0, "medium": 0, "low": 0}
        validation_buckets: Dict[str, int] = {}
        type_rows: Dict[str, Dict[str, float]] = {}
        drift_rows: List[Dict[str, Any]] = []

        for row in filtered:
            metadata = row.get("metadata") or {}
            trust_tier = str(metadata.get("trust_tier") or "low")
            validation_state = str(metadata.get("validation_state") or "unvalidated")
            trust_buckets[trust_tier] = trust_buckets.get(trust_tier, 0) + 1
            validation_buckets[validation_state] = validation_buckets.get(validation_state, 0) + 1

            memory_type = str(metadata.get("memory_type") or "strategy")
            bucket = type_rows.setdefault(memory_type, {"count": 0, "trust_sum": 0.0, "drift_sum": 0.0})
            bucket["count"] += 1
            bucket["trust_sum"] += self._safe_float(metadata.get("trust_score"), 0.0)
            bucket["drift_sum"] += self._safe_float(metadata.get("drift_score"), 0.0)

            drift_score = self._safe_float(metadata.get("drift_score"), 0.0)
            if drift_score >= 0.25:
                drift_rows.append(
                    {
                        "memory_id": row.get("memory_id"),
                        "content": row.get("content"),
                        "source": row.get("source"),
                        "memory_type": memory_type,
                        "ticker": metadata.get("ticker"),
                        "interval": metadata.get("interval"),
                        "trust_tier": trust_tier,
                        "trust_score": round(self._safe_float(metadata.get("trust_score"), 0.0), 4),
                        "drift_score": round(drift_score, 4),
                        "validation_state": validation_state,
                    }
                )

        type_summary = [
            {
                "memory_type": memory_type,
                "count": int(values["count"]),
                "avg_trust_score": round(values["trust_sum"] / max(values["count"], 1), 4),
                "avg_drift_score": round(values["drift_sum"] / max(values["count"], 1), 4),
            }
            for memory_type, values in type_rows.items()
        ]
        type_summary.sort(key=lambda row: (-row["count"], row["memory_type"]))
        drift_rows.sort(key=lambda row: (-row["drift_score"], row["memory_type"], row["source"]))

        return {
            "status": "success",
            "ticker": ticker,
            "interval": interval,
            "total_memories": len(filtered),
            "trust_tiers": trust_buckets,
            "validation_states": validation_buckets,
            "type_summary": type_summary,
            "drifted_memories": drift_rows[:20],
            "last_maintenance_at": self._last_maintenance_at.isoformat().replace("+00:00", "Z") if self._last_maintenance_at else None,
        }

    def get_runtime_status(self) -> Dict[str, Any]:
        rows = self._load_local_memories()
        active = 0
        expired = 0
        by_type: Dict[str, int] = {}
        trust_tiers = {"high": 0, "medium": 0, "low": 0}
        validation_states: Dict[str, int] = {}
        now = self._utc_now()

        for row in rows:
            metadata = row.get("metadata") or {}
            expires_at = self._parse_ts(metadata.get("expires_at"))
            if expires_at and expires_at <= now:
                expired += 1
            else:
                active += 1

            mtype = str(metadata.get("memory_type") or "strategy")
            trust_tier = str(metadata.get("trust_tier") or "low")
            validation_state = str(metadata.get("validation_state") or "unvalidated")
            by_type[mtype] = by_type.get(mtype, 0) + 1
            trust_tiers[trust_tier] = trust_tiers.get(trust_tier, 0) + 1
            validation_states[validation_state] = validation_states.get(validation_state, 0) + 1

        avg_trust = (
            sum(self._safe_float((row.get("metadata") or {}).get("trust_score"), 0.0) for row in rows) / max(len(rows), 1)
            if rows else 0.0
        )
        avg_drift = (
            sum(self._safe_float((row.get("metadata") or {}).get("drift_score"), 0.0) for row in rows) / max(len(rows), 1)
            if rows else 0.0
        )

        return {
            "status": "success",
            "local_store_path": str(self.store_path),
            "remote_enabled": self.remote_enabled,
            "remote_search_enabled": self.remote_search_enabled,
            "active_memories": active,
            "expired_memories": expired,
            "memory_type_counts": by_type,
            "trust_tier_counts": trust_tiers,
            "validation_state_counts": validation_states,
            "avg_trust_score": round(avg_trust, 4),
            "avg_drift_score": round(avg_drift, 4),
            "max_local_records": self.max_local_records,
            "last_maintenance_at": self._last_maintenance_at.isoformat().replace("+00:00", "Z") if self._last_maintenance_at else None,
        }


memory_service = MemoryService()
