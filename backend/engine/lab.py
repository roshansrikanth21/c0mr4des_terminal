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
from .data import closed_bars, get_candles, long_history
from .indicators import atr, ema
from .options import round_trip_cost, years_to_expiry
from .signal import evaluate

T930, T945, T1000, T1015, T1500, T1515 = time(9, 30), time(9, 45), time(10, 0), time(10, 15), time(15, 0), time(15, 15)


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


def first_hour_breakout(day, ctx, rr=2.0, max_trades=1, filter_fn=None, range_minutes=60):
    """The live First-Hour rule, exactly: 09:15-10:15 range, the first 5m CLOSE outside it after
    10:15 that is ALSO on the right side of yesterday's close. Fill at the next bar's open, stop at
    the other side of the range, target rr x risk. `orb.evaluate` is the same rule in live form.

    `range_minutes=30` moves the range to 09:15-09:45 and the trigger to 09:45 - the same rule with
    only the window changed, which is the only honest way to compare the two (registry row 15).
    """
    end = T945 if range_minutes == 30 else T1015
    need = 6 if range_minutes == 30 else 12
    first = day[day.index.time < end]
    if len(first) < need:
        return []
    hi, lo = float(first.high.max()), float(first.low.min())
    pdc = ctx.get("pdc")
    for ts, bar in day[day.index.time >= end].iterrows():
        c = float(bar.close)
        d = 1 if c > hi else -1 if c < lo else 0
        if d == 0 or (pdc is not None and (c - pdc) * d <= 0):
            continue
        i = int(day.index.get_loc(ts)) + 1  # we can only fill after the bar that closed outside
        if i >= len(day):
            return []
        if filter_fn and not filter_fn(d, day, i, ctx):
            continue
        fill = float(day.open.iloc[i])
        stop = lo if d > 0 else hi
        if (fill - stop) * d <= 0:  # gapped through the stop: not a trade
            return []
        return [{"i": i, "dir": d, "stop": stop, "target": fill + d * rr * abs(fill - stop)}]
    return []


def mtf_align(day, i, ctx, d) -> tuple[bool, bool]:
    """(5m agrees with the trade, 15m agrees with the trade) using only bars BEFORE the fill.

    The decision engine's win head put the strongest single weight on this feature, and the sign
    was negative - aligned trends went with a LOWER probability of a green trade. That is a
    hypothesis about breakouts (by the time 5m and 15m agree, the move has already happened), and
    a lab run is the only way to see whether it survives as money.
    """
    hist, start = ctx["hist"], ctx["day_start"]
    before = hist.iloc[max(0, start + i - 240):start + i]  # 240 5m bars ~= 60 15m bars
    if len(before) < 55:
        return False, False
    up5 = 1 if ema(before.close, 20).iloc[-1] > ema(before.close, 50).iloc[-1] else -1
    b15 = before.resample("15min").agg({"open": "first", "high": "max", "low": "min",
                                        "close": "last", "volume": "sum"}).dropna()
    if len(b15) < 55:
        return d * up5 > 0, False
    up15 = 1 if ema(b15.close, 20).iloc[-1] > ema(b15.close, 50).iloc[-1] else -1
    return d * up5 > 0, d * up15 > 0


def not_aligned(d, day, i, ctx) -> bool:
    """Skip the trade when BOTH timeframes already agree with it (the model's negative sign)."""
    a5, a15 = mtf_align(day, i, ctx, d)
    return not (a5 and a15)


def only_aligned(d, day, i, ctx) -> bool:
    """The conventional rule: take the trade only when both timeframes agree with it."""
    a5, a15 = mtf_align(day, i, ctx, d)
    return a5 and a15


def skip_5m_aligned(d, day, i, ctx) -> bool:
    """Skip when the 5m alone agrees - isolates the faster timeframe."""
    a5, _ = mtf_align(day, i, ctx, d)
    return not a5


def orb30_breakout(day, ctx, rr=2.0, filter_fn=None, max_trades=1):
    """30-min opening range breakout. Delegates so the two windows cannot drift apart.

    This used to be a separate implementation without the yesterday's-close side filter, which
    made any First-Hour vs 30-min comparison silently unfair. Same rule, shorter window.
    """
    return first_hour_breakout(day, ctx, rr=rr, filter_fn=filter_fn, range_minutes=30)


