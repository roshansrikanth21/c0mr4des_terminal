"""Paper prop-firm challenge: the one rule research/PROP_RESULTS.md left standing, run forward on free prices.

PAPER ONLY. No broker, no account, no fee, no order. It answers one question before any challenge is bought:
does the daily RSI-2 pullback (S12) keep working on prices it has never seen, and would it have passed?

Rule, frozen at version 1 (identical to research/prop_zoo.py `daily`, S12):
  markets   EURUSD, GBPUSD, USDJPY, AUDUSD, gold, S&P 500, Nasdaq 100
  bars      UTC days built from hourly bars; a day needs 18 hours; weekdays only
  long      close above the 200-day average and RSI(2) below 10
  short     close below the 200-day average and RSI(2) above 90
  stop      2 x ATR(14) from the entry close; a gap through the stop fills at the open
  exit      close back across the 5-day average, or after 5 days, at the close
  size      every trade risks the same amount (1R); one position per market
  costs     a round-trip spread + commission per market (COST); overnight financing is NOT charged

Challenge, read off the closed trades (two-step form): +10%, then +5%, account dead on a day that loses 5% or a
total loss of 10%; once funded, 80% of profit is paid every 14 days. Shown for 1% and 2% risk a trade on a paper
$100,000. Losses count when a trade closes; open losses are not marked (flattering). A failed attempt restarts.

Prices: Yahoo hourly (futures for gold and the two indices), so fills differ a little from a prop firm's CFD feed.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("propbook")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BOOK_FILE = DATA_DIR / "prop_book.json"

MARKETS = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X", "AUDUSD": "AUDUSD=X",
           "XAUUSD": "GC=F", "US500": "ES=F", "NAS100": "NQ=F"}
COST = {"EURUSD": 0.00010, "GBPUSD": 0.00014, "USDJPY": 0.014, "AUDUSD": 0.00012, "XAUUSD": 0.40, "US500": 0.7, "NAS100": 2.5}
RULES = {"version": 1, "stop_atr": 2.0, "max_days": 5, "min_risk_costs": 4, "account": 100_000, "risk_pcts": [1.0, 2.0],
         "phase_targets": [10.0, 5.0], "daily_loss": 5.0, "total_loss": 10.0, "payout_share": 0.8, "payout_days": 14,
         "need_trades": 60}
BACKTEST = {"build_2021_24": {"trades": 315, "avg_R": 0.105, "pf": 1.57}, "judge_2025_26": {"trades": 151, "avg_R": 0.070, "pf": 1.34},
            "note": "t-statistic 1.5 on the unseen years: positive, not settled. Carried by the two US indices."}


def daily_bars(hourly: pd.DataFrame, today_utc) -> pd.DataFrame:
    """Completed UTC weekdays with at least 18 hourly bars."""
    h = hourly[hourly.index.dayofweek < 5]
    d = h.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d = d[h["close"].resample("1D").count().reindex(d.index) >= 18]
    return d[d.index < pd.Timestamp(today_utc)]


def signals(d: pd.DataFrame) -> pd.DataFrame:
    c = d["close"]
    pc = c.shift()
    tr = np.maximum(d["high"] - d["low"], np.maximum((d["high"] - pc).abs(), (d["low"] - pc).abs()))
    diff = c.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-diff.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    r2 = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    s200, s5 = c.rolling(200).mean(), c.rolling(5).mean()
    out = d.copy()
    out["atr"] = tr.rolling(14).mean()
    out["go"] = np.where((r2 < 10) & (c > s200), 1, np.where((r2 > 90) & (c < s200), -1, 0))
    out["out_long"], out["out_short"] = c > s5, c < s5
    return out


def _yahoo_hourly(symbol: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf

        df = yf.download(symbol, interval="1h", period="730d", progress=False, auto_adjust=False, multi_level_index=False, threads=False)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
        idx = pd.DatetimeIndex(df.index)
        df.index = (idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")).tz_localize(None)
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("prop book: Yahoo hourly failed for %s: %s", symbol, exc)
        return None


def challenge(closed: list[dict], risk_pct: float, upto: str | None = None) -> dict:
    """Walk the closed trades day by day through the challenge rules. Pure function of the trade list."""
    by_day: dict[str, float] = {}
    for t in closed:
        by_day[t["exit_day"]] = by_day.get(t["exit_day"], 0.0) + t["R"] * risk_pct
    st = {"risk_pct": risk_pct, "attempt": 1, "phase": 1, "equity_pct": 0.0, "failed": 0, "passed_on": None, "paid_pct": 0.0,
          "worst_day_pct": 0.0, "history": []}
    if not by_day:
        return st
    day, last = datetime.fromisoformat(min(by_day)), datetime.fromisoformat(max(upto or "", max(by_day)))
    funded_from = None
    while day <= last:
        key = day.date().isoformat()
        pnl = by_day.get(key, 0.0)
        st["equity_pct"] += pnl
        st["worst_day_pct"] = min(st["worst_day_pct"], pnl)
        if pnl <= -RULES["daily_loss"] or st["equity_pct"] <= -RULES["total_loss"]:
            st["history"].append(f"{key}: attempt {st['attempt']} failed in {'funded' if st['phase'] == 3 else 'phase ' + str(st['phase'])}")
            st.update(attempt=st["attempt"] + 1, phase=1, equity_pct=0.0, failed=st["failed"] + 1)
            funded_from = None
        elif st["phase"] < 3 and st["equity_pct"] >= RULES["phase_targets"][st["phase"] - 1]:
            st["history"].append(f"{key}: attempt {st['attempt']} passed phase {st['phase']}")
            st.update(phase=st["phase"] + 1, equity_pct=0.0)
            if st["phase"] == 3:
                st["passed_on"], funded_from = st["passed_on"] or key, day
        elif st["phase"] == 3 and (day - funded_from).days and (day - funded_from).days % RULES["payout_days"] == 0 and st["equity_pct"] > 0:
            paid = RULES["payout_share"] * st["equity_pct"]
            st["history"].append(f"{key}: payout {paid:.2f}% of the account")
            st["paid_pct"] += paid
            st["equity_pct"] = 0.0
        day += timedelta(days=1)
    st["equity_pct"], st["paid_pct"] = round(st["equity_pct"], 3), round(st["paid_pct"], 3)
    return st


def _phase_name(st: dict) -> str:
    if st["phase"] == 3:
        return f"FUNDED, {st['equity_pct']:+.2f}% since last payout, {st['paid_pct']:.2f}% paid"
    return f"phase {st['phase']}, {st['equity_pct']:+.2f}% of {RULES['phase_targets'][st['phase'] - 1]:.0f}%"


class PropBook:
    def __init__(self, path: Path = BOOK_FILE, fetch=_yahoo_hourly):
        self.path, self.fetch, self.lock = Path(path), fetch, threading.Lock()
        self.state = {"version": RULES["version"], "started": None, "checked": None, "last_day": {}, "open": {}, "closed": []}
        if self.path.exists():
            try:
                self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                log.exception("prop book unreadable, starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    # one completed day for one market: exactly research/prop_zoo.machine, one step
    def step(self, sym: str, row: pd.Series) -> list[dict]:
        day = row.name.date().isoformat()
        ev, pos = [], self.state["open"].get(sym)
        if pos:
            pos["days"] += 1
            side, stop, px, why = pos["side"], pos["stop"], None, None
            if side * (row["open"] - stop) <= 0:
                px, why = float(row["open"]), "stop (gap)"
            elif (row["low"] <= stop) if side > 0 else (row["high"] >= stop):
                px, why = stop, "stop"
            elif (row["out_long"] if side > 0 else row["out_short"]) or pos["days"] >= RULES["max_days"]:
                px, why = float(row["close"]), "5-day average" if (row["out_long"] if side > 0 else row["out_short"]) else "5 days"
            if px is not None:
                r = (side * (px - pos["entry"]) - COST[sym]) / pos["risk"]
                t = {**pos, "sym": sym, "exit": round(px, 5), "exit_day": day, "reason": why, "R": round(r, 4)}
                self.state["closed"].append(t)
                del self.state["open"][sym]
                ev.append({"type": "prop_exit", "trade": t})
            return ev
        atr = row["atr"]
        if row["go"] and atr == atr and RULES["stop_atr"] * atr >= RULES["min_risk_costs"] * COST[sym]:
            side, risk = int(row["go"]), float(RULES["stop_atr"] * atr)
            pos = {"side": side, "entry": round(float(row["close"]), 5), "stop": round(float(row["close"]) - side * risk, 5),
                   "risk": risk, "entry_day": day, "days": 0}
            self.state["open"][sym] = pos
            ev.append({"type": "prop_entry", "trade": {**pos, "sym": sym}})
        return ev

    def tick(self, now: datetime | None = None) -> dict:
        """Once per UTC day, shortly after midnight: process the day that just completed for every market."""
        now = now or datetime.now(timezone.utc)
        today = now.date().isoformat()
        with self.lock:
            if self.state["checked"] == today or (now.hour == 0 and now.minute < 10):
                return {"events": []}
            before = {r: len(challenge(self.state["closed"], r)["history"]) for r in RULES["risk_pcts"]}
            events, complete = [], True
            for sym, ticker in MARKETS.items():
                h = self.fetch(ticker)
                if h is None or len(h) < 24 * 250:
                    complete = False
                    continue
                d = signals(daily_bars(h, today))
                new = d[d.index > pd.Timestamp(self.state["last_day"].get(sym, "1900-01-01"))]
                if new.empty:
                    continue
                if sym not in self.state["last_day"]:
                    new = new.iloc[-1:]                      # first run: never back-fill trades
                for _, row in new.iterrows():
                    events += self.step(sym, row)
                self.state["last_day"][sym] = new.index[-1].date().isoformat()
            self.state["started"] = self.state["started"] or today
            if complete:
                self.state["checked"] = today
            self._save()
            for e in events:
                e["text"] = self._text(e)
            for r in RULES["risk_pcts"]:
                after = challenge(self.state["closed"], r)
                for line in after["history"][before[r]:]:      # each pass, fail or payout that this day produced
                    events.append({"type": "prop_phase",
                                   "text": f"PROP CHALLENGE (paper, {r:.0f}% risk): {line}. Now {_phase_name(after)}."})
            return {"events": events}

    def _text(self, e: dict) -> str:
        t = e["trade"]
        acct, r1 = RULES["account"], RULES["risk_pcts"][0]
        if e["type"] == "prop_entry":
            return (f"PROP PAPER: {'BUY' if t['side'] > 0 else 'SELL'} {t['sym']} at {t['entry']:,} "
                    f"({'dip in an uptrend' if t['side'] > 0 else 'bounce in a downtrend'}, daily). Stop {t['stop']:,}. "
                    f"Risk {r1:.0f}% = ${acct * r1 / 100:,.0f} on the paper ${acct:,}. No real order.")
        st = challenge(self.state["closed"], r1)
        return (f"PROP PAPER: closed {t['sym']} at {t['exit']:,} ({t['reason']}): {t['R']:+.2f}R = ${t['R'] * acct * r1 / 100:+,.0f}. "
                f"Challenge at {r1:.0f}% risk: {_phase_name(st)}. Trades {len(self.state['closed'])}/{RULES['need_trades']}.")

    def report(self) -> dict:
        with self.lock:
            closed = list(self.state["closed"])
            rs = [t["R"] for t in closed]
            wins, losses = sum(r for r in rs if r > 0), -sum(r for r in rs if r <= 0)
            return {"paper_only": True, "rules": RULES, "markets": list(MARKETS), "started": self.state["started"],
                    "last_day": self.state["last_day"], "open": self.state["open"], "closed": closed[-50:],
                    "trades": len(rs), "need_trades": RULES["need_trades"],
                    "win_rate": round(100 * sum(r > 0 for r in rs) / len(rs), 1) if rs else None,
                    "avg_R": round(sum(rs) / len(rs), 3) if rs else None, "total_R": round(sum(rs), 2),
                    "profit_factor": round(wins / losses, 2) if losses else None,
                    "challenge": {f"{r:.0f}%": challenge(closed, r, self.state["checked"]) for r in RULES["risk_pcts"]},
                    "backtest": BACKTEST,
                    "caveats": ["financing not charged", "open losses not marked", "Yahoo prices, not a prop firm's feed",
                                "no consistency, news or weekend rules"]}


_book: PropBook | None = None


def book() -> PropBook:
    global _book
    if _book is None:
        _book = PropBook()
    return _book


def tick(now: datetime | None = None) -> dict:
    return book().tick(now)


def report() -> dict:
    return book().report()
