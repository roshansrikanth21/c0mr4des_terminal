"""Expiry-day short straddle: a PAPER-ONLY book. It never places an order.

Why this exists
---------------
The 50-strategy study (research/ZOO_RESULTS.md, 12 Nov 2026) scored every strategy on six years of real
NIFTY option prices. One options strategy came through with a case: on weekly expiry days, sell the
at-the-money call and put at 09:20, stop each leg if its premium rises 30%, and be flat by 15:15.
305 trades, profitable in all six years, profit factor 1.50 after charges and 0.5% slippage, worst day
-Rs 9,374 on one lot. It needs roughly Rs 2 lakh of margin, which is why it is paper only here.

Known weak spots, so nobody reads more into it than is there (research/ZOO_NOTES.md):
  * 09:20 was the best of the entry times tried (09:30-12:00 gave profit factor 1.17-1.48)
  * since expiry moved to Tuesday the profit factor is 1.17 over 63 trades
  * the hedged version a small account could fund does not carry the edge
This book is the forward test of exactly the rule that was back-tested. The rule is frozen: do not tune
it against its own paper results.

Rules (version 1)
-----------------
  * NIFTY only, weekly expiry day only, one trade a day
  * entry between 09:20 and 09:25 at live Angel One prices; no live quote for both legs = no trade
  * sell 1 lot of the ATM call and 1 lot of the ATM put
  * each leg is bought back when its premium is 30% above the price it was sold at
  * anything still open is bought back at 15:15

One difference from the back-test: the study saw prices every five minutes, this book sees them on
every engine pass (about 15 seconds), so a stop here fills nearer its trigger.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, time
from pathlib import Path

from .config import INSTRUMENTS
from .options import round_trip_cost

log = logging.getLogger("engine.straddle")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BOOK_FILE = DATA_DIR / "straddle_book.json"

RULES = {
    "instrument": "NIFTY",
    "entry_from": time(9, 20),
    "entry_until": time(9, 25),
    "leg_stop_pct": 30.0,
    "square_off": time(15, 15),
    "margin": 200_000.0,       # round assumption for one naked short straddle lot, not a broker quote
    "slippage_pct": 0.5,       # per side, the same haircut the study used; reported next to the raw P&L
    "need_trades": 20,
}
RULES_VERSION = 1
KINDS = ("CE", "PE")


def chain_quotes(chain: list[dict] | None) -> dict[float, dict[str, float]]:
    """{strike: {"CE": ltp, "PE": ltp}} from the engine's live chain; missing or zero prices are left out."""
    out: dict[float, dict[str, float]] = {}
    for row in chain or []:
        legs = {k: float(row[k]["ltp"]) for k in KINDS if (row.get(k) or {}).get("ltp")}
        if legs:
            out[float(row["strike"])] = legs
    return out


def _live_quotes(key: str, expiry: date, strike: float) -> dict[float, dict[str, float]]:
    from . import options  # late import: keeps this module importable without the broker stack

    return chain_quotes(options.live_chain(key, expiry, strike, width=1))


