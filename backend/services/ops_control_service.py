from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class OpsControlService:
    """
    Persistent runtime safety controls for live operations.
    Automatic route switching is only allowed when the safety lock is armed.
    """

    DEFAULT_CONFIG = {
        "manual_safety_lock": False,
        "auto_broker_switch_enabled": False,
        "preferred_live_broker": "ANGEL_ONE",
        "last_updated_at": None,
    }

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.data_dir = root / "data" / "ops"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "control.json"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return dict(self.DEFAULT_CONFIG)
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return {**self.DEFAULT_CONFIG, **data}
        except Exception:
            return dict(self.DEFAULT_CONFIG)

    def _save(self, config: Dict[str, Any]) -> None:
        config["last_updated_at"] = self._utc_now()
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def get_config(self) -> Dict[str, Any]:
        return {"status": "success", "config": self._load()}

    def update_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        config = self._load()
        if "manual_safety_lock" in payload:
            config["manual_safety_lock"] = bool(payload.get("manual_safety_lock"))
        if "auto_broker_switch_enabled" in payload:
            config["auto_broker_switch_enabled"] = bool(payload.get("auto_broker_switch_enabled"))
        if "preferred_live_broker" in payload:
            broker = str(payload.get("preferred_live_broker") or "ANGEL_ONE").strip().upper()
            if broker in {"ANGEL_ONE"}:
                config["preferred_live_broker"] = broker
        self._save(config)
        return {"status": "success", "config": config}

    def can_auto_switch(self) -> bool:
        cfg = self._load()
        return bool(cfg.get("manual_safety_lock")) and bool(cfg.get("auto_broker_switch_enabled"))


ops_control_service = OpsControlService()
