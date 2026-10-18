"""Strategy lab: test simple intraday rules on real NIFTY/SENSEX 5m data with the SAME execution,
option pricing (Black-Scholes, real daily India VIX, real time to expiry, theta included),
slippage and charges as the main backtest - so results are directly comparable.

Each strategy is a function(day_bars, ctx) -> list of entries
    {"i": bar index within the day to ENTER AT ITS OPEN, "dir": +1/-1, "stop": px, "target": px or None}
Entries fill at that bar's open; stop checked before target on the same bar; exit by 15:15.
"""
from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

from . import timeline
from .backtest import SLIPPAGE, _option_price, _vix_lookup
from .config import INSTRUMENTS
from .data import closed_bars, get_candles
from .indicators import atr, ema
from .options import round_trip_cost, years_to_expiry
from .signal import evaluate

T930, T945, T1000, T1500, T1515 = time(9, 30), time(9, 45), time(10, 0), time(15, 0), time(15, 15)


# ------------------------------------------------------------------ strategies
def first30_direction(day, ctx, stop_mode="range", rr=None):
    """User's rule: 09:15-09:45 went up -> BUY, went down -> SELL. Enter 09:45, hold to stop/target/15:15."""
    first = day[day.index.time < T945]
    if len(first) < 6:
        return []
    o, c, hi, lo = first.open.iloc[0], first.close.iloc[-1], first.high.max(), first.low.min()
    d = 1 if c > o else -1 if c < o else 0
    if d == 0:
        return []
    i = len(first)
    stop = lo if d > 0 else hi
    if stop_mode == "mid":
        stop = (hi + lo) / 2
    entry_ref = c
    tgt = entry_ref + d * rr * abs(entry_ref - stop) if rr else None
    return [{"i": i, "dir": d, "stop": stop, "target": tgt}]


def orb30_breakout(day, ctx, rr=2.0, filter_fn=None, max_trades=1):
    """30-min opening range breakout: first CLOSE beyond the range after 09:45, stop at the other side."""
    first = day[day.index.time < T945]
    if len(first) < 6:
        return []
    hi, lo = first.high.max(), first.low.min()
    out = []
    for i in range(len(first), len(day) - 1):
        if day.index[i].time() >= T1500 or len(out) >= max_trades:
            break
        c = day.close.iloc[i]
        d = 1 if c > hi else -1 if c < lo else 0
        if d == 0 or (filter_fn and not filter_fn(d, day, i, ctx)):
            continue
        stop = lo if d > 0 else hi
        risk = abs(c - stop)
        out.append({"i": i + 1, "dir": d, "stop": stop, "target": c + d * rr * risk if rr else None})
        break
    return out


def gap_follow(day, ctx, rr=2.0):
    """Gap beyond previous day's range and the first 15 min holds the gap -> trade in the gap direction."""
    pdh, pdl = ctx.get("pdh"), ctx.get("pdl")
    if pdh is None:
        return []
    o = day.open.iloc[0]
    first = day[day.index.time < T930]
    if len(first) < 3:
        return []
    if o > pdh and first.low.min() > pdh * 0.999 and first.close.iloc[-1] > o:
        d, stop = 1, first.low.min()
    elif o < pdl and first.high.max() < pdl * 1.001 and first.close.iloc[-1] < o:
        d, stop = -1, first.high.max()
    else:
        return []
    c = first.close.iloc[-1]
    return [{"i": len(first), "dir": d, "stop": stop, "target": c + d * rr * abs(c - stop)}]


def engine(day, ctx, buy_threshold=None, sell_threshold=None, max_trades=3, sell_only=False):
    """The live engine, optionally with asymmetric conviction (buy only when very sure)."""
    out, hist_all, start = [], ctx["hist"], ctx["day_start"]
    for i in range(len(day) - 1):
        t = day.index[i].time()
        if not (T930 <= t < T1500) or len(out) >= max_trades:
            continue
        if out and i < out[-1]["exit_hint"]:
            continue
        hist = hist_all.iloc[max(0, start + i - 400):start + i + 1]
        sess = {"can_enter": True, "is_expiry_day": ctx["expiry"] == day.index[i].date(),
                "phase": "midday_chop" if time(11, 30) <= t < time(13, 30) else "trend"}
        r = evaluate(hist, ctx["daily"], ctx["step"], now=day.index[i].to_pydatetime(), session=sess)
        d = r["plan"]["direction"]
        if r["verdict"] == "NO TRADE":
            # asymmetric override: allow a strong-enough SELL even if the base threshold gate fired
            only_threshold_gate = all("not aligned" in g for g in r["gates"])
            if not (sell_threshold is not None and d < 0 and only_threshold_gate and -r["score"] >= sell_threshold):
                continue
        if d > 0 and (sell_only or (buy_threshold is not None and r["score"] < buy_threshold)):
            continue
        if d < 0 and sell_threshold is not None and -r["score"] < sell_threshold:
            continue
        out.append({"i": i + 1, "dir": d, "stop": r["plan"]["stop"], "target": r["plan"]["target"], "exit_hint": i + 6})
    return out