class StraddleBook:
    def __init__(self, path: Path | None = None, quote_fn=None):
        self.path = path or BOOK_FILE
        self.quote_fn = quote_fn or _live_quotes
        self._lock = threading.Lock()
        self.state = self._load()

    # ---------------- storage ----------------
    def _load(self) -> dict:
        for p in (self.path, self.path.with_name(self.path.name + ".bak")):
            try:
                s = json.loads(p.read_text())
                if isinstance(s, dict) and "closed" in s:
                    s.setdefault("open", None)
                    s.setdefault("skipped", [])
                    return s
            except (OSError, ValueError):
                continue
        return {"open": None, "closed": [], "skipped": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, default=str))
        if self.path.exists():
            try:
                json.loads(self.path.read_text())
                os.replace(self.path, self.path.with_name(self.path.name + ".bak"))
            except (OSError, ValueError):
                pass                       # never let a broken main file overwrite a good backup
        os.replace(tmp, self.path)

    # ---------------- the engine hook ----------------
    def on_analysis(self, a: dict) -> dict:
        """Called on every fresh NIFTY analysis. Returns {"events": [{"type", "text"}]} for the alert channel."""
        if (a.get("instrument") or {}).get("key") != RULES["instrument"]:
            return {"events": []}
        now = datetime.fromisoformat(a["generated_at"])
        sess = a.get("session") or {}
        with self._lock:
            events = self._manage(a, now, sess) if self.state["open"] else []
            if not self.state["open"]:
                events += self._maybe_enter(a, now, sess)
            return {"events": events}

    def _quotes(self, a: dict, expiry: str, strike: float) -> dict[str, float]:
        """Live prices for one strike: the chain the engine already fetched if it is for this expiry, else a
        small dedicated quote. After 12:00 on expiry day the engine's own chain has rolled to next week."""
        have = chain_quotes((a.get("chains") or {}).get(expiry)).get(float(strike))
        if have and all(k in have for k in KINDS):
            return have
        try:
            return self.quote_fn(RULES["instrument"], date.fromisoformat(expiry), float(strike)).get(float(strike), {})
        except Exception as exc:  # noqa: BLE001 - a quote failure must never stop the desk
            log.warning("straddle quote failed: %s", exc)
            return have or {}

    def _skip(self, today: str, why: str) -> list[dict]:
        if any(s["date"] == today for s in self.state["skipped"]):
            return []
        self.state["skipped"] = (self.state["skipped"] + [{"date": today, "why": why}])[-60:]
        self._save()
        return [{"type": "straddle_skip", "text": f"EXPIRY STRADDLE (paper): no trade today - {why}."}]

    def _maybe_enter(self, a: dict, now: datetime, sess: dict) -> list[dict]:
        today = now.date().isoformat()
        if not sess.get("is_expiry_day") or not sess.get("is_open"):
            return []
        if any(t["date"] == today for t in self.state["closed"]) or any(s["date"] == today for s in self.state["skipped"]):
            return []
        if now.time() < RULES["entry_from"]:
            return []
        if now.time() >= RULES["entry_until"]:
            return self._skip(today, "the 09:20-09:25 entry window was missed")
        if a.get("data_delayed"):
            return []                      # keep trying inside the window; a late feed is not a tradable price
        inst = INSTRUMENTS[RULES["instrument"]]
        spot = float(a.get("spot_live") or a["price"])
        strike = float(round(spot / inst.strike_step) * inst.strike_step)
        q = self._quotes(a, sess["expiry"], strike)
        if not all(q.get(k, 0) > 0 for k in KINDS):
            return []                      # no live price for both legs yet: retry until the window closes
        self.state["open"] = {
            "date": today, "expiry": sess["expiry"], "strike": strike, "lot": inst.lot_size,
            "opened_at": now.isoformat(), "entry_spot": spot, "rules_version": RULES_VERSION,
            "legs": {k: {"in": round(q[k], 2), "mark": round(q[k], 2), "out": None, "why": None, "closed_at": None}
                     for k in KINDS},
        }
        self._save()
        credit = (q["CE"] + q["PE"]) * inst.lot_size
        return [{"type": "straddle_entry", "text": (
            f"EXPIRY STRADDLE (paper) SOLD NIFTY {strike:.0f} CE @ {q['CE']:.2f} + PE @ {q['PE']:.2f}\n"
            f"1 lot ({inst.lot_size}), credit Rs {credit:,.0f}. Each leg stops at +{RULES['leg_stop_pct']:.0f}%, "
            f"flat by 15:15. Paper only: needs about Rs {RULES['margin']:,.0f} margin.")}]

    def _manage(self, a: dict, now: datetime, sess: dict) -> list[dict]:
        pos = self.state["open"]
        events: list[dict] = []
        stale = pos["date"] != now.date().isoformat()
        q = {} if stale else self._quotes(a, pos["expiry"], pos["strike"])
        done = stale or now.time() >= RULES["square_off"] or not sess.get("is_open")
        for k in KINDS:
            leg = pos["legs"][k]
            if leg["out"] is not None:
                continue
            ltp = q.get(k)
            if ltp:
                leg["mark"] = round(ltp, 2)
            if not stale and ltp and ltp >= leg["in"] * (1 + RULES["leg_stop_pct"] / 100):
                leg.update(out=round(ltp, 2), why="stop", closed_at=now.isoformat())
                events.append({"type": "straddle_stop", "text": (
                    f"EXPIRY STRADDLE (paper) STOP: {pos['strike']:.0f} {k} bought back @ {ltp:.2f} "
                    f"(sold @ {leg['in']:.2f}).")})
            elif done:
                why = "stale (square-off missed)" if stale else "15:15 square-off" if ltp else "15:15 at last mark (no quote)"
                leg.update(out=leg["mark"], why=why, closed_at=now.isoformat())
        if all(pos["legs"][k]["out"] is not None for k in KINDS):
            closed = self._settle(pos, now)
            self.state["closed"].append(closed)
            self.state["open"] = None
            n = len(self.state["closed"])
            events.append({"type": "straddle_exit", "text": (
                f"EXPIRY STRADDLE (paper) CLOSED {pos['strike']:.0f}: P&L Rs {closed['pnl']:,.0f} after charges "
                f"(Rs {closed['pnl_after_slippage']:,.0f} with slippage). CE {closed['legs']['CE']['why']}, "
                f"PE {closed['legs']['PE']['why']}. Trade {n} of the {RULES['need_trades']} needed.")})
        self._save()
        return events

    @staticmethod
    def _settle(pos: dict, now: datetime) -> dict:
        lot = pos["lot"]
        gross = charges = slip = 0.0
        for leg in pos["legs"].values():
            gross += (leg["in"] - leg["out"]) * lot
            charges += round_trip_cost((leg["in"] + leg["out"]) / 2, lot)
            slip += RULES["slippage_pct"] / 100 * (leg["in"] + leg["out"]) * lot
        return {**pos, "closed_at": now.isoformat(), "credit": round(sum(leg["in"] for leg in pos["legs"].values()) * lot, 2),
                "charges": round(charges, 2), "pnl": round(gross - charges, 2),
                "pnl_after_slippage": round(gross - charges - slip, 2)}

    # ---------------- reporting ----------------
    def report(self) -> dict:
        with self._lock:
            closed = list(self.state["closed"])
            pos = self.state["open"]
        pnl = [t["pnl_after_slippage"] for t in closed]
        wins = [p for p in pnl if p > 0]
        losses = [p for p in pnl if p <= 0]
        streak = worst = 0
        eq = peak = dd = 0.0
        for p in pnl:
            streak = streak + 1 if p <= 0 else 0
            worst = max(worst, streak)
            eq += p
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        unreal = None
        if pos:
            unreal = round(sum((leg["in"] - (leg["out"] if leg["out"] is not None else leg["mark"])) * pos["lot"]
                               for leg in pos["legs"].values()), 2)
        return {
            "paper_only": True, "rules_version": RULES_VERSION,
            "rules": {"entry": "09:20-09:25 on weekly expiry day", "leg_stop_pct": RULES["leg_stop_pct"],
                      "square_off": "15:15", "margin_assumed": RULES["margin"], "slippage_pct": RULES["slippage_pct"]},
            "backtest": {"trades": 305, "profit_factor": 1.50, "worst_day": -9374, "since_tuesday_expiry_pf": 1.17,
                         "source": "research/ZOO_RESULTS.md"},
            "trades": len(closed), "need_trades": RULES["need_trades"],
            "net": round(sum(t["pnl"] for t in closed), 2), "net_after_slippage": round(sum(pnl), 2),
            "win_rate": round(100 * len(wins) / len(pnl), 1) if pnl else None,
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
            "worst_day": round(min(pnl), 2) if pnl else None, "worst_streak": worst, "max_drawdown": round(dd, 2),
            "open": pos, "unrealized": unreal, "closed": closed[::-1], "skipped": self.state["skipped"][-10:],
        }


_book: StraddleBook | None = None


def book() -> StraddleBook:
    global _book
    if _book is None:
        _book = StraddleBook()
    return _book


def on_analysis(a: dict) -> dict:
    return book().on_analysis(a)


def report() -> dict:
    return book().report()
