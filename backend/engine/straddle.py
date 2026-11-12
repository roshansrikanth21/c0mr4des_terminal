"""Expiry-day short straddle: two PAPER-ONLY books. Neither ever places an order.

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

The two books
-------------
  naked   the rule exactly as back-tested (research B07). File data/straddle_book.json.
  hedged  the lower-margin form (research/zoo_hedged_expiry.py): the same short straddle plus a call
          350 points above and a put 350 points below, bought as protection. When a short leg stops,
          its protective leg is sold with it. Back-test: profit factor 1.27 over six years but 1.04
          on unseen 2025-26, and only about 40% of the far-strike prices were real quotes. This book
          exists to replace those estimates with live prices. File data/straddle_hedged_book.json.

Both rules are frozen: do not tune them against their own paper results.

Rules (version 1, both books)
-----------------------------
  * NIFTY only, weekly expiry day only, one trade a day
  * entry between 09:20 and 09:25 at live Angel One prices; a missing live quote for any leg = no trade
  * sell 1 lot of the ATM call and 1 lot of the ATM put (hedged: also buy the +-350 point wings)
  * each short leg is bought back when its premium is 30% above the price it was sold at
  * anything still open is closed at 15:15

One difference from the back-test: the study saw prices every five minutes, these books see them on
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
HEDGED_FILE = DATA_DIR / "straddle_hedged_book.json"

RULES = {
    "instrument": "NIFTY",
    "entry_from": time(9, 20),
    "entry_until": time(9, 25),
    "leg_stop_pct": 30.0,
    "square_off": time(15, 15),
    "margin": 200_000.0,        # round assumption for one naked short straddle lot, not a broker quote
    "hedged_margin": 60_000.0,  # round assumption for the 350-point iron fly, not a broker quote
    "wing_steps": 7,            # 7 strikes of 50 = 350 points, the width picked on 2021-2024
    "slippage_pct": 0.5,        # per side, the same haircut the study used; reported next to the raw P&L
    "need_trades": 20,
}
RULES_VERSION = 1
KINDS = ("CE", "PE")
WING_SIGN = {"CE": 1, "PE": -1}
BACKTEST = {
    "naked": {"trades": 305, "profit_factor": 1.50, "worst_day": -9374, "since_tuesday_expiry_pf": 1.17,
              "source": "research/ZOO_RESULTS.md"},
    "hedged": {"trades": 305, "profit_factor": 1.27, "unseen_2025_26_pf": 1.04, "worst_day": -8583,
               "real_far_strike_prints_pct": 40, "source": "research/zoo_hedged_expiry.py"},
}


def chain_quotes(chain: list[dict] | None) -> dict[float, dict[str, float]]:
    """{strike: {"CE": ltp, "PE": ltp}} from the engine's live chain; missing or zero prices are left out."""
    out: dict[float, dict[str, float]] = {}
    for row in chain or []:
        legs = {k: float(row[k]["ltp"]) for k in KINDS if (row.get(k) or {}).get("ltp")}
        if legs:
            out[float(row["strike"])] = legs
    return out


_memo: dict = {}


def _live_quotes(key: str, expiry: date, strike: float) -> dict[float, dict[str, float]]:
    """One broker call covers the strike and the wings either side. Both books ask within the same engine
    pass, so the answer is kept for a few seconds instead of being fetched twice."""
    import time as _time

    from . import options  # late import: keeps this module importable without the broker stack

    tag = (key, expiry, float(strike))
    if _memo.get("tag") == tag and _time.time() - _memo.get("at", 0) < 5:
        return _memo["val"]
    val = chain_quotes(options.live_chain(key, expiry, strike, width=RULES["wing_steps"]))
    _memo.update(tag=tag, at=_time.time(), val=val)
    return val


