"""Defined-risk credit spreads: collect theta instead of paying it.

Why this exists
---------------
Every long option pays theta; the paper book showed the stop being hit by time decay
before the index ever reached its level. The documented edge in Indian index options is
on the other side of that trade: implied volatility exceeded realised volatility on 79.5%
of days (NIFTY, 2016-2024). Selling premium is the way to be on that side, but naked
selling needs Rs 1-1.5 lakh of margin per lot.

A vertical credit spread gets the same side of the trade with the risk capped:

    bullish  -> sell an OTM put, buy a further-OTM put   (bull put spread)
    bearish  -> sell an OTM call, buy a further-OTM call (bear call spread)

You receive a credit. If the index stays away from the short strike you keep it. If it
does not, the long leg caps the loss at (width - credit) per unit. Margin is the width,
not the index.

Rules (kept deliberately simple so one week can test them):
  * short leg near 0.20 delta, long leg near 0.08 delta, width clamped to 2-10 steps
  * one spread per day, one open at a time
  * close at 50% of the credit, or at 2x the credit if it goes against us
  * hold to the EXPIRY DAY (15:15), not to the same afternoon

Why the last rule changed (28-30 Oct): the book opened three spreads, sold at ~6 DTE, and closed
each one at the 14:30 time stop after about five hours. All three lost. A replay of the same 35
signals on the same history showed the short strike was NEVER breached, and that the same-day
exit lost -Rs 8,133 at 31.4% wins while holding to expiry with the same 2x stop made +Rs 2,290 at
60.0% wins. A credit spread sells theta, and theta needs days, not hours - closing it the same
afternoon pays the full directional risk and collects almost none of the decay it sold.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, time
from pathlib import Path

from .config import ENTRY_RULES, INSTRUMENTS, IST
from .options import bs, round_trip_cost, years_to_expiry

log = logging.getLogger("engine.spreads")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BOOK_FILE = DATA_DIR / "spread_book.json"

SPREAD = {
    "stake": 50_000.0,          # the case's own stake - nothing is borrowed from the other books
    "short_delta": 0.20,        # how far OTM the leg we sell sits
    "long_delta": 0.08,         # the leg we buy as protection
    "min_width_steps": 2,       # narrowest allowed spread (100 NIFTY points)
    "max_width_steps": 10,      # widest allowed spread (500 NIFTY points)
    "target_pct": 50.0,         # take the trade off at 50% of the credit received
    "stop_mult": 2.0,           # or when closing costs twice the credit
    "max_per_day": 1,
    "min_credit_pct": 8.0,      # a credit thinner than this is not worth four orders of charges
}
NO_ENTRY_AFTER = time(*ENTRY_RULES["no_entry_after"])
EXPIRY_CLOSE = time(15, 15)   # on expiry day only: settle before the 15:30 close
RULES_VERSION = 2             # 1 = same-day time stop (the first three trades), 2 = hold to expiry


# ---------------------------------------------------------------- pricing
def _legs(direction: int, spot: float, expiry: date, sigma: float, inst, now: datetime,
          chain: list[dict] | None, rules: dict) -> tuple[float, float, str] | None:
    """Pick the short and long strikes by delta, walking outward from ATM."""
    kind = "PE" if direction > 0 else "CE"
    step = inst.strike_step
    atm = round(spot / step) * step
    T = years_to_expiry(expiry, now)

    def greek(k: float) -> float:
        return abs(bs(spot, k, T, sigma, kind)["delta"])

    short = long_ = None
    for n in range(1, 41):
        k = atm - direction * n * step
        if short is None:
            if greek(k) <= rules["short_delta"]:
                short = k
            continue
        if abs(k - short) < rules["min_width_steps"] * step:
            continue
        if greek(k) <= rules["long_delta"] or abs(k - short) >= rules["max_width_steps"] * step:
            long_ = k
            break
    if short is None or long_ is None:
        return None
    return short, long_, kind


def _premium(spot: float, strike: float, expiry: date, sigma: float, kind: str,
             now: datetime, chain: list[dict] | None) -> tuple[float, str]:
    if chain:
        row = next((r for r in chain if r["strike"] == strike), None)
        ltp = (row or {}).get(kind, {}).get("ltp") if row else None
        if ltp:
            return float(ltp), "live (Angel One)"
    return float(bs(spot, strike, years_to_expiry(expiry, now), sigma, kind)["price"]), "model (Black-Scholes)"


def plan(key: str, direction: int, spot: float, expiry: date, vix: float | None,
         now: datetime, chain: list[dict] | None = None, rules: dict | None = None) -> dict | None:
    """Build a vertical credit spread. None when the numbers do not clear the rules."""
    if direction == 0 or spot <= 0:
        return None
    r = {**SPREAD, **(rules or {})}
    inst = INSTRUMENTS[key]
    sigma = (vix or 14) / 100
    picked = _legs(direction, spot, expiry, sigma, inst, now, chain, r)
    if not picked:
        return None
    short_k, long_k, kind = picked
    short_px, short_src = _premium(spot, short_k, expiry, sigma, kind, now, chain)
    long_px, long_src = _premium(spot, long_k, expiry, sigma, kind, now, chain)
    credit = round(short_px - long_px, 2)
    if credit <= 0:
        return None
    lot = inst.lot_size
    width = abs(short_k - long_k)
    width_value = width * lot
    credit_value = credit * lot
    if credit_value / width_value * 100 < r["min_credit_pct"]:
        return None
    cost = round_trip_cost(short_px, lot) + round_trip_cost(long_px, lot)
    return {
        "kind": "bull_put" if direction > 0 else "bear_call",
        "label": "Bull put spread" if direction > 0 else "Bear call spread",
        "direction": direction, "instrument": key, "expiry": expiry.isoformat(),
        "short_strike": short_k, "long_strike": long_k, "option_type": kind, "lot_size": lot,
        "short_premium": round(short_px, 2), "long_premium": round(long_px, 2),
        "premium_source": short_src if short_src == long_src else f"{short_src} / {long_src}",
        "credit": credit, "credit_value": round(credit_value, 2),
        "width": width, "width_value": round(width_value, 2),
        "margin": round(width_value, 2),
        "max_loss": round(width_value - credit_value + cost, 2),
        "charges": round(cost, 2),
        "target_debit": round(credit * (1 - r["target_pct"] / 100), 2),
        "stop_debit": round(credit * r["stop_mult"], 2),
        "credit_pct_of_width": round(credit_value / width_value * 100, 1),
        "symbol_hint": (f"{key} {expiry.strftime('%d %b').upper()} "
                        f"{int(short_k)}/{int(long_k)} {kind} spread"),
        "iv": round(sigma, 4),
    }


def mark(pos: dict, spot: float, now: datetime, vix: float | None = None,
         chain: list[dict] | None = None) -> tuple[float, str]:
    """What it costs to close both legs right now, per unit."""
    exp = date.fromisoformat(pos["expiry"])
    sigma = pos.get("iv") or (vix or 14) / 100
    kind = pos["option_type"]
    short_px, src1 = _premium(spot, pos["short_strike"], exp, sigma, kind, now, chain)
    long_px, src2 = _premium(spot, pos["long_strike"], exp, sigma, kind, now, chain)
    return round(max(short_px - long_px, 0.0), 2), src1 if src1 == src2 else f"{src1} / {src2}"


# ---------------------------------------------------------------- the book
class SpreadBook:
    """One isolated paper book. It never borrows and never touches the other books."""

    def __init__(self, path: Path | None = None, rules: dict | None = None):
        self.path = path or BOOK_FILE
        self.rules = {**SPREAD, **(rules or {})}
        self._lock = threading.RLock()
        self.state = self._load()

    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"open": None, "closed": []}
        except Exception as exc:  # noqa: BLE001
            log.error("spread book unreadable (%s) - starting flat, keeping the file", exc)
            return {"open": None, "closed": []}
        if not isinstance(state, dict) or "closed" not in state:
            return {"open": None, "closed": []}
        return state

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def equity(self) -> float:
        return round(self.rules["stake"] + sum(t.get("pnl", 0) for t in self.state["closed"]), 2)

    def today_closed(self, day: date) -> list[dict]:
        return [t for t in self.state["closed"] if t.get("closed_at", "")[:10] == day.isoformat()]

    # ---------- main hook ----------
    def on_analysis(self, a: dict, settings: dict | None = None) -> dict:
        with self._lock:
            key = a["instrument"]["key"]
            if key != "NIFTY":
                return {"events": [], "open": self.state["open"]}
            now = datetime.fromisoformat(a["generated_at"])
            spot = a.get("spot_live") or a.get("price")
            vix = (a.get("vix") or {}).get("value")
            events: list[dict] = []

            pos = self.state["open"]
            if pos:
                events += self._manage(pos, now, spot, vix, a)
                return {"events": events, "open": self.state["open"]}

            if not (a.get("session") or {}).get("is_open") or spot is None:
                return {"events": [], "open": None}
            if now.time() >= NO_ENTRY_AFTER:
                return {"events": [], "open": None}
            if len(self.today_closed(now.date())) >= self.rules["max_per_day"]:
                return {"events": [], "open": None}

            leg = a.get("orb") or {}
            verdict, direction = leg.get("verdict"), leg.get("direction") or 0
            if verdict not in ("BUY", "SELL") or direction == 0:
                return {"events": [], "open": None}
            expiry = date.fromisoformat((a.get("session") or {})["expiry"])
            chain = (a.get("chains") or {}).get(expiry.isoformat())
            p = plan(key, direction, float(spot), expiry, vix, now, chain, self.rules)
            if not p:
                return {"events": [], "open": None}
            if p["margin"] > self.equity:
                events.append({"type": "blocked", "reason": (
                    f"spread needs Rs {p['margin']:,.0f} of margin but the book has "
                    f"Rs {self.equity:,.0f} - skipped, never borrowed")})
                return {"events": events, "open": None}

            p.update({"opened_at": now.isoformat(), "entry_spot": float(spot), "strategy": "First-Hour",
                      "slot": f"{key}|spread", "mark": p["credit"], "rules_version": RULES_VERSION,
                      "unrealized": 0.0, "iv": p["iv"]})
            self.state["open"] = p
            self._save()
            events.append({"type": "spread_entry", "trade": p})
            return {"events": events, "open": p}

    def _manage(self, pos: dict, now: datetime, spot, vix, a: dict) -> list[dict]:
        exp = date.fromisoformat(pos["expiry"])
        lot = pos["lot_size"]
        d = pos["direction"]
        reason = None
        if now.date() > exp:
            # The contract is gone. `years_to_expiry` clamps to 60 seconds, so marking it would
            # price a dead option against today's spot and invent a P&L. Settle at the last mark.
            debit = float(pos.get("mark") or pos["credit"])
            src = "last mark (contract expired)"
            reason = "expired (last mark)"
        else:
            if spot is None:
                return []
            chain = (a.get("chains") or {}).get(pos["expiry"])
            debit, src = mark(pos, float(spot), now, vix, chain)
            pos["mark"] = debit
            pos["unrealized"] = round((pos["credit"] - debit) * lot - pos["charges"], 2)
            breached = float(spot) <= pos["short_strike"] if d > 0 else float(spot) >= pos["short_strike"]
            if debit <= pos["target_debit"]:
                reason = f"target ({self.rules['target_pct']:g}% of credit)"
            elif debit >= pos["stop_debit"]:
                reason = f"stop ({self.rules['stop_mult']:g}x credit)"
            elif breached:
                reason = "short strike breached"
            elif now.date() == exp and now.time() >= EXPIRY_CLOSE:
                reason = "expiry day close"
        if not reason:
            self._save()
            return []

        exit_cost = round_trip_cost(pos["short_premium"], lot) + round_trip_cost(pos["long_premium"], lot)
        pnl = round((pos["credit"] - debit) * lot - pos["charges"] - exit_cost, 2)
        closed = {**pos, "closed_at": now.isoformat(), "exit_spot": float(spot) if spot is not None else None,
                  "exit_debit": debit, "exit_source": src, "reason": reason,
                  "exit_charges": round(exit_cost, 2), "pnl": pnl}
        self.state["closed"].append(closed)
        self.state["open"] = None
        self._save()
        return [{"type": "spread_exit", "trade": closed}]

    # ---------- report ----------
    def report(self) -> dict:
        with self._lock:
            closed = self.state["closed"]
            wins = [t for t in closed if t["pnl"] > 0]
            pos = self.state["open"]
            by_version: dict[str, dict] = {}
            for t in closed:
                v = str(t.get("rules_version") or 1)
                b = by_version.setdefault(v, {"trades": 0, "wins": 0, "net": 0.0})
                b["trades"] += 1
                b["wins"] += 1 if t["pnl"] > 0 else 0
                b["net"] = round(b["net"] + t.get("pnl", 0), 2)
            return {
                "stake": self.rules["stake"],
                "equity": self.equity,
                "net": round(sum(t.get("pnl", 0) for t in closed), 2),
                "return_pct": round(sum(t.get("pnl", 0) for t in closed) / self.rules["stake"] * 100, 2),
                "trades": len(closed),
                "wins": len(wins),
                "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
                "rules_version": RULES_VERSION,
                "by_version": by_version,
                "open": pos,
                "closed": list(reversed(closed[-50:])),
                "rules": {k: self.rules[k] for k in
                          ("stake", "short_delta", "long_delta", "target_pct", "stop_mult", "max_per_day")},
                "note": ("One spread a day on the First-Hour signal, defined risk, theta collected "
                         "instead of paid, held to the expiry day. Version 1 closed the same afternoon "
                         "at 14:30 and lost money; those trades stay in the record, labelled v1. "
                         "A handful of trades is a sample, not a verdict."),
            }


_book: SpreadBook | None = None


def book() -> SpreadBook:
    global _book
    if _book is None:
        _book = SpreadBook()
    return _book


def on_analysis(a: dict, settings: dict | None = None) -> dict:
    return book().on_analysis(a, settings)


def report() -> dict:
    return book().report()
