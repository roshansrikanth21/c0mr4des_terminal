"""Paper autopilot + gated live orders.

PAPER (default): every live BUY/SELL verdict opens a simulated option position at the live premium
(Angel One LTP when connected, otherwise a Black-Scholes estimate), then exits on the index stop,
index target, or 15:15. Risk caps (trades/day, daily loss) are enforced. Everything is saved to
data/paper_trades.json so you can review the day honestly.

LIVE: off unless backend/.env has LIVE_TRADING=true AND Angel One is connected. Even then the app
never fires on its own: you click "Place order", the server re-checks the caps, and sends one LIMIT
order through SmartAPI. Exits on live positions are your job (the app alerts you).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, time
from pathlib import Path

from .config import INSTRUMENTS, IST
from .data import angel
from .options import bs, implied_vol, round_trip_cost, years_to_expiry

log = logging.getLogger("engine.trader")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PAPER_FILE = DATA_DIR / "paper_trades.json"
REPLAY_FILE = DATA_DIR / "replay_paper.json"
ORDER_LOG = DATA_DIR / "live_orders.jsonl"
SQUARE_OFF = time(15, 15)


def live_enabled() -> bool:
    return os.getenv("LIVE_TRADING", "").lower() == "true"


class PaperTrader:
    def __init__(self, path: Path | None = None):
        self.path = path or PAPER_FILE
        self._lock = threading.Lock()
        self.state = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:  # noqa: BLE001
            return {"open": {}, "closed": []}

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=1, default=str))

    # ---------- helpers ----------
    def today_closed(self, key: str | None = None, day: date | None = None) -> list[dict]:
        d = (day or date.today()).isoformat()
        return [t for t in self.state["closed"] if t["opened_at"][:10] == d and (key is None or t["instrument"] == key)]

    def day_pnl(self, day: date | None = None) -> float:
        return sum(t["pnl"] for t in self.today_closed(day=day))

    def _premium_now(self, pos: dict, spot: float, now: datetime, chain: list | None) -> tuple[float, str]:
        if chain:
            row = next((r for r in chain if r["strike"] == pos["strike"]), None)
            ltp = (row or {}).get(pos["option_type"], {}).get("ltp") if row else None
            if ltp:
                return float(ltp), "live"
        exp = date.fromisoformat(pos["expiry"])
        return bs(spot, pos["strike"], years_to_expiry(exp, now), pos["iv"], pos["option_type"])["price"], "model"

    # ---------- main hook, called on every fresh analysis ----------
    def on_analysis(self, a: dict, settings: dict) -> dict:
        """Run every strategy in its own paper slot so they can be compared live."""
        key = a["instrument"]["key"]
        events = []
        if key not in settings.get("autopilot_instruments", ["NIFTY"]):
            return {"events": [], "open": []}
        events += self._process(f"{key}|engine", "Engine", a.get("verdict"), a.get("option"), a.get("plan"), a, settings,
                                settings["max_trades_per_day"])
        orb = a.get("orb") or {}
        events += self._process(f"{key}|orb", "First-Hour", orb.get("verdict"), orb.get("option"),
                                {"direction": orb.get("direction", 0), "stop": orb.get("stop"), "target": orb.get("target")},
                                a, settings, 1)
        f30 = a.get("first30") or {}
        events += self._process(f"{key}|first30", "First-30", f30.get("verdict"), f30.get("option"),
                                {"direction": f30.get("direction", 0), "stop": f30.get("stop"), "target": f30.get("target")},
                                a, settings, 1)
        return {"events": events, "open": [p for s, p in self.state["open"].items() if s.startswith(key + "|")]}

    def _process(self, slot, strategy, verdict, option, plan, a, settings, max_trades) -> list[dict]:
        key = a["instrument"]["key"]
        now = datetime.fromisoformat(a["generated_at"])
        spot = a.get("spot_live") or a["price"]
        events = []
        with self._lock:
            pos = self.state["open"].get(slot)
            if pos:
                d = pos["dir"]
                hit_stop = (spot <= pos["index_stop"]) if d > 0 else (spot >= pos["index_stop"])
                hit_tgt = (spot >= pos["index_target"]) if d > 0 else (spot <= pos["index_target"])
                eod = now.time() >= SQUARE_OFF or not a["session"]["is_open"]
                prem, src = self._premium_now(pos, spot, now, a.get("chain"))
                pos["mark"] = round(prem, 2)
                pos["unrealized"] = round((prem - pos["entry_premium"]) * pos["quantity"], 2)
                # premium-based stop as a backstop (theta can kill a position before the index stop hits)
                prem_stop = prem <= pos["premium_stop"]
                if hit_stop or hit_tgt or eod or prem_stop:
                    reason = "target" if hit_tgt else "stop" if hit_stop else "premium stop" if prem_stop else "15:15 square-off"
                    cost = round_trip_cost((pos["entry_premium"] + prem) / 2, pos["quantity"])
                    pnl = round((prem - pos["entry_premium"]) * pos["quantity"] - cost, 2)
                    closed = {**pos, "closed_at": now.isoformat(), "exit_spot": spot, "exit_premium": round(prem, 2),
                              "exit_source": src, "reason": reason, "charges": cost, "pnl": pnl}
                    self.state["closed"].append(closed)
                    del self.state["open"][slot]
                    events.append({"type": "paper_exit", "trade": closed})
                self._save()
            elif verdict in ("BUY", "SELL") and option and plan.get("stop") is not None:
                mine = [t for t in self.state["closed"] if t.get("slot") == slot]
                n_today = sum(1 for t in mine if t["opened_at"][:10] == now.date().isoformat())
                loss_cap = -settings["capital"] * settings["max_daily_loss_pct"] / 100
                cooling = mine and (now - datetime.fromisoformat(mine[-1]["closed_at"])).total_seconds() < 900
                if (spot - plan["stop"]) * plan["direction"] <= 0:
                    events.append({"type": "blocked", "reason": f"{strategy}: stop is on the wrong side of price - skipped"})
                elif cooling:
                    events.append({"type": "blocked", "reason": f"{strategy}: cooling off 15 min after the last exit"})
                elif n_today >= max_trades:
                    events.append({"type": "blocked", "reason": f"{strategy}: max {max_trades} trade(s)/day reached"})
                elif self.day_pnl(now.date()) <= loss_cap:
                    events.append({"type": "blocked", "reason": "Daily loss limit hit - done for the day"})
                else:
                    o, p = option, plan
                    # Paper always takes at least 1 lot (same as the lab), and flags when that breaks your risk budget.
                    lots = max(1, o.get("lots", 0))
                    qty = lots * INSTRUMENTS[key].lot_size
                    oversize = o.get("lots", 0) < 1
                    exp = date.fromisoformat(o["expiry"])
                    iv = (o["greeks"].get("iv")
                          or implied_vol(o["premium"], spot, o["strike"], years_to_expiry(exp, now), o["option_type"])
                          or (a["vix"]["value"] / 100 if a.get("vix") else 0.14))
                    pos = {"slot": slot, "strategy": strategy, "instrument": key, "dir": p["direction"], "side": o["side"],
                           "symbol": o["symbol_hint"], "strike": o["strike"], "option_type": o["option_type"],
                           "expiry": o["expiry"], "quantity": qty, "lots": lots, "oversize": oversize, "entry_premium": o["premium"],
                           "premium_source": o["premium_source"], "premium_stop": o["premium_stop"],
                           "premium_target": o["premium_target"], "iv": iv, "entry_spot": spot,
                           "index_stop": p["stop"], "index_target": p["target"], "opened_at": now.isoformat(),
                           "score": a["score"], "mark": o["premium"], "unrealized": 0.0}
                    self.state["open"][slot] = pos
                    self._save()
                    events.append({"type": "paper_entry", "trade": pos})
        return events

    def summary(self, day: date | None = None) -> dict:
        today = self.today_closed(day=day)
        allc = self.state["closed"]
        wins = [t for t in allc if t["pnl"] > 0]
        by_strategy = {}
        for t in allc:
            b = by_strategy.setdefault(t.get("strategy", "Engine"), {"trades": 0, "wins": 0, "pnl": 0.0})
            b["trades"] += 1
            b["wins"] += t["pnl"] > 0
            b["pnl"] = round(b["pnl"] + t["pnl"], 2)
        return {
            "by_strategy": by_strategy,
            "open": list(self.state["open"].values()),
            "today": {"trades": len(today), "pnl": round(sum(t["pnl"] for t in today), 2),
                      "wins": sum(1 for t in today if t["pnl"] > 0)},
            "all_time": {"trades": len(allc), "pnl": round(sum(t["pnl"] for t in allc), 2), "wins": len(wins),
                         "win_rate": round(len(wins) / len(allc) * 100, 1) if allc else None},
            "closed": list(reversed(allc[-200:])),
            "live_trading_enabled": live_enabled(), "broker_connected": angel.api is not None,
        }

    def reset(self):
        with self._lock:
            self.state = {"open": {}, "closed": []}
            self._save()


paper = PaperTrader()
replay_paper = PaperTrader(REPLAY_FILE)


# ---------------- live orders (explicit click only) ----------------
def _find_contract(key: str, expiry: str, strike: float, kind: str) -> dict | None:
    from .options import _scrip_master

    inst = INSTRUMENTS[key]
    exp = date.fromisoformat(expiry).strftime("%d%b%Y").upper()
    for r in _scrip_master():
        if (r.get("name") == inst.angel_name and r.get("expiry") == exp and r.get("exch_seg") == inst.option_exchange
                and abs(float(r.get("strike", 0)) / 100 - strike) < 0.01 and r["symbol"].endswith(kind)):
            return r
    return None


def place_live_order(key: str, expiry: str, strike: float, kind: str, lots: int, side: str, limit_price: float,
                     settings: dict) -> dict:
    """One LIMIT order via SmartAPI. Caller must be a deliberate user click."""
    if not live_enabled():
        return {"ok": False, "error": "Live trading is disabled. Set LIVE_TRADING=true in backend/.env to enable."}
    api = angel.session()
    if api is None:
        return {"ok": False, "error": "Angel One is not connected."}
    if side == "BUY":
        if len([t for t in _order_log_today() if t.get("side") == "BUY" and t.get("ok")]) >= settings["max_trades_per_day"]:
            return {"ok": False, "error": "Max trades per day reached."}
        if paper.day_pnl() <= -settings["capital"] * settings["max_daily_loss_pct"] / 100:
            return {"ok": False, "error": "Daily loss limit reached."}
        max_lots = int(settings["capital"] // (limit_price * INSTRUMENTS[key].lot_size)) if limit_price > 0 else 0
        if lots < 1 or lots > max_lots:
            return {"ok": False, "error": f"Lots must be 1..{max_lots} for your capital."}
    c = _find_contract(key, expiry, strike, kind)
    if not c:
        return {"ok": False, "error": "Contract not found in Angel One scrip master."}
    tick = 0.05
    price = round(round(limit_price / tick) * tick, 2)
    params = {
        "variety": "NORMAL", "tradingsymbol": c["symbol"], "symboltoken": c["token"], "transactiontype": side,
        "exchange": INSTRUMENTS[key].option_exchange, "ordertype": "LIMIT", "producttype": "INTRADAY",
        "duration": "DAY", "price": str(price), "quantity": str(lots * INSTRUMENTS[key].lot_size),
    }
    rec = {"at": datetime.now(IST).isoformat(), "side": side, **params}
    try:
        fn = getattr(api, "placeOrderFullResponse", None)
        res = fn(params) if fn else {"status": True, "data": {"orderid": api.placeOrder(params)}}
        ok = bool(res and res.get("status") and (res.get("data") or {}).get("orderid"))
        rec.update({"ok": ok, "response": res})
    except Exception as exc:  # noqa: BLE001
        rec.update({"ok": False, "error": str(exc)})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ORDER_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return {"ok": rec.get("ok", False), "order": rec, "error": rec.get("error") or (None if rec.get("ok") else str(rec.get("response")))}


def _order_log_today() -> list[dict]:
    if not ORDER_LOG.exists():
        return []
    d = date.today().isoformat()
    rows = [json.loads(x) for x in ORDER_LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if str(r.get("at", ""))[:10] == d]
