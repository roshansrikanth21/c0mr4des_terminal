from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class EABridgeAdapter:
    """
    Lightweight bridge for MT4/MT5 Expert Advisors.
    Produces normalized JSON payloads and persists them to a shared folder.
    """

    def __init__(self):
        root = Path(__file__).resolve().parents[2]
        self.signal_dir = root / "data" / "ea_signals"
        self.execution_dir = root / "data" / "ea_executions"
        self.signal_dir.mkdir(parents=True, exist_ok=True)
        self.execution_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def build_signal_payload(self, fusion_response: Dict[str, Any], strategy_tag: str = "C0MR4DE_TERMINAL_FUSION_V1") -> Dict[str, Any]:
        decision = fusion_response.get("decision") or {}
        market = fusion_response.get("market") or {}
        ticker = fusion_response.get("ticker", "UNKNOWN")

        action = str(decision.get("action", "HOLD")).upper()
        entry = float(decision.get("entry", market.get("price", 0.0)) or 0.0)
        sl = float(decision.get("stop_loss", entry) or entry)
        tp = float(decision.get("take_profit", entry) or entry)

        payload = {
            "schema_version": "1.0",
            "generated_at": self._utc_now(),
            "source": strategy_tag,
            "symbol": ticker,
            "action": action,
            "entry": round(entry, 6),
            "stop_loss": round(sl, 6),
            "take_profit": round(tp, 6),
            "confidence": float(decision.get("confidence", 0.0) or 0.0),
            "risk_budget": float(decision.get("risk_budget", 0.0) or 0.0),
            "position_multiplier": float(decision.get("position_multiplier", 0.0) or 0.0),
            "meta": {
                "raw_score": decision.get("raw_score", 0.0),
                "components": decision.get("components", {}),
                "interval": market.get("interval"),
            },
        }
        return payload

    def write_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(payload.get("symbol", "UNKNOWN")).replace("^", "IDX_")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_path = self.signal_dir / f"signal__{symbol}__{ts}.json"
        file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        # Keep rolling "latest" file for EA polling.
        latest_path = self.signal_dir / "latest_signal.json"
        latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return {
            "status": "success",
            "path": str(file_path),
            "latest_path": str(latest_path),
            "generated_at": payload.get("generated_at"),
        }

    def get_latest_signal(self) -> Dict[str, Any]:
        latest_path = self.signal_dir / "latest_signal.json"
        if not latest_path.exists():
            return {"status": "error", "message": "No EA signal generated yet"}
        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
            return {"status": "success", "data": payload}
        except Exception as exc:
            return {"status": "error", "message": f"Invalid latest signal file: {exc}"}

    def save_execution_feedback(self, execution_payload: Dict[str, Any]) -> Dict[str, Any]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_path = self.execution_dir / f"execution__{ts}.json"
        wrapped = {
            "received_at": self._utc_now(),
            "payload": execution_payload,
        }
        file_path.write_text(json.dumps(wrapped, indent=2), encoding="utf-8")
        return {"status": "success", "path": str(file_path)}


ea_bridge_adapter = EABridgeAdapter()