class StraddleBook:
    def __init__(self, path: Path | None = None, quote_fn=None, wing_steps: int = 0):
        self.wing_steps = int(wing_steps)
        self.name = "hedged" if self.wing_steps else "naked"
        self.label = "EXPIRY IRON FLY (paper)" if self.wing_steps else "EXPIRY STRADDLE (paper)"
        self.path = path or (HEDGED_FILE if self.wing_steps else BOOK_FILE)
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

    def _wing_strike(self, strike: float, kind: str) -> float:
        return strike + WING_SIGN[kind] * self.wing_steps * INSTRUMENTS[RULES["instrument"]].strike_step

    def _needed(self, strike: float, legs: dict | None = None) -> list[tuple[float, str]]:
        """(strike, kind) of every price this book has to see: the short legs and, when hedged, their wings."""
        need = []
        for k in KINDS:
            if legs is not None and legs[k]["out"] is not None:
                continue
            need.append((strike, k))
            if self.wing_steps:
                need.append((self._wing_strike(strike, k), k))
        return need

    def _quotes(self, a: dict, expiry: str, strike: float, need: list[tuple[float, str]]) -> dict[float, dict[str, float]]:
        """Live prices: the chain the engine already fetched if it covers what is needed, else one dedicated
        quote. After 12:00 on expiry day the engine's own chain has rolled to next week."""
        have = chain_quotes((a.get("chains") or {}).get(expiry))
        if all(have.get(s, {}).get(k) for s, k in need):
            return have
        try:
            live = self.quote_fn(RULES["instrument"], date.fromisoformat(expiry), float(strike))
        except Exception as exc:  # noqa: BLE001 - a quote failure must never stop the desk
            log.warning("straddle quote failed: %s", exc)
            return have
        merged = {s: dict(v) for s, v in have.items()}
        for s, v in (live or {}).items():
            merged.setdefault(float(s), {}).update(v)
        return merged

    def _skip(self, today: str, why: str) -> list[dict]:
        if any(s["date"] == today for s in self.state["skipped"]):
            return []
        self.state["skipped"] = (self.state["skipped"] + [{"date": today, "why": why}])[-60:]
        self._save()
        return [{"type": "straddle_skip", "book": self.name, "text": f"{self.label}: no trade today - {why}."}]

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
        need = self._needed(strike)
        q = self._quotes(a, sess["expiry"], strike, need)
        if not all(q.get(s, {}).get(k, 0) > 0 for s, k in need):
            return []                      # a leg has no live price yet: retry until the window closes
        legs = {}
        for k in KINDS:
            p = q[strike][k]
            legs[k] = {"in": round(p, 2), "mark": round(p, 2), "out": None, "why": None, "closed_at": None}
            if self.wing_steps:
                wk = self._wing_strike(strike, k)
                wp = q[wk][k]
                legs[k].update(wing_strike=wk, wing_in=round(wp, 2), wing_mark=round(wp, 2), wing_out=None)
        self.state["open"] = {"date": today, "expiry": sess["expiry"], "strike": strike, "lot": inst.lot_size,
                              "opened_at": now.isoformat(), "entry_spot": spot, "rules_version": RULES_VERSION,
                              "book": self.name, "legs": legs}
        self._save()
        credit = sum(v["in"] - v.get("wing_in", 0.0) for v in legs.values())
        text = (f"{self.label} SOLD NIFTY {strike:.0f} CE @ {legs['CE']['in']:.2f} + PE @ {legs['PE']['in']:.2f}\n")
        if self.wing_steps:
            width = self.wing_steps * inst.strike_step
            text += (f"Protection bought: {legs['CE']['wing_strike']:.0f} CE @ {legs['CE']['wing_in']:.2f}, "
                     f"{legs['PE']['wing_strike']:.0f} PE @ {legs['PE']['wing_in']:.2f}. "
                     f"Net credit Rs {credit * inst.lot_size:,.0f}, most it can lose Rs {(width - credit) * inst.lot_size:,.0f}.\n")
        else:
            text += f"1 lot ({inst.lot_size}), credit Rs {credit * inst.lot_size:,.0f}. "
        text += (f"Each sold leg stops at +{RULES['leg_stop_pct']:.0f}%, flat by 15:15. Paper only: needs about "
                 f"Rs {RULES['hedged_margin' if self.wing_steps else 'margin']:,.0f} margin.")
        return [{"type": "straddle_entry", "book": self.name, "text": text}]

    def _manage(self, a: dict, now: datetime, sess: dict) -> list[dict]:
        pos = self.state["open"]
        events: list[dict] = []
        stale = pos["date"] != now.date().isoformat()
        strike = pos["strike"]
        q = {} if stale else self._quotes(a, pos["expiry"], strike, self._needed(strike, pos["legs"]))
        done = stale or now.time() >= RULES["square_off"] or not sess.get("is_open")
        for k in KINDS:
            leg = pos["legs"][k]
            if leg["out"] is not None:
                continue
            ltp = q.get(strike, {}).get(k)
            if ltp:
                leg["mark"] = round(ltp, 2)
            if "wing_strike" in leg:
                wltp = q.get(leg["wing_strike"], {}).get(k)
                if wltp:
                    leg["wing_mark"] = round(wltp, 2)
            stopped = not stale and ltp and ltp >= leg["in"] * (1 + RULES["leg_stop_pct"] / 100)
            if stopped:
                leg.update(out=round(ltp, 2), why="stop", closed_at=now.isoformat())
                events.append({"type": "straddle_stop", "book": self.name, "text": (
                    f"{self.label} STOP: {strike:.0f} {k} bought back @ {ltp:.2f} (sold @ {leg['in']:.2f})"
                    + (f", its {leg['wing_strike']:.0f} {k} protection sold @ {leg['wing_mark']:.2f}." if "wing_strike" in leg else "."))})
            elif done:
                why = "stale (square-off missed)" if stale else "15:15 square-off" if ltp else "15:15 at last mark (no quote)"
                leg.update(out=leg["mark"], why=why, closed_at=now.isoformat())
            if leg["out"] is not None and "wing_strike" in leg:
                leg["wing_out"] = leg["wing_mark"]           # the wing leaves with the leg it protects
        if all(pos["legs"][k]["out"] is not None for k in KINDS):
            closed = self._settle(pos, now)
            self.state["closed"].append(closed)
            self.state["open"] = None
            n = len(self.state["closed"])
            events.append({"type": "straddle_exit", "book": self.name, "text": (
                f"{self.label} CLOSED {strike:.0f}: P&L Rs {closed['pnl']:,.0f} after charges "
                f"(Rs {closed['pnl_after_slippage']:,.0f} with slippage). CE {closed['legs']['CE']['why']}, "
                f"PE {closed['legs']['PE']['why']}. Trade {n} of the {RULES['need_trades']} needed.")})
        self._save()
        return events

    @staticmethod
    def _settle(pos: dict, now: datetime) -> dict:
        lot = pos["lot"]
        gross = charges = slip = credit = 0.0
        for leg in pos["legs"].values():
            fills = [(-1, leg["in"], leg["out"])]                       # sold then bought back
            if "wing_strike" in leg:
                fills.append((1, leg["wing_in"], leg["wing_out"]))      # bought then sold
            for side, p_in, p_out in fills:
                gross += side * (p_out - p_in) * lot
                charges += round_trip_cost((p_in + p_out) / 2, lot)
                slip += RULES["slippage_pct"] / 100 * (p_in + p_out) * lot
                credit -= side * p_in * lot
        return {**pos, "closed_at": now.isoformat(), "credit": round(credit, 2), "charges": round(charges, 2),
                "pnl": round(gross - charges, 2), "pnl_after_slippage": round(gross - charges - slip, 2)}

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
            unreal = 0.0
            for leg in pos["legs"].values():
                unreal += (leg["in"] - (leg["out"] if leg["out"] is not None else leg["mark"])) * pos["lot"]
                if "wing_strike" in leg:
                    unreal += ((leg["wing_out"] if leg["wing_out"] is not None else leg["wing_mark"]) - leg["wing_in"]) * pos["lot"]
            unreal = round(unreal, 2)
        step = INSTRUMENTS[RULES["instrument"]].strike_step
        return {
            "book": self.name, "paper_only": True, "rules_version": RULES_VERSION,
            "rules": {"entry": "09:20-09:25 on weekly expiry day", "leg_stop_pct": RULES["leg_stop_pct"],
                      "square_off": "15:15", "wing_points": self.wing_steps * step,
                      "margin_assumed": RULES["hedged_margin" if self.wing_steps else "margin"],
                      "slippage_pct": RULES["slippage_pct"]},
            "backtest": BACKTEST[self.name],
            "trades": len(closed), "need_trades": RULES["need_trades"],
            "net": round(sum(t["pnl"] for t in closed), 2), "net_after_slippage": round(sum(pnl), 2),
            "win_rate": round(100 * len(wins) / len(pnl), 1) if pnl else None,
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
            "worst_day": round(min(pnl), 2) if pnl else None, "worst_streak": worst, "max_drawdown": round(dd, 2),
            "open": pos, "unrealized": unreal, "closed": closed[::-1], "skipped": self.state["skipped"][-10:],
        }


_books: dict[str, StraddleBook] = {}


def books() -> dict[str, StraddleBook]:
    if not _books:
        _books["naked"] = StraddleBook()
        _books["hedged"] = StraddleBook(wing_steps=RULES["wing_steps"])
    return _books


def book() -> StraddleBook:
    return books()["naked"]


def on_analysis(a: dict) -> dict:
    """Run both books on one analysis. One book failing must not stop the other."""
    events: list[dict] = []
    for b in books().values():
        try:
            events += b.on_analysis(a)["events"]
        except Exception:  # noqa: BLE001
            log.exception("straddle book %s failed", b.name)
    return {"events": events}


def report() -> dict:
    """The naked book at the top level (as before), the hedged book under "hedged"."""
    return {**books()["naked"].report(), "hedged": books()["hedged"].report()}
