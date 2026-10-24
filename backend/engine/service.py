"""Orchestration: pulls data, runs the brain, attaches option plan + context, keeps a signal log."""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path

from . import macro, options, orb, replay, timeline
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


ALL_STRATEGIES = ("First-Hour", "First-30", "Engine")
# Engine is off by default: weakest backtest (PF 1.27) and 0/2 in the first live week.
DEFAULT_STRATEGIES = ("First-Hour", "First-30")


def load_settings() -> dict:
    base = {**RISK_DEFAULTS, "autopilot_instruments": ["NIFTY"], "autopilot_strategies": list(DEFAULT_STRATEGIES)}
    try:
        return {**base, **json.loads(SETTINGS_FILE.read_text())}
    except Exception:  # noqa: BLE001
        return base


def save_settings(new: dict) -> dict:
    cur = load_settings()
    for k in RISK_DEFAULTS:
        if k in new and new[k] is not None:
            cur[k] = float(new[k]) if k != "max_trades_per_day" else int(new[k])
    if new.get("autopilot_strategies") is not None:
        cur["autopilot_strategies"] = [x for x in new["autopilot_strategies"] if x in ALL_STRATEGIES] or list(DEFAULT_STRATEGIES)
    if new.get("autopilot_instruments") is not None:
        cur["autopilot_instruments"] = [x for x in new["autopilot_instruments"] if x in INSTRUMENTS] or ["NIFTY"]
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
    now = replay.now()
    sess = timeline.session(now, key)
    raw5, source = get_candles(key, "5m")
    daily, _ = get_candles(key, "1d")
    if replay.active():
        raw5, daily = replay.cut(raw5, "5m"), replay.cut(daily, "1d")
        source = f"replay ({source})"
        if raw5.empty:
            raise RuntimeError("Replay: no candles yet for this day/time")
    df5 = closed_bars(raw5, "5m", now)
    vix = macro.india_vix()
    news = radar.sentiment()
    cues = macro.global_cues()
    # Global cues matter most before/at the open; fade their weight as the day's own price action builds.
    cue_w = 1.0 if (not sess["is_open"] or sess["phase"] in ("pre_open", "opening")) else 0.5
    result = evaluate(df5, daily, inst.strike_step, now=now, news_bias=news["bias"],
                      cue_bias=cues["bias"] * cue_w, session=sess)

    expiry = date.fromisoformat(sess["expiry"])
    chain = options.live_chain(key, expiry, result["price"]) if sess["is_open"] and not replay.active() else None
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
                                           settings, chain, now, otm_steps=1) if orb_sig["direction"] else None
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
        "data_source": source, "data_delayed": source not in ("angel_one",) and not source.startswith("replay"),
        "session": sess, "vix": vix, "expected_move_rest_of_day": round(em, 1) if em else None,
        **result, "reasons": reasons, "option": option, "pcr": options.pcr(chain), "chain": chain,
        "news": news, "global": cues, "candles": chart_payload(raw5), "broker_connected": angel.api is not None,
        "spot_live": (None if replay.active() else _spot_ltp(inst)) or float(raw5["close"].iloc[-1]),
        "replay": replay.status(), "orb": orb_sig, "first30": f30,
        "shock": shock_check(raw5, daily, vix, news),
    }
    _log_signal(key, out)
    return out


def shock_check(df5, daily, vix, news) -> dict | None:
    """Shock days (war headlines, crashes, VIX spikes). Historical NIFTY behaviour, 2008-2026 daily data:
    - VIX +15% in a day (81 cases): next day up 60% of the time (avg +0.46%), next-day range ~1.8x normal.
    - NIFTY -3% in a day (70 cases): up 20 days later 64% of the time (avg +2.1%).
    - Named geopolitical shocks (Uri, Balakot, Ukraine, Israel, Pahalgam, Sindoor): mostly recovered within 5-20 days.
    """
    today = df5.index[-1].date()
    prev = daily[daily.index.date < today]
    if not len(prev):
        return None
    pc = float(prev["close"].iloc[-1])
    chg = (float(df5["close"].iloc[-1]) / pc - 1) * 100
    reasons = []
    if chg <= -2:
        reasons.append(f"NIFTY is down {chg:.1f}% today")
    if chg >= 2:
        reasons.append(f"NIFTY is up {chg:.1f}% today")
    if vix and vix.get("change_pct", 0) >= 15:
        reasons.append(f"India VIX jumped {vix['change_pct']:.0f}%")
    geo = [d for d in news.get("drivers", []) if d.get("direction", 0) < 0 and any(w in d["title"].lower() for w in ("war", "missile", "strike", "attack", "terror", "border", "flood", "earthquake", "cyclone"))]
    if geo:
        reasons.append("geopolitical/disaster headline: " + geo[0]["title"][:90])
    if not reasons:
        return None
    return {"active": True, "reasons": reasons,
            "playbook": [
                "Expect roughly double the normal intraday range: the first-hour breakout is the right tool, wider stops are normal.",
                "Option premiums are expensive (high IV). Buy ATM, not far OTM; IV falls when fear fades and eats far-OTM options first.",
                "History favours a rebound, not a collapse: after VIX spikes NIFTY rose the next day 60% of the time; after -3% days it was higher 20 days later 64% of the time.",
                "Don't buy puts into the close after a crash day; the next session gaps up more often than down.",
            ]}


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
    if not out["session"]["is_open"] or replay.active():
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
