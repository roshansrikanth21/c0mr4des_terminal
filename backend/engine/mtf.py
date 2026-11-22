"""Multi-timeframe read: what the market is doing at every speed at once.

The point is not to predict. It is to answer one question the single-timeframe score
cannot: *is the fast move going with the slow trend, or is it fighting it?* A 5-minute
sell-off inside a daily uptrend is a buying opportunity; the same 5-minute sell-off
inside a daily downtrend is a warning. Only a ladder tells them apart.

Timeframe honesty note: NSE trades 09:15-15:30, i.e. 6h15m per session. A "4-hour"
bar therefore holds about half a session, so there are roughly two per day and it
reads much like the daily. We show it because owners ask for it, but we count it
with a small weight so it does not double-count the daily.

`ladder()` is a pure function of candles, exactly like `signal.evaluate()`, so live
and replay run the same code.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import adx, atr, ema, linreg_slope, rsi, supertrend

# tf, label, weight in the confluence, minimum bars before the row is trustworthy
_ROWS = [
    ("1d", "Daily", 2.2, 20),
    ("4h", "4-hour", 0.6, 20),
    ("60min", "1-hour", 1.5, 25),
    ("15min", "15-minute", 1.2, 25),
    ("5min", "5-minute", 0.9, 25),
    ("1min", "1-minute", 0.4, 25),
]


def _resample(df: pd.DataFrame, rule: str, offset: str | None, min_bars: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    kw = {"label": "left", "closed": "left"}
    if offset:
        kw["offset"] = offset
    g = df.resample(rule, **kw)
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    if out.empty:
        return out
    counts = g["close"].count().reindex(out.index).fillna(0)
    # Drop partial buckets: an overnight gap bin must never look like a 4-hour range.
    return out[counts >= min_bars]


def _series_for(tf: str, ctx: dict) -> pd.DataFrame:
    if tf == "1d":
        return ctx.get("daily") if ctx.get("daily") is not None else pd.DataFrame()
    if tf == "4h":
        return _resample(ctx.get("df5"), "4h", None, 20)
    if tf == "60min":
        return _resample(ctx.get("df5"), "60min", "15min", 6)
    if tf == "15min":
        return _resample(ctx.get("df5"), "15min", None, 3)
    if tf == "5min":
        return ctx.get("df5") if ctx.get("df5") is not None else pd.DataFrame()
    if tf == "1min":
        return ctx.get("df1m") if ctx.get("df1m") is not None else pd.DataFrame()
    return pd.DataFrame()


def _read(df: pd.DataFrame, tf: str, label: str, weight: float, min_bars: int) -> dict:
    """Trend + momentum on one timeframe, scored -1..+1 the same way as the main engine."""
    row = {"tf": tf, "label": label, "weight": weight, "available": False, "score": 0.0,
           "direction": 0, "adx": None, "rsi": None, "atr": None, "text": ""}
    if df is None or df.empty or len(df) < min_bars:
        have = 0 if df is None or df.empty else len(df)
        row["text"] = f"Not enough {label.lower()} bars yet ({have}/{min_bars})."
        return row

    c = df["close"]
    last = float(c.iloc[-1])
    e20 = float(ema(c, 20).iloc[-1])
    e50 = float(ema(c, 50).iloc[-1]) if len(c) >= 50 else e20
    st = float(supertrend(df).iloc[-1])
    adx_v, pdi, mdi = (float(x.iloc[-1]) for x in adx(df))
    r = float(rsi(c).iloc[-1])
    slope, r2 = linreg_slope(c, min(20, len(c) - 1))
    a = float(atr(df).iloc[-1]) or 1.0

    trend = 0.0
    trend += 0.35 if e20 > e50 else -0.35
    trend += 0.25 if last > e20 else -0.25
    trend += 0.25 * (1.0 if st > 0 else -1.0)
    trend += 0.15 if pdi > mdi else -0.15
    trend *= min(1.0, max(0.3, adx_v / 30))  # a weak ADX shrinks the vote, it does not flip it

    momentum = 0.0
    momentum += 0.4 if r > 55 else -0.4 if r < 45 else 0.0
    momentum += 0.3 if slope > 0 else -0.3
    momentum += 0.3 * float(np.clip(slope / a * 4, -1, 1)) * r2

    score = float(np.clip(0.7 * trend + 0.3 * momentum, -1, 1))
    direction = 1 if score > 0.12 else -1 if score < -0.12 else 0

    strength = "trending" if adx_v >= 25 else "soft" if adx_v >= 18 else "choppy"
    row.update({
        "available": True, "score": round(score, 3), "direction": direction,
        "adx": round(adx_v, 1), "rsi": round(r, 1), "atr": round(a, 2),
        "text": (f"{'up' if direction > 0 else 'down' if direction < 0 else 'flat'} - price "
                 f"{'above' if last > e20 else 'below'} the 20 EMA, 20 EMA "
                 f"{'above' if e20 > e50 else 'below'} the 50 EMA, Supertrend "
                 f"{'green' if st > 0 else 'red'}, ADX {adx_v:.0f} ({strength}), RSI {r:.0f}."),
    })
    return row


def ladder(df5: pd.DataFrame, daily: pd.DataFrame, df1m: pd.DataFrame | None = None) -> dict:
    """Return the timeframe ladder, the confluence between them, and the two scenarios.

    Keys:
      rows       one row per timeframe, slowest first
      bias       weighted direction, -1..+1
      agreement  0..1, how much of the weight points the same way
      phase      aligned | pullback | conflict | unclear
      story      plain English, one paragraph
      primary    {"direction", "text", "hold_above"/"flip_below"} or None
      warning    what would make this read wrong
    """
    ctx = {"df5": df5, "daily": daily, "df1m": df1m}
    rows = []
    for tf, label, weight, min_bars in _ROWS:
        rows.append(_read(_series_for(tf, ctx), tf, label, weight, min_bars))

    counted = [r for r in rows if r["available"] and r["weight"] > 0]
    twap = None
    if df5 is not None and len(df5):
        # A true VWAP needs volume, and index spot volume is always zero on both feeds. The
        # session's average typical price is the honest substitute: same question, no fake volume.
        typical = (df5["high"] + df5["low"] + df5["close"]) / 3
        twap = round(float(typical.mean()), 2)
    if not counted:
        return {"rows": rows, "bias": 0.0, "agreement": 0.0, "phase": "unclear",
                "story": "Not enough price history on any timeframe to form a read yet.",
                "primary": None, "warning": None, "counted": 0, "twap": twap, "above_twap": None}

    wsum = sum(r["weight"] for r in counted)
    bias = sum(r["score"] * r["weight"] for r in counted) / wsum
    sign = 1 if bias > 0.12 else -1 if bias < -0.12 else 0
    agreement = (sum(r["weight"] for r in counted if r["direction"] == sign) / wsum) if sign else 0.0

    slow = [r for r in counted if r["tf"] in ("1d", "4h", "60min")]
    fast = [r for r in counted if r["tf"] in ("5min", "1min")]
    slow_s = (sum(r["score"] * r["weight"] for r in slow) / sum(r["weight"] for r in slow)) if slow else 0.0
    fast_s = (sum(r["score"] * r["weight"] for r in fast) / sum(r["weight"] for r in fast)) if fast else 0.0

    if sign == 0:
        phase = "unclear"
    elif slow and fast and np.sign(slow_s) != np.sign(fast_s) and abs(slow_s) > 0.12 and abs(fast_s) > 0.12:
        phase = "pullback"
    elif agreement >= 0.75:
        phase = "aligned"
    else:
        phase = "conflict"

    up = sign > 0
    a5 = float(atr(df5).iloc[-1]) if df5 is not None and len(df5) > 15 else 0.0
    price = float(df5["close"].iloc[-1]) if df5 is not None and len(df5) else None

    if phase == "aligned":
        story = (f"All speeds agree {'higher' if up else 'lower'}. When the daily, the hourly and the "
                 f"fast charts point the same way, the move usually has follow-through - this is the "
                 f"cleanest kind of setup there is.")
    elif phase == "pullback":
        story = (f"The big picture is {'up' if slow_s > 0 else 'down'}, but the fast charts are "
                 f"{'selling off' if fast_s < 0 else 'bouncing'}. That is a pullback inside a "
                 f"{'uptrend' if slow_s > 0 else 'downtrend'}, not a reversal - until the fast move "
                 f"starts breaking the big-picture levels.")
    elif phase == "conflict":
        story = ("The timeframes disagree with no clear leader. When the daily and the hourly point "
                 "opposite ways, whoever wins decides the day - and you find out after the money is spent.")
    else:
        story = ("No timeframe has a direction worth acting on. Flat market: buying options here pays "
                 "time decay for nothing.")

    primary = None
    warning = None
    if sign and price:
        hold = price - 1.2 * a5 if up else price + 1.2 * a5
        primary = {
            "direction": sign,
            "text": (f"Primary read: {'higher' if up else 'lower'}. While price stays "
                     f"{'above' if up else 'below'} {hold:.0f}, the fast charts should keep "
                     f"{'buying dips' if up else 'selling rallies'}."),
            "hold_above" if up else "flip_below": round(hold, 2),
        }
        warning = (f"If price closes {'below' if up else 'above'} {hold:.0f}, this read is wrong - "
                   f"the fast money has taken over and you should be out, not averaging.")
        if phase == "pullback":
            warning = (f"This is a pullback, so it can always become a reversal. "
                       f"{'Below' if up else 'Above'} {hold:.0f} it has, and the rule says stand down.")

    return {
        "rows": rows,
        "bias": round(float(bias), 3),
        "agreement": round(float(agreement), 2),
        "phase": phase,
        "story": story,
        "primary": primary,
        "warning": warning,
        "counted": len(counted),
        "weights": {r["tf"]: r["weight"] for r in rows},
        "twap": twap,
        "above_twap": None if (twap is None or price is None) else bool(price > twap),
    }
