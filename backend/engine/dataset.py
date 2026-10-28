"""Turn the strategy lab into a supervised dataset.

One row per trade the rule would actually take, carrying
  * the state observable at the entry bar (features), and
  * the outcome that rule actually got (win / points / pnl).

No lookahead: every feature is computed from bars strictly BEFORE the entry bar. The entry
fills at that bar's open, so anything from that bar onwards is off limits.

This is the training table for `decision.py`. It is deliberately the same execution model as
`lab.run` (same option pricing, slippage, charges, stop-before-target, 15:15 exit) so a model
fitted here is predicting the P&L the terminal would really have booked.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import lab, timeline
from .backtest import _vix_lookup
from .config import INSTRUMENTS
from .data import closed_bars, get_candles, long_history
from .indicators import atr, ema, linreg_slope

FEATURES = (
    "range_atr",     # opening-range width / ATR - how big a day is this
    "risk_atr",      # distance from entry to the stop / ATR - how much room the trade needs
    "pos_range",     # how far through the opening range, in the trade's direction
    "dist_res_atr",  # distance to the obvious barrier ahead (prev high for longs, prev low for shorts)
    "gap_atr",       # gap from the previous close, in the trade's direction
    "ema_align",     # 5m and 15m EMA20/50 agreement, in the trade's direction (+1 / 0 / -1)
    "slope_atr",     # 20-bar regression slope, in ATR units, in the trade's direction
    "minutes",       # minutes since 09:15 / 60 - time-of-day risk
    "atr_pct",       # ATR / price * 100 - volatility regime
    "vix",           # India VIX
    "is_expiry",     # expiry-day theta
)


def features(day, i0: int, ctx: dict, d: int, stop: float, entry: float) -> dict | None:
    """State at the entry bar. `day` is the session's 5m bars, `i0` the bar we fill at."""
    hist, start = ctx["hist"], ctx["day_start"]
    before = hist.iloc[max(0, start + i0 - 120):start + i0]  # strictly before the fill
    if len(before) < 20 or i0 < 6:
        return None
    a = float(atr(before, 14).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        return None
    first = day.iloc[:6]  # 09:15-09:45
    hi, lo = float(first.high.max()), float(first.low.min())
    width = hi - lo
    mid = (hi + lo) / 2
    at_bar = day.index[min(i0, len(day) - 1)]
    e20, e50 = ema(before.close, 20), ema(before.close, 50)
    up = 1 if e20.iloc[-1] > e50.iloc[-1] else -1
    # 15m agreement: resample the same pre-entry bars
    b15 = before.resample("15min").agg({"open": "first", "high": "max", "low": "min",
                                        "close": "last", "volume": "sum"}).dropna()
    up15 = 0
    if len(b15) >= 55:
        up15 = 1 if ema(b15.close, 20).iloc[-1] > ema(b15.close, 50).iloc[-1] else -1
    align = d * up + (d * up15 if up15 else 0)
    slope, _ = linreg_slope(before.close, 20)
    pdh, pdl = ctx.get("pdh"), ctx.get("pdl")
    barrier = (pdh - entry) if (d > 0 and pdh) else ((entry - pdl) if (d < 0 and pdl) else 0.0)
    pdc = ctx.get("pdc") or float(day.open.iloc[0])
    return {
        "range_atr": round(width / a, 4),
        "risk_atr": round(abs(entry - stop) / a, 4),
        "pos_range": round(d * (entry - mid) / width, 4) if width > 0 else 0.0,
        "dist_res_atr": round(barrier / a, 4),
        "gap_atr": round(d * (float(day.open.iloc[0]) - pdc) / a, 4),
        "ema_align": float(align),
        "slope_atr": round(d * (slope or 0.0) * 20 / a, 4),
        "minutes": round((at_bar.hour * 60 + at_bar.minute - 555) / 60, 4),
        "atr_pct": round(a / entry * 100, 4),
        "vix": round(float(ctx.get("vix") or 14.0), 4),
        "is_expiry": 1.0 if ctx.get("expiry") == at_bar.date() else 0.0,
    }


def build(key: str, strategy, label: str, **kw) -> pd.DataFrame:
    """Every trade `strategy` would take on the stored history, with its entry-time features."""
    df5 = closed_bars(long_history(key, "5m"), "5m")
    source = df5.attrs.get("source") or "unknown"
    daily, _ = get_candles(key, "1d")
    vix = _vix_lookup()
    inst = INSTRUMENTS[key]
    rows = []
    days = sorted(set(df5.index.date))
    for dday in days:
        mask = df5.index.date == dday
        day = df5[mask]
        start = int(np.argmax(mask))
        if start < 200 or len(day) < 30:
            continue
        prev = daily[daily.index.date < dday]
        if prev.empty:
            continue
        ctx = {"pdh": float(prev.high.iloc[-1]), "pdl": float(prev.low.iloc[-1]),
               "pdc": float(prev.close.iloc[-1]), "prev": prev, "daily": daily, "hist": df5,
               "day_start": start, "step": inst.strike_step,
               "expiry": timeline.weekly_expiry(key, dday), "vix": vix.get(dday, 14.0)}
        for t in lab._execute(key, day, strategy(day, ctx, **kw), ctx, feature_fn=features):
            if not t.get("features"):
                continue
            rows.append({"day": str(dday), "time": t["time"], "dir": t["dir"],
                         "reason": t["reason"], "points": t["points"], "pnl": t["pnl"],
                         "risk_rs": t["risk_rs"],
                         "r": round(t["pnl"] / t["risk_rs"], 4) if t.get("risk_rs") else 0.0,
                         "win": 1 if t["pnl"] > 0 else 0, **t["features"]})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["day", "time"]).reset_index(drop=True)
        df["label"] = label
    df.attrs["source"] = source
    return df


def matrix(df: pd.DataFrame, cols=FEATURES) -> tuple[np.ndarray, np.ndarray]:
    """(X, y) with a leading bias column."""
    X = np.column_stack([np.ones(len(df))] + [df[f].to_numpy(dtype=float) for f in cols])
    return X, df["win"].to_numpy(dtype=float)
