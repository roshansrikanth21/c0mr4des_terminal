"""One signal feed, four isolated paper accounts: does capital size change the outcome?

The owner's question is narrow and worth answering honestly: run the same live signals on
Rs 10k, Rs 30k and Rs 50k, never move money between them, and see which stake actually yields.
A fourth book (Rs 10k, puts only) tests the "trade short as the main trade" hunch as its own
case instead of forcing bearish trades into the capital comparison.

Rules, chosen before the week so the result cannot be rationalised afterwards:

* One trade at a time, long options only. A SELL verdict means BUY PE - the engine has no
  shorting, and selling options would need margin this app cannot see.
* One trade per day. A second is allowed only if that day's first closed trade made money -
  losing days stop at one. This is the owner's 1-2 trades/day rule, applied to every book so
  the comparison stays fair.
* Size = 20% of current equity of stop-risk, at least one lot, capped per case
  (A 1 lot, B 3, C 4, D 1) and by what the equity can actually pay for. The lot floor is the
  market's, not a choice: one NIFTY lot is already ~60% of Rs 10k.
* No borrowing. If one lot costs more than the book's equity, the trade is skipped, not taken.
* Bust rule: when equity falls below the cheapest one-lot cost, the era is over. The book is
  snapshotted to ``{id}_bust{n}.json`` (nothing is ever deleted) and the case restarts at its
  original stake. Busts are counted, not hidden.

Everything here is a study aid. It never places a live order and never touches the main paper
book; a failure in this module must not be able to stop the market loop.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import date, datetime
from pathlib import Path

from .config import IST, INSTRUMENTS
from .options import MAX_LOTS, round_trip_cost
from .trader import PaperTrader, scorecard

log = logging.getLogger("engine.capital_test")

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "capital_test"
META_FILE = DATA_DIR / "meta.json"
WEEK_DAYS = 7

# The rule set is fixed for the whole week. Changing it mid-week invalidates the comparison.
CASES = (
    {"id": "A", "label": "Rs 10,000", "capital": 10_000.0, "puts_only": False, "max_lots": 1,
     "risk_pct": 20.0, "daily_loss_pct": 25.0,
     "rule": "1 lot max. One NIFTY lot is already ~60% of this stake, so a single gap can end it."},
    {"id": "B", "label": "Rs 30,000", "capital": 30_000.0, "puts_only": False, "max_lots": 3,
     "risk_pct": 20.0, "daily_loss_pct": 25.0,
     "rule": "3 lots max - about one lot per Rs 10k, with room for a second trade."},
    {"id": "C", "label": "Rs 50,000", "capital": 50_000.0, "puts_only": False, "max_lots": 4,
     "risk_pct": 20.0, "daily_loss_pct": 25.0,
     "rule": "4 lots max - the engine's hard cap. Extra capital mostly stays idle."},
    {"id": "D", "label": "Rs 10,000 puts only", "capital": 10_000.0, "puts_only": True, "max_lots": 1,
     "risk_pct": 20.0, "daily_loss_pct": 25.0,
     "rule": "Same as A, but only BUY PE signals. Tests the 'short as the main trade' idea in isolation."},
)

STRATEGIES = {"orb": "First-Hour", "first30": "First-30"}
PRIORITY = ("orb", "first30")  # First-Hour triggers first; First-30 only if it did not


def _meta() -> dict:
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing/corrupt meta must not stop the study
        return {}


def _start_clock(when: datetime) -> None:
    """Pin the week's start to the first real analysis, not to the deploy time."""
    if META_FILE.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps({"started_at": when.isoformat(timespec="seconds"),
                                     "week_days": WEEK_DAYS}, indent=1), encoding="utf-8")


