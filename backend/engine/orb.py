"""Opening Range Playbook (best performer in the strategy lab on real NIFTY data).

Rules:
1. 09:15-09:45 builds the opening range (high/low of the first 30 minutes).
2. After 09:45, the first 5-minute CLOSE above the range high = BUY (CE); below the low = SELL (PE).
3. Filter: only BUY if price is above yesterday's close, only SELL if below it (trade with the day's side).
4. Stop: the opposite side of the range. Target: 1.5x the risk. Exit by 15:15 regardless.
5. One trade per day. No new entry after 15:00.
Lab result (Jul-Oct 2026, 1 lot NIFTY, modelled option premiums + costs): 48 trades, 56% winners, PF 2.6.
"""
from __future__ import annotations

from datetime import datetime, time

import pandas as pd

RR = 1.5
T945, T1500 = time(9, 45), time(15, 0)


def evaluate(df5: pd.DataFrame, prev_close: float | None, now: datetime) -> dict:
    today = now.date()
    day = df5[df5.index.date == today]
    base = {"name": "Opening Range Playbook", "verdict": "NO TRADE", "direction": 0}
    if day.empty:
        return {**base, "status": "waiting", "text": "Waiting for today's open. The opening range forms 09:15-09:45."}
    first = day[day.index.time < T945]
    hi, lo = float(first.high.max()), float(first.low.min())
    info = {"range_high": hi, "range_low": lo, "range_points": round(hi - lo, 2), "prev_close": prev_close}
    if now.time() < T945 or len(first) < 6:
        return {**base, **info, "status": "forming",
                "text": f"Opening range is forming: {lo:.0f}-{hi:.0f} so far. Don't trade the first 30 minutes; let it settle."}
    after = day[day.index.time >= T945]
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
                "target_points": RR * risk,
                "text": (f"{'NOW: ' if live else ''}Price closed {word} of the opening range at {ts.strftime('%H:%M')} "
                         f"({c:.0f}), on the {'right' if side_ok else 'wrong'} side of yesterday's close. "
                         f"Stop {stop:.0f} (other side of the range), target {target:.0f} (1.5x risk)."
                         + ("" if live else " Today's one trade has already triggered."))}
    last = float(day.close.iloc[-1])
    where = "inside" if lo <= last <= hi else "outside (but against yesterday's close)"
    return {**base, **info, "status": "waiting" if now.time() < T1500 else "done",
            "text": (f"Opening range {lo:.0f}-{hi:.0f} ({hi - lo:.0f} pts). Price {last:.0f} is {where}. "
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
            "direction": d, "entry": c, "stop": stop, "target": c + d * 50 * abs(c - stop), "risk_points": abs(c - stop),
            "target_points": 3 * abs(c - stop),
            "text": f"First 30 minutes went {word}: {o:.0f} -> {c:.0f}. {'Enter now' if live else 'Entered at 09:45'}, stop {stop:.0f} (middle of the range), hold to 15:15."}