def first30_plus_engine(day, ctx, **kw):
    """Engine trades only in the direction the first 30 minutes chose."""
    f = first30_direction(day, ctx)
    if not f:
        return []
    return [e for e in engine(day, ctx, **kw) if e["dir"] == f[0]["dir"] and day.index[min(e["i"], len(day) - 1)].time() >= T945]


# ------------------------------------------------------------------ executor
def _execute(key, day, entries, ctx):
    inst = INSTRUMENTS[key]
    trades = []
    busy_until = -1
    for e in sorted(entries, key=lambda x: x["i"]):
        i0 = e["i"]
        if i0 <= busy_until or i0 >= len(day):
            continue
        d = e["dir"]
        entry = float(day.open.iloc[i0])
        stop = e["stop"]
        if (entry - stop) * d <= 0:  # gapped through the stop already
            continue
        tgt = e.get("target")
        now = day.index[i0].to_pydatetime()
        kind = "CE" if d > 0 else "PE"
        atm = round(entry / inst.strike_step) * inst.strike_step
        strike = atm - d * (1 if years_to_expiry(ctx["expiry"], now) * 365 < 2 else 0) * inst.strike_step
        prem_in = _option_price(key, entry, strike, kind, ctx["expiry"], now, ctx["vix"]) * (1 + SLIPPAGE)
        exit_px, reason, j = None, "time", i0
        for j in range(i0, len(day)):
            b = day.iloc[j]
            if (b.low <= stop) if d > 0 else (b.high >= stop):
                exit_px, reason = stop, "stop"
                break
            if tgt is not None and ((b.high >= tgt) if d > 0 else (b.low <= tgt)):
                exit_px, reason = tgt, "target"
                break
            if day.index[j].time() >= T1515:
                exit_px = float(b.close)
                break
        if exit_px is None:
            exit_px = float(day.close.iloc[-1])
        busy_until = j
        at = day.index[j].to_pydatetime() + pd.Timedelta(minutes=5)
        prem_out = _option_price(key, exit_px, strike, kind, ctx["expiry"], at, ctx["vix"]) * (1 - SLIPPAGE)
        cost = round_trip_cost((prem_in + prem_out) / 2, inst.lot_size)
        trades.append({"time": day.index[i0].isoformat(), "dir": d, "entry": round(entry, 2), "exit": round(exit_px, 2),
                       "reason": reason, "points": round((exit_px - entry) * d, 2),
                       "pnl": round((prem_out - prem_in) * inst.lot_size - cost, 2)})
    return trades


def run(key: str, strategy, label: str, **kw) -> dict:
    df5, _ = get_candles(key, "5m")
    df5 = closed_bars(df5, "5m")
    daily, _ = get_candles(key, "1d")
    vix = _vix_lookup()
    inst = INSTRUMENTS[key]
    trades = []
    days = sorted(set(df5.index.date))
    for n, dday in enumerate(days):
        mask = df5.index.date == dday
        day = df5[mask]
        start = int(np.argmax(mask))
        if start < 200 or len(day) < 30:
            continue
        prev = daily[daily.index.date < dday]
        if prev.empty:
            continue
        ctx = {"pdh": float(prev.high.iloc[-1]), "pdl": float(prev.low.iloc[-1]), "pdc": float(prev.close.iloc[-1]),
               "prev": prev, "daily": daily, "hist": df5, "day_start": start, "step": inst.strike_step,
               "expiry": timeline.weekly_expiry(key, dday), "vix": vix.get(dday, 14.0)}
        entries = strategy(day, ctx, **kw)
        for t in _execute(key, day, entries, ctx):
            t["day"] = str(dday)
            trades.append(t)
    return stats(pd.DataFrame(trades), label, days)


def stats(df: pd.DataFrame, label: str, days) -> dict:
    if df.empty:
        return {"strategy": label, "trades": 0}
    mid = str(days[(len(days) + 3) // 2])  # split the tested days into two halves
    w, l = df[df.pnl > 0], df[df.pnl <= 0]
    h1, h2 = df[df.day < mid], df[df.day >= mid]
    pf = (w.pnl.sum() / -l.pnl.sum()) if l.pnl.sum() < 0 else float("inf")
    eq = df.pnl.cumsum()
    return {
        "strategy": label, "trades": len(df), "win_rate": round(len(w) / len(df) * 100, 1),
        "winners": len(w), "profit": round(w.pnl.sum()), "losers": len(l), "loss": round(l.pnl.sum()),
        "net": round(df.pnl.sum()), "avg_win": round(w.pnl.mean()) if len(w) else 0,
        "avg_loss": round(l.pnl.mean()) if len(l) else 0, "pf": round(pf, 2),
        "max_dd": round(float((eq - eq.cummax()).min())),
        "buys": int((df.dir > 0).sum()), "buy_net": round(df[df.dir > 0].pnl.sum()),
        "sells": int((df.dir < 0).sum()), "sell_net": round(df[df.dir < 0].pnl.sum()),
        "half1_net": round(h1.pnl.sum()), "half2_net": round(h2.pnl.sum()),
        "half1_wr": round((h1.pnl > 0).mean() * 100, 1) if len(h1) else None,
        "half2_wr": round((h2.pnl > 0).mean() * 100, 1) if len(h2) else None,
    }