class CaseBook(PaperTrader):
    """One isolated account: its own file, its own equity, its own daily budget."""

    def __init__(self, spec: dict):
        self.spec = spec
        self._case_lock = threading.RLock()
        super().__init__(DATA_DIR / f"{spec['id']}.json")

    # ---------- money ----------
    def equity(self) -> float:
        """Cash the case actually has: original stake plus everything it has realised this era."""
        return round(self.spec["capital"] + sum(t.get("pnl", 0) for t in self.state["closed"]), 2)

    def _snapshots(self) -> list[Path]:
        own = list(self.path.parent.glob(f"{self.path.stem}_bust*.json"))

        def n(p: Path) -> int:
            try:
                return int(p.stem.rsplit("_bust", 1)[1])
            except Exception:  # noqa: BLE001
                return 0

        return sorted(own, key=n)

    def all_closed(self) -> list[dict]:
        """Every trade this case ever made, including eras that busted (oldest first)."""
        out: list[dict] = []
        for p in self._snapshots():
            try:
                out.extend(json.loads(p.read_text(encoding="utf-8")).get("closed", []))
            except Exception:  # noqa: BLE001 - a broken snapshot must not hide the live era
                log.error("capital test %s: unreadable snapshot %s", self.spec["id"], p.name)
        out.extend(self.state["closed"])
        return out

    def _bust(self) -> int:
        with self._case_lock:
            n = len(self._snapshots()) + 1
            snap = self.path.with_name(f"{self.path.stem}_bust{n}.json")
            try:
                shutil.copy2(self.path, snap)
            except Exception:  # noqa: BLE001
                log.exception("capital test %s: could not snapshot the busted book", self.spec["id"])
            self.reset()
            log.warning("capital test %s busted - era %d archived to %s, reset to Rs %s",
                        self.spec["id"], n, snap.name, f"{self.spec['capital']:,.0f}")
            return n

    def _lot_floor(self, a: dict) -> float | None:
        """The cheapest one-lot purchase available right now, charges included."""
        sides = a.get("sides") or {}
        costs = [s.get("worst_case") or s.get("lot_cost") for s in sides.values()
                 if isinstance(s, dict) and (s.get("worst_case") or s.get("lot_cost"))]
        if self.spec["puts_only"]:
            put = sides.get("put") or {}
            own = put.get("worst_case") or put.get("lot_cost")
            costs = [own] if own else []
        if costs:
            return float(min(costs))
        opt = a.get("option") or {}
        if opt.get("premium"):
            lot = INSTRUMENTS[a["instrument"]["key"]].lot_size
            return float(opt["premium"]) * lot + round_trip_cost(float(opt["premium"]), lot)
        return None

    # ---------- rules ----------
    def budget_today(self, day: date) -> int:
        """One trade, plus a second only when the day's first trade closed green."""
        done = sorted(self.today_closed(day=day), key=lambda t: t.get("closed_at", ""))
        if done and done[0].get("pnl", 0) > 0:
            return 2
        return 1

    def _size(self, option: dict, key: str, equity: float) -> tuple[int, int, float]:
        """Lots for this case, the lots the equity can fund, and the stop-risk of one lot."""
        inst = INSTRUMENTS[key]
        premium = float(option["premium"])
        prem_stop = float(option.get("premium_stop") or premium)
        risk_per_lot = max(premium - prem_stop, 0.01) * inst.lot_size
        budget = equity * self.spec["risk_pct"] / 100.0
        affordable = int(equity // max(premium * inst.lot_size, 1))
        lots = int(budget // risk_per_lot)
        lots = max(0, min(lots, affordable, self.spec["max_lots"], MAX_LOTS))
        return lots, affordable, risk_per_lot

    @staticmethod
    def _plan(leg: dict) -> dict:
        return {"direction": leg.get("direction", 0), "stop": leg.get("stop"), "target": leg.get("target")}

    # ---------- main hook ----------
    def on_analysis(self, a: dict, settings: dict) -> dict:
        with self._case_lock:
            key = a["instrument"]["key"]
            if key not in settings.get("autopilot_instruments", ["NIFTY"]):
                return {"events": [], "open": []}
            now = datetime.fromisoformat(a["generated_at"])
            events: list[dict] = []

            open_slots = [s for s in self.state["open"] if s.startswith(key + "|")]
            if open_slots:
                for slot in open_slots:
                    suffix = slot.split("|", 1)[1]
                    events += self._process(slot, STRATEGIES.get(suffix, suffix), None, None, {},
                                            a, self._settings(settings, self.equity()), self.budget_today(now.date()))
                return {"events": events, "open": self._open(key)}

            # A busted book must not be traded again until it has a fresh stake to trade with.
            # Ruin is measured against the cheapest instrument the book can trade (NIFTY by
            # default), not against a pricier SENSEX lot it simply chose not to buy today. And
            # only a book that actually lost money can bust: if the original stake cannot fund
            # today's lot, resetting it would just produce the same impossible comparison forever.
            instruments = settings.get("autopilot_instruments") or ["NIFTY"]
            ruin_key = "NIFTY" if "NIFTY" in instruments else key
            floor = self._lot_floor(a)
            if floor and self.equity() < floor:
                if key == ruin_key and self.state["closed"]:
                    events.append({"type": "bust", "case": self.spec["id"], "era": self._bust(),
                                   "equity": self.equity(), "needed": round(floor, 2)})
                else:
                    events.append({"type": "blocked",
                                   "reason": (f"{self.spec['id']}: one {key} lot costs Rs {floor:,.0f} today, "
                                              f"more than the whole Rs {self.spec['capital']:,.0f} stake - "
                                              f"no trade rather than invented money")})
                return {"events": events, "open": []}

            allowed = self.budget_today(now.date())
            if len(self.today_closed(day=now.date())) >= allowed:
                return {"events": events, "open": []}

            equity = self.equity()
            for suffix in PRIORITY:
                leg = a.get(suffix) or {}
                verdict = leg.get("verdict")
                option = leg.get("option")
                plan = self._plan(leg)
                strategy = STRATEGIES[suffix]
                if verdict not in ("BUY", "SELL") or not option or plan.get("stop") is None:
                    continue
                if self.spec["puts_only"] and (verdict != "SELL" or option.get("option_type") != "PE"):
                    continue
                if (a.get("spot_live") or a["price"]) is not None:
                    spot = a.get("spot_live") or a["price"]
                    if (float(spot) - float(plan["stop"])) * int(plan["direction"]) <= 0:
                        continue
                lots, affordable, risk_per_lot = self._size(option, key, equity)
                if affordable < 1:
                    one = float(option["premium"]) * INSTRUMENTS[key].lot_size
                    events.append({"type": "blocked",
                                   "reason": (f"{self.spec['id']} {strategy}: one lot costs Rs {one:,.0f} "
                                              f"but the book has Rs {equity:,.0f} - skipped, never borrowed")})
                    continue
                # lots == 0 means the risk budget cannot fund a full lot; the paper book floors it to
                # one and flags it oversize, so the record stays honest.
                sized = {**option, "lots": lots}
                events += self._process(f"{key}|{suffix}", strategy, verdict, sized, plan, a,
                                        self._settings(settings, equity), allowed)
                break  # one decision per analysis: the next one waits for the next tick
            return {"events": events, "open": self._open(key)}

    def _settings(self, base: dict, equity: float) -> dict:
        return {**base, "capital": equity, "risk_per_trade_pct": self.spec["risk_pct"],
                "max_daily_loss_pct": self.spec["daily_loss_pct"], "max_open_positions": 1,
                "autopilot_strategies": list(STRATEGIES.values())}

    def _open(self, key: str) -> list[dict]:
        return [p for s, p in self.state["open"].items() if s.startswith(key + "|")]

    # ---------- report ----------
    def report(self) -> dict:
        with self._case_lock:
            closed = self.all_closed()
            sc = scorecard(closed)
            snaps = self._snapshots()
            eras = 1 + len(snaps)
            stake = self.spec["capital"] * eras
            era_closed = self.state["closed"]
            today = datetime.now(IST).date()
            return {
                "id": self.spec["id"], "label": self.spec["label"], "capital": self.spec["capital"],
                "rule": self.spec["rule"], "puts_only": self.spec["puts_only"],
                "max_lots": self.spec["max_lots"], "risk_pct": self.spec["risk_pct"],
                "daily_loss_pct": self.spec["daily_loss_pct"],
                "equity": self.equity(), "era_net": round(sum(t.get("pnl", 0) for t in era_closed), 2),
                "net": sc["net"], "stake": stake, "eras": eras, "busts": len(snaps),
                "return_pct": round(sc["net"] / stake * 100, 2) if stake else 0.0,
                "trades": sc["trades"], "win_rate": sc["win_rate"], "payoff": sc["payoff"],
                "worst_streak": sc["worst_streak"], "oversize": sc["oversize"],
                "charges": round(sum(t.get("charges", 0) for t in closed), 2),
                "ce": sum(1 for t in closed if t.get("option_type") == "CE"),
                "pe": sum(1 for t in closed if t.get("option_type") == "PE"),
                "today": {"trades": len([t for t in closed if t.get("opened_at", "")[:10] == today.isoformat()]),
                          "pnl": round(sum(t.get("pnl", 0) for t in closed
                                           if t.get("opened_at", "")[:10] == today.isoformat()), 2)},
                "open": list(self.state["open"].values()),
                "closed": list(reversed(closed[-60:])),
            }


BOOKS = tuple(CaseBook(spec) for spec in CASES)


def on_analysis(a: dict, settings: dict) -> dict:
    """Run all four books. Never raises into the caller - the main loop outranks the study."""
    if (a.get("session") or {}).get("is_open"):
        # The week starts on the first live session, not on a deploy or an after-hours poll.
        try:
            _start_clock(datetime.fromisoformat(a["generated_at"]))
        except Exception:  # noqa: BLE001
            log.exception("capital test: could not start the week clock")
    out = {}
    for book in BOOKS:
        try:
            out[book.spec["id"]] = book.on_analysis(a, settings)
        except Exception:  # noqa: BLE001
            log.exception("capital test case %s failed - other cases continue", book.spec["id"])
    return out


def report() -> dict:
    meta = _meta()
    cases = [b.report() for b in BOOKS]
    started = meta.get("started_at")
    day_index = None
    if started:
        try:
            day_index = (datetime.now(IST).date() - date.fromisoformat(started[:10])).days + 1
        except Exception:  # noqa: BLE001
            day_index = None
    best = None
    traded = [c for c in cases if c["trades"] > 0]
    if traded:
        best = max(traded, key=lambda c: c["return_pct"])
    return {
        "started_at": started, "day_index": day_index, "week_days": WEEK_DAYS,
        "cases": cases,
        "leader": best["id"] if best else None,
        "note": ("One week on the same signals is behavioural evidence about sizing, not proof of an edge. "
                 "Four or five trades per case is a sample, not a verdict; the return % divides the case's "
                 "total net by every rupee it ever staked (original stake x eras), so a reset is not hidden."),
        "rules": ("Long options only. One trade at a time; a second only after the day's first trade closed "
                  "green. 20% stop-risk per trade, at least one lot, capped at each case's lot limit and by "
                  "equity - no borrowing. A book that cannot fund one lot is reset to its original stake and "
                  "the old era is archived."),
    }


def restart() -> dict:
    """Archive all four books and start a fresh week. Files are moved, never deleted."""
    if DATA_DIR.exists():
        stamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
        archive = DATA_DIR / f"archive-{stamp}"
        archive.mkdir(parents=True, exist_ok=True)
        for p in DATA_DIR.glob("*.json*"):
            shutil.move(str(p), str(archive / p.name))
    for book in BOOKS:
        book.state = {"open": {}, "closed": []}
        book._save()
    log.warning("capital test restarted - previous week archived")
    return report()