def orb_two_candles(day, ctx, rr=2.0, target_points=None, max_trades=1,
                    min_range=None, max_range=None, filter_fn=None):
    """The toddler rule: range = the first two 15-minute candles (09:15-09:45).

    Wait for a 15-minute CLOSE outside the range (a wick through it is not a trade), enter on
    the next bar, stop at the opposite end of the range, and take `rr` times the risk.

    `target_points` exists only to replay the flat-point variant, which loses: with a fixed
    target the break-even win rate moves with the day's range, so the same rule is easy on a
    quiet morning and impossible on a wide one. Keep it at 2R.
    """
    first = day[day.index.time < T945]
    if len(first) < 6:
        return []
    hi, lo = float(first.high.max()), float(first.low.min())
    rng = hi - lo
    if min_range is not None and rng < min_range:
        return []
    if max_range is not None and rng > max_range:
        return []

    b15 = day.resample("15min").agg({"open": "first", "high": "max",
                                     "low": "min", "close": "last"}).dropna()
    for ts, bar in b15[b15.index.time >= T945].iterrows():
        c = float(bar.close)
        d = 1 if c > hi else -1 if c < lo else 0
        if d == 0:
            continue
        if filter_fn and not filter_fn(d, day, ctx):
            continue
        after = day.index[day.index >= ts + pd.Timedelta(minutes=15)]
        if not len(after):
            break
        i = int(day.index.get_loc(after[0]))
        if i >= len(day) - 1:
            break
        stop = lo if d > 0 else hi
        tgt = (c + d * target_points if target_points
               else c + d * rr * abs(c - stop) if rr else None)
        return [{"i": i, "dir": d, "stop": stop, "target": tgt, "range": round(rng, 2)}]
    return []


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


def tjr_sweep(day, ctx, rr=2.0, max_trades=2, wait=6):
    """TJR / ICT-style model adapted to NIFTY/SENSEX:
    1. Liquidity pools: previous day high/low and the 09:15-09:30 opening range high/low.
    2. Sweep: a candle trades through a pool and CLOSES back inside (stop hunt).
    3. Within `wait` bars, a displacement candle (body > 50% of range, range >= 1 ATR) closes beyond the
       lowest low (bearish) / highest high (bullish) printed since the sweep = structure shift.
    4. The displacement leaves a fair value gap; enter with a limit order when price retraces into it
       (within `wait` bars). Stop beyond the sweep extreme, target `rr` x risk. Entries 09:30-14:30.
    """
    a = atr(ctx["hist"].iloc[max(0, ctx["day_start"] - 200):ctx["day_start"] + len(day)], 14)
    a = a.reindex(day.index).ffill()
    orr = day[day.index.time < T930]
    pools_hi = [ctx["pdh"]] + ([float(orr.high.max())] if len(orr) >= 3 else [])
    pools_lo = [ctx["pdl"]] + ([float(orr.low.min())] if len(orr) >= 3 else [])
    o, h, l, c = (day[k].to_numpy() for k in ("open", "high", "low", "close"))
    out, used = [], set()
    i = 3
    while i < len(day) - 2 and len(out) < max_trades:
        t = day.index[i].time()
        if not (T930 <= t < time(14, 30)):
            i += 1
            continue
        sweep = None
        for p in pools_hi:
            if ("H", p) not in used and h[i] > p and c[i] < p:
                sweep = (-1, h[i], p)
        for p in pools_lo:
            if ("L", p) not in used and l[i] < p and c[i] > p:
                sweep = (1, l[i], p)
        if not sweep:
            i += 1
            continue
        d, extreme, pool = sweep
        used.add(("H" if d < 0 else "L", pool))
        found = False
        for j in range(i + 1, min(i + 1 + wait, len(day) - 1)):
            rng = h[j] - l[j]
            body = abs(c[j] - o[j])
            if rng <= 0 or np.isnan(a.iloc[j]) or body < 0.5 * rng or rng < a.iloc[j]:
                continue
            if d < 0 and c[j] < o[j] and c[j] < min(l[i:j]):
                fvg_lo, fvg_hi = h[j + 1] if j + 1 < len(day) else None, l[j - 1]
            elif d > 0 and c[j] > o[j] and c[j] > max(h[i:j]):
                fvg_lo, fvg_hi = h[j - 1], l[j + 1] if j + 1 < len(day) else None
            else:
                continue
            # 3-candle gap between candle j-1 and j+1
            if d < 0:
                gap_top, gap_bot = l[j - 1], (h[j + 1] if j + 1 < len(day) else None)
                if gap_bot is None or gap_bot >= gap_top:
                    break
                for k in range(j + 2, min(j + 2 + wait, len(day))):
                    if h[k] >= gap_bot:
                        risk = extreme - gap_bot
                        if risk > 0:
                            out.append({"i": k, "fill": gap_bot, "dir": -1, "stop": extreme + 0.5, "target": gap_bot - rr * risk})
                            found = True
                        break
            else:
                gap_bot, gap_top = h[j - 1], (l[j + 1] if j + 1 < len(day) else None)
                if gap_top is None or gap_top <= gap_bot:
                    break
                for k in range(j + 2, min(j + 2 + wait, len(day))):
                    if l[k] <= gap_top:
                        risk = gap_top - extreme
                        if risk > 0:
                            out.append({"i": k, "fill": gap_top, "dir": 1, "stop": extreme - 0.5, "target": gap_top + rr * risk})
                            found = True
                        break
            break
        i = (out[-1]["i"] + 1) if found else i + 1
    return out


