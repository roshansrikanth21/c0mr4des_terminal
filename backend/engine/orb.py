"""Opening Range Playbook - FIRST-HOUR breakout (the best-validated rule in this project).

Rules:
1. 09:15-10:15 builds the first-hour range.
2. After 10:15, the first 5-minute CLOSE above the range high = BUY (CE); below the low = SELL (PE).
3. Filter: only BUY above yesterday's close, only SELL below it (trade with the day's side).
4. Stop: the opposite side of the range. Target: 2x the risk (never a fixed number of points -
   see target_plan: a flat 10-point target needs an 86.6% win rate on a quiet NIFTY day and
   94.7% on a wide one, while 2R needs 33.3% every day). Exit by 15:15 regardless.
5. One trade per day. No new entry after 15:00.

Evidence (modelled option premiums from real index + real India VIX, theta, slippage, charges, 1 lot):
- NIFTY, 2 years of hourly bars (Nov 2023 - Oct 2026): 549 trades, 44% winners, PF 1.41, +Rs 2.07L,
  profitable in 11 of 13 quarters; excluding expiry days PF 1.15 (+Rs 65k).
- SENSEX same period: PF 1.32, profitable in 12 of 13 quarters.
- NIFTY 5-minute bars, last 60 days: 51 trades, 49% winners, PF 2.1.
"""
from __future__ import annotations

from datetime import datetime, time

import pandas as pd

RR = 2.0
T945, T1015, T1500 = time(9, 45), time(10, 15), time(15, 0)


def target_plan(entry: float, stop: float, rr: float = RR) -> dict:
    """Stop, target and the win rate that target demands.

    A fixed number of points is the wrong instruction, because the stop is not fixed: the
    distance from the entry to the other end of the range changes every morning. With a flat
    10-point target the break-even win rate drifts with the range - 86.6% on a quiet NIFTY day,
    94.7% on a wide one - so the same rule is easy one day and impossible the next. Sizing the
    target as a multiple of the risk pins the requirement at 1/(1+rr) every single day.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        return {"risk_points": 0.0, "target": entry, "target_points": 0.0, "breakeven_win_rate": None}
    d = 1 if entry > stop else -1
    return {
        "risk_points": round(risk, 2),
        "target": round(entry + d * rr * risk, 2),
        "target_points": round(rr * risk, 2),
        "breakeven_win_rate": breakeven_win_rate(risk, rr * risk),
    }


def breakeven_win_rate(risk_points: float, target_points: float) -> float | None:
    """Win rate at which a target of `target_points` against a `risk_points` stop breaks even."""
    if risk_points <= 0 or target_points <= 0:
        return None
    return round(risk_points / (risk_points + target_points) * 100, 1)


def evaluate(df5: pd.DataFrame, prev_close: float | None, now: datetime) -> dict:
    today = now.date()
    day = df5[df5.index.date == today]
    base = {"name": "First-Hour Breakout", "verdict": "NO TRADE", "direction": 0}
    if day.empty:
        return {**base, "status": "waiting", "text": "Waiting for today's open. The first-hour range forms 09:15-10:15."}
    first = day[day.index.time < T1015]
    hi, lo = float(first.high.max()), float(first.low.min())
    info = {"range_high": hi, "range_low": lo, "range_points": round(hi - lo, 2), "prev_close": prev_close}
    if now.time() < T1015 or len(first) < 12:
        return {**base, **info, "status": "forming",
                "text": f"First-hour range is forming: {lo:.0f}-{hi:.0f} so far. No breakout trades before 10:15."}
    after = day[day.index.time >= T1015]
    for ts, bar in after.iterrows():
        c = float(bar.close)
        d = 1 if c > hi else -1 if c < lo else 0
        if d == 0:
            continue
        side_ok = prev_close is None or (c - prev_close) * d > 0
        if not side_ok:
            continue
        stop = lo if d > 0 else hi
        risk = abs(c - stop)
        target = c + d * RR * risk
        fresh = ts == after.index[-1]
        live = fresh and ts.time() < T1500
        word = "above the high" if d > 0 else "below the low"
        return {**base, **info, "status": "triggered" if live else "taken",
                "verdict": ("BUY" if d > 0 else "SELL") if live else "NO TRADE", "direction": d,
                "trigger_time": ts.isoformat(), "entry": c, "stop": stop, "target": target, "risk_points": risk,
                "target_points": RR * risk, "breakeven_win_rate": breakeven_win_rate(risk, RR * risk),
                "text": (f"{'NOW: ' if live else ''}Price closed {word} of the first-hour range at {ts.strftime('%H:%M')} "
                         f"({c:.0f}), on the {'right' if side_ok else 'wrong'} side of yesterday's close. "
                         f"Stop {stop:.0f} (other side of the range), target {target:.0f} (2x risk)."
                         + ("" if live else " Today's one trade has already triggered."))}
    last = float(day.close.iloc[-1])
    where = "inside" if lo <= last <= hi else "outside (but against yesterday's close)"
    return {**base, **info, "status": "waiting" if now.time() < T1500 else "done",
            "text": (f"First-hour range {lo:.0f}-{hi:.0f} ({hi - lo:.0f} pts). Price {last:.0f} is {where}. "
                     + ("Waiting for a 5-minute close outside the range." if now.time() < T1500 else "No breakout today - no trade."))}


def first30(df5: pd.DataFrame, now: datetime) -> dict:
    """Your rule: if 09:15-09:45 moved up, BUY at 09:45; if down, SELL. Stop at the middle of the
    first-30 range, hold to 15:15 (no target). Lab: NIFTY +48k, SENSEX +57k per lot, ~31% winners
    (few big winners pay for many small losers)."""
    base = {"name": "First-30 Direction", "verdict": "NO TRADE", "direction": 0}
    day = df5[df5.index.date == now.date()]
    first = day[day.index.time < T945]
    if now.time() < T945 or len(first) < 6:
        return {**base, "status": "forming", "text": "Watching which way the first 30 minutes move (09:15-09:45)."}
    o, c, hi, lo = float(first.open.iloc[0]), float(first.close.iloc[-1]), float(first.high.max()), float(first.low.min())
    d = 1 if c > o else -1 if c < o else 0
    if d == 0:
        return {**base, "status": "done", "text": "First 30 minutes closed flat - no trade."}
    stop = (hi + lo) / 2
    after = day[day.index.time >= T945]
    live = len(after) <= 2  # entry window 09:45-10:00 (tolerates a few minutes of feed delay)
    word = "UP (low to high)" if d > 0 else "DOWN (high to low)"
    return {**base, "status": "triggered" if live else "taken", "verdict": ("BUY" if d > 0 else "SELL") if live else "NO TRADE",
            "direction": d, "entry": c, "stop": stop, "target": None, "risk_points": abs(c - stop),
            "text": f"First 30 minutes went {word}: {o:.0f} -> {c:.0f}. {'Enter now' if live else 'Entered at 09:45'}, "
                    f"stop {stop:.0f} (middle of the range), hold to 15:15 - no target."}
