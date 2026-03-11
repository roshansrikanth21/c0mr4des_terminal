from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np

from backend.broker.angel_one_broker import ANGEL_ONE_AVAILABLE
from backend.broker.paper_broker import PaperBroker
from backend.services.execution_quality_service import execution_quality_service
from backend.services.market_data_service import async_market_data_service
from backend.services.ops_control_service import ops_control_service
from backend.services.service_manager import service_manager


class RoutingService:
    """
    Scores execution brokers and market-data providers so the system can prefer
    stronger routes and avoid obviously degraded paths.
    """

    def _build_broker_rows(self) -> List[Dict[str, Any]]:
        exec_engine = service_manager.execution_engine
        current_broker_name = type(exec_engine.broker).__name__
        quality_summary = execution_quality_service.get_summary()
        by_broker = {
            str(row.get("broker")): row
            for row in (quality_summary.get("by_broker") or [])
        }

        angel_credentials_ready = bool(
            os.getenv("ANGEL_API_KEY")
            and os.getenv("ANGEL_CLIENT_ID")
            and os.getenv("ANGEL_PASSWORD")
            and os.getenv("ANGEL_TOTP_KEY")
        )
        broker_candidates: List[Dict[str, Any]] = [
            {
                "broker": "PaperBroker",
                "mode": "PAPER",
                "available": True,
                "current": current_broker_name == "PaperBroker",
                "live": False,
                "credentials_ready": True,
            },
            {
                "broker": "AngelOneBroker",
                "mode": "ANGEL_ONE",
                "available": bool(
                    ANGEL_ONE_AVAILABLE
                    and angel_credentials_ready
                ),
                "current": current_broker_name == "AngelOneBroker",
                "live": True,
                "credentials_ready": angel_credentials_ready,
            },
        ]

        rows: List[Dict[str, Any]] = []
        for candidate in broker_candidates:
            quality = by_broker.get(candidate["broker"], {})
            score = 0.55 if candidate["available"] else 0.10
            if candidate["current"]:
                score += 0.06
            if candidate["live"]:
                score += 0.04
            score += float(quality.get("quality_score", 0.5) or 0.5) * 0.28
            score -= min(float(quality.get("reject_rate", 0.0) or 0.0) / 100.0, 0.35)
            score -= min(max(float(quality.get("avg_slippage_bps", 0.0) or 0.0), 0.0) / 35.0, 0.22)
            score -= max(0.0, 1.0 - float(quality.get("avg_fill_ratio", 1.0) or 1.0)) * 0.18
            score -= min(max(float(quality.get("avg_time_to_fill_ms", 0.0) or 0.0), 0.0) / 180000.0, 0.16)
            if candidate["live"] and not candidate["credentials_ready"]:
                score -= 0.20
            recommendation = "use"
            if not candidate["available"]:
                recommendation = "unavailable"
            elif float(quality.get("reject_rate", 0.0) or 0.0) >= 20.0:
                recommendation = "avoid"
            elif float(quality.get("quality_score", 0.5) or 0.5) < 0.40 and int(quality.get("orders", 0) or 0) >= 5:
                recommendation = "avoid"
            elif float(quality.get("avg_fill_ratio", 1.0) or 1.0) < 0.82 and int(quality.get("orders", 0) or 0) >= 5:
                recommendation = "avoid"
            elif float(quality.get("avg_slippage_bps", 0.0) or 0.0) >= 10.0:
                recommendation = "reduce_size"
            elif float(quality.get("avg_time_to_fill_ms", 0.0) or 0.0) >= 90000:
                recommendation = "reduce_size"
            rows.append(
                {
                    **candidate,
                    "score": round(float(np.clip(score, 0.0, 1.0)), 4),
                    "orders": int(quality.get("orders", 0) or 0),
                    "fill_rate": float(quality.get("fill_rate", 0.0) or 0.0),
                    "reject_rate": float(quality.get("reject_rate", 0.0) or 0.0),
                    "avg_slippage_bps": float(quality.get("avg_slippage_bps", 0.0) or 0.0),
                    "avg_fill_ratio": float(quality.get("avg_fill_ratio", 0.0) or 0.0),
                    "avg_time_to_fill_ms": float(quality.get("avg_time_to_fill_ms", 0.0) or 0.0),
                    "quality_score": float(quality.get("quality_score", 0.0) or 0.0),
                    "recommendation": recommendation,
                }
            )
        rows.sort(key=lambda x: (-x["score"], x["broker"]))
        return rows

    def _build_provider_rows(self) -> List[Dict[str, Any]]:
        rows = list(async_market_data_service.get_provider_status() or [])
        rows.sort(key=lambda x: (-float(x.get("route_score", 0.0) or 0.0), int(x.get("priority", 99) or 99)))
        for row in rows:
            recommendation = "use"
            if row.get("cooled_down"):
                recommendation = "cooldown"
            elif not row.get("connected", True) and row.get("priority", 9) == 0:
                recommendation = "degraded"
            elif float(row.get("route_score", 0.0) or 0.0) < 0.38:
                recommendation = "avoid"
            row["recommendation"] = recommendation
        return rows

    def get_routing_snapshot(self, ticker: str = "^NSEI") -> Dict[str, Any]:
        broker_rows = self._build_broker_rows()
        provider_rows = self._build_provider_rows()
        best_broker = broker_rows[0] if broker_rows else None
        best_provider = provider_rows[0] if provider_rows else None

        notes: List[str] = []
        if best_broker:
            notes.append(
                f"Execution route: {best_broker['broker']} ({best_broker['recommendation']}, score={best_broker['score']:.2f})"
            )
        if best_provider:
            notes.append(
                f"Data route: {best_provider['provider']} ({best_provider['recommendation']}, score={float(best_provider.get('route_score', 0.0)):.2f})"
            )

        return {
            "status": "success",
            "ticker": ticker,
            "execution_brokers": broker_rows,
            "market_data_providers": provider_rows,
            "recommended_execution_broker": best_broker,
            "recommended_market_data_provider": best_provider,
            "notes": notes,
        }

    def get_execution_directive(self, ticker: str = "^NSEI") -> Dict[str, Any]:
        snapshot = self.get_routing_snapshot(ticker=ticker)
        current_broker_name = type(service_manager.execution_engine.broker).__name__
        recommended = snapshot.get("recommended_execution_broker") or {}
        current_row = next(
            (row for row in (snapshot.get("execution_brokers") or []) if row.get("broker") == current_broker_name),
            None,
        )

        directive = "proceed"
        reason = "Current broker route is acceptable."
        if current_row and current_row.get("recommendation") == "avoid":
            directive = "halt"
            reason = f"Current broker {current_broker_name} is degraded."
        elif current_row and current_row.get("recommendation") == "reduce_size":
            directive = "reduce_size"
            reason = f"Current broker {current_broker_name} has elevated slippage or rejects."
        elif recommended and recommended.get("broker") != current_broker_name and recommended.get("score", 0) > (current_row or {}).get("score", 0) + 0.12:
            directive = "prefer_alternate"
            reason = f"An alternate broker route is materially stronger: {recommended.get('broker')}."

        return {
            "status": "success",
            "directive": directive,
            "reason": reason,
            "snapshot": snapshot,
        }

    def apply_auto_switch(self, ticker: str = "^NSEI") -> Dict[str, Any]:
        snapshot = self.get_routing_snapshot(ticker=ticker)
        current_broker_name = type(service_manager.execution_engine.broker).__name__
        if not ops_control_service.can_auto_switch():
            return {
                "status": "success",
                "switched": False,
                "reason": "Auto switching is disabled or safety lock is not armed.",
                "snapshot": snapshot,
            }

        recommended = snapshot.get("recommended_execution_broker") or {}
        target_broker = str(recommended.get("broker") or "")
        if not target_broker or target_broker == current_broker_name:
            return {
                "status": "success",
                "switched": False,
                "reason": "Current broker already matches recommended route.",
                "snapshot": snapshot,
            }
        if not bool(recommended.get("available")):
            return {
                "status": "success",
                "switched": False,
                "reason": "Recommended broker is not currently available.",
                "snapshot": snapshot,
            }

        mode_map = {
            "PaperBroker": "PAPER",
            "AngelOneBroker": "ANGEL_ONE",
        }
        target_mode = mode_map.get(target_broker)
        if not target_mode:
            return {
                "status": "success",
                "switched": False,
                "reason": f"No switch mapping defined for {target_broker}.",
                "snapshot": snapshot,
            }

        result = service_manager.execution_engine.switch_mode(target_mode)
        switched = str(result.get("status", "")).lower() == "success"
        return {
            "status": "success",
            "switched": switched,
            "reason": "Broker switched automatically." if switched else result.get("message", "Auto switch failed."),
            "target_mode": target_mode,
            "broker_result": result,
            "snapshot": snapshot,
        }


routing_service = RoutingService()