def five_ema(day, ctx, rr=3.0, max_trades=3, sell_only=False):
    """Power of Stocks (Subasish Pani) 5 EMA method, as publicly taught.
    SELL (5m): alert candle entirely ABOVE the 5 EMA (low > EMA). A later candle breaking the alert
    candle's low triggers the sell; if another candle stays fully above the EMA first, it becomes the new alert.
    Stop = alert high, target = rr x risk.
    BUY (15m): alert candle entirely BELOW the 5 EMA (high < EMA); break of its high = buy; stop = alert low.
    """
    end = ctx["day_start"] + len(day)
    hist = ctx["hist"].iloc[max(0, end - 600):end]
    ema5 = hist["close"].ewm(span=5, adjust=False).mean().reindex(day.index)
    out, busy = [], -1
    alert = None
    for i in range(len(day) - 1):
        t = day.index[i].time()
        if alert and i > alert["i"] and day.low.iloc[i] < alert["low"] and T930 <= t < T1500 and i > busy:
            risk = alert["high"] - alert["low"]
            fill = min(alert["low"], float(day.open.iloc[i]))
            out.append({"i": i, "fill": fill, "dir": -1, "stop": alert["high"], "target": fill - rr * risk})
            busy = i + 3
            alert = None
            if len(out) >= max_trades:
                return out
            continue
        if day.low.iloc[i] > ema5.iloc[i]:
            alert = {"i": i, "high": float(day.high.iloc[i]), "low": float(day.low.iloc[i])}
    if sell_only:
        return out
    # BUY side on 15-minute candles
    h15 = hist.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    e15 = h15["close"].ewm(span=5, adjust=False).mean()
    d15 = h15[h15.index.date == day.index[0].date()]
    balert = None
    for ts, b in d15.iterrows():
        if balert is not None:
            # trigger on any 5m bar after the alert 15m candle closes that breaks its high
            later = day[(day.index >= ts) & (day.index < ts + pd.Timedelta(minutes=15))]
            hit = later[later.high > balert["high"]]
            if len(hit) and T930 <= hit.index[0].time() < T1500 and len(out) < max_trades:
                i = day.index.get_loc(hit.index[0])
                risk = balert["high"] - balert["low"]
                fill = max(balert["high"], float(day.open.iloc[i]))
                out.append({"i": i, "fill": fill, "dir": 1, "stop": balert["low"], "target": fill + rr * risk})
                balert = None
                continue
        if b.high < e15.loc[ts]:
            balert = {"high": float(b.high), "low": float(b.low)}
    return out


def first30_plus_engine(day, ctx, **kw):
    """Engine trades only in the direction the first 30 minutes chose."""
    f = first30_direction(day, ctx)
    if not f:
        return []
    return [e for e in engine(day, ctx, **kw) if e["dir"] == f[0]["dir"] and day.index[min(e["i"], len(day) - 1)].time() >= T945]


# ------------------------------------------------------------------ executor
def _execute(key, day, entries, ctx, feature_fn=None):
    inst = INSTRUMENTS[key]
    trades = []
    busy_until = -1
    for e in sorted(entries, key=lambda x: x["i"]):
        i0 = e["i"]
        if i0 <= busy_until or i0 >= len(day):
            continue
        d = e["dir"]
        entry = float(e.get("fill", day.open.iloc[i0]))  # limit fills (FVG retrace) use their price
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
                       "pnl": round((prem_out - prem_in) * inst.lot_size - cost, 2),
                       "risk_rs": round(abs(entry - stop) * inst.lot_size, 2),
                       "features": feature_fn(day, i0, ctx, d, stop, entry) if feature_fn else None})
    return trades


def run(key: str, strategy, label: str, **kw) -> dict:
    # The lab is research, so it wants the LONGEST history, not the freshest frame: on the VM that
    # is Angel's 100-day 5m window (69 sessions) instead of the 25-day live one (13 sessions).
    df5 = closed_bars(long_history(key, "5m"), "5m")
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
