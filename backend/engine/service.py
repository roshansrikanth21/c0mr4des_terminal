"""Orchestration: pulls data, runs the brain, attaches option plan + context, keeps a signal log."""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path

from . import macro, options, orb, timeline
from .config import IST, INSTRUMENTS, RISK_DEFAULTS
from .data import angel, closed_bars, get_candles
from .news import radar
from .signal import evaluate

log = logging.getLogger("engine.service")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SIGNAL_LOG = DATA_DIR / "signals.jsonl"
SETTINGS_FILE = DATA_DIR / "settings.json"
_last_verdict: dict[str, str] = {}
_lock = threading.Lock()


def load_settings() -> dict:
    try:
        return {**RISK_DEFAULTS, **json.loads(SETTINGS_FILE.read_text())}
    except Exception:  # noqa: BLE001
        return dict(RISK_DEFAULTS)


def save_settings(new: dict) -> dict:
    cur = load_settings()
    for k in RISK_DEFAULTS:
        if k in new and new[k] is not None:
            cur[k] = float(new[k]) if k != "max_trades_per_day" else int(new[k])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(cur, indent=2))
    return cur


def chart_payload(df, bars: int = 300) -> list[dict]:
    tail = df.tail(bars)
    return [{"time": int(ts.timestamp()), "open": round(r.open, 2), "high": round(r.high, 2),
             "low": round(r.low, 2), "close": round(r.close, 2)} for ts, r in tail.iterrows()]


def analyze(key: str = "NIFTY", interval: str = "5m") -> dict:
    key = key.upper()
    if key not in INSTRUMENTS:
        raise ValueError(f"Unknown instrument {key}; use one of {list(INSTRUMENTS)}")
    inst = INSTRUMENTS[key]
    now = datetime.now(IST)
    sess = timeline.session(now, key)
    raw5, source = get_candles(key, "5m")
    df5 = closed_bars(raw5, "5m", now)
    daily, _ = get_candles(key, "1d")
    vix = macro.india_vix()
    news = radar.sentiment()
    cues = macro.global_cues()
    # Global cues matter most before/at the open; fade their weight as the day's own price action builds.
    cue_w = 1.0 if (not sess["is_open"] or sess["phase"] in ("pre_open", "opening")) else 0.5
    result = evaluate(df5, daily, inst.strike_step, now=now, news_bias=news["bias"],
                      cue_bias=cues["bias"] * cue_w, session=sess)

    expiry = date.fromisoformat(sess["expiry"])
    chain = options.live_chain(key, expiry, result["price"]) if sess["is_open"] else None
    settings = load_settings()
    plan = result["plan"]
    option = options.plan_trade(key, plan["direction"], result["price"], expiry, vix["value"] if vix else None,
                                plan["risk_points"], plan["target_points"], settings, chain, now)
    prev = daily[daily.index.date < now.date()]
    orb_sig = orb.evaluate(df5, float(prev["close"].iloc[-1]) if len(prev) else None, now)
    if not sess["can_enter"] and orb_sig["verdict"] != "NO TRADE":
        orb_sig["verdict"] = "NO TRADE"
    orb_sig["option"] = options.plan_trade(key, orb_sig["direction"], result["price"], expiry, vix["value"] if vix else None,
                                           orb_sig.get("risk_points") or 0, orb_sig.get("target_points") or 0,
                                           settings, chain, now) if orb_sig["direction"] else None
    f30 = orb.first30(df5, now)
    if not sess["is_open"] and f30["verdict"] != "NO TRADE":
        f30["verdict"] = "NO TRADE"
    f30["option"] = options.plan_trade(key, f30["direction"], result["price"], expiry, vix["value"] if vix else None,
                                       f30.get("risk_points") or 0, f30.get("target_points") or 0,
                                       settings, chain, now) if f30["direction"] else None
    minutes_left = max(sess["minutes_to_close"], 30)
    em = options.expected_move(result["price"], vix["value"] if vix else None, minutes_left)

    reasons = result["reasons"] + [
        {"factor": "News flow", "signal": "bullish" if news["bias"] > 0.15 else "bearish" if news["bias"] < -0.15 else "neutral",
         "text": news["text"] + (" Top driver: " + news["drivers"][0]["title"] if news["drivers"] else "")},
        {"factor": "Global cues", "signal": "bullish" if cues["bias"] > 0.2 else "bearish" if cues["bias"] < -0.2 else "neutral",
         "text": cues["text"]},
        {"factor": "Timeline", "signal": "neutral", "text": f"{sess['phase_note']} {sess['expiry_note']}"},
    ]
    if vix:
        reasons.append({"factor": "Volatility (India VIX)", "signal": "neutral", "text": vix["text"]})

    out = {
        "instrument": {"key": key, "name": inst.name, "lot_size": inst.lot_size, "strike_step": inst.strike_step},
        "generated_at": now.isoformat(timespec="seconds"),
        "data_source": source, "data_delayed": source != "angel_one",
        "session": sess, "vix": vix, "expected_move_rest_of_day": round(em, 1) if em else None,
        **result, "reasons": reasons, "option": option, "pcr": options.pcr(chain), "chain": chain,
        "news": news, "global": cues, "candles": chart_payload(raw5), "broker_connected": angel.api is not None,
        "spot_live": _spot_ltp(inst) or float(raw5["close"].iloc[-1]), "orb": orb_sig, "first30": f30,
    }
    _log_signal(key, out)
    return out


def _spot_ltp(inst) -> float | None:
    """Freshest spot price: Angel One LTP when connected (real time), else None."""
    api = angel.api
    if api is None:
        return None
    try:
        res = api.ltpData(inst.angel_exchange, inst.key if inst.key != "NIFTY" else "Nifty 50", inst.angel_spot_token)
        return float(res["data"]["ltp"])
    except Exception:  # noqa: BLE001
        return None


def _log_signal(key: str, out: dict) -> None:
    """Append when the verdict changes during market hours, for honest after-the-fact review."""
    if not out["session"]["is_open"]:
        return
    with _lock:
        if _last_verdict.get(key) == out["verdict"]:
            return
        _last_verdict[key] = out["verdict"]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        rec = {k: out[k] for k in ("generated_at", "verdict", "lean", "score", "price", "plan", "bar_time")}
        rec["instrument"] = key
        rec["option"] = (out.get("option") or {}).get("symbol_hint")
        with SIGNAL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def signal_log(limit: int = 100) -> list[dict]:
    if not SIGNAL_LOG.exists():
        return []
    lines = SIGNAL_LOG.read_text(encoding="utf-8").strip().splitlines()[-limit:]
    return [json.loads(x) for x in reversed(lines)]
