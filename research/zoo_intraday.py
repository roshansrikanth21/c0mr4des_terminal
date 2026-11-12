"""Strategy zoo, part 1: 28 intraday NIFTY signals traded by BUYING the at-the-money option, and 11 option-SELLING
structures. Every entry and exit is priced from the real 5-minute option prints (Black-Scholes on the bar's real
spot and implied volatility only when a held strike has no print). One lot of 65, full charges, 0.5% slippage a side.

    python research/zoo_intraday.py     ->  data/zoo_intraday.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.engine.options import bs, round_trip_cost  # noqa: E402
from research.zoo_data import ROOT, load  # noqa: E402

LOT, SLIP, STEP = 65, 0.005, 50
NO_ENTRY_AFTER, EXIT_AT = 870, 910           # no new trade after 14:30; flat at the 15:10 bar's close (15:15)


# ------------------------------------------------------------------ data and indicators
class Day:
    pass


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def prepare():
    raw = load()
    dates = sorted(raw)
    frames = []
    for d in dates:
        v = raw[d]
        frames.append(pd.DataFrame({"d": d, "t": v["t"], "o": v["o"], "h": v["h"], "l": v["l"], "c": v["c"]}))
    f = pd.concat(frames, ignore_index=True)
    c, h, l = f.c, f.h, f.l
    for n in (5, 9, 20, 21, 50):
        f[f"ema{n}"] = ema(c, n)
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    f["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    f["macd"] = ema(c, 12) - ema(c, 26)
    f["macds"] = ema(f.macd, 9)
    f["bbm"] = c.rolling(20).mean()
    sd = c.rolling(20).std()
    f["bbu"], f["bbl"] = f.bbm + 2 * sd, f.bbm - 2 * sd
    bw = (f.bbu - f.bbl) / f.bbm
    f["squeeze"] = bw <= bw.rolling(100).quantile(0.2)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 10, adjust=False).mean()
    # Supertrend(10, 3)
    mid = (h + l) / 2
    ub, lb = (mid + 3 * atr).to_numpy(), (mid - 3 * atr).to_numpy()
    cl = c.to_numpy()
    st_dir = np.ones(len(f), int)
    st_line = np.zeros(len(f))
    fu, fl = ub.copy(), lb.copy()
    for i in range(1, len(f)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or cl[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or cl[i - 1] < fl[i - 1]) else fl[i - 1]
        st_dir[i] = 1 if cl[i] > fu[i - 1] else -1 if cl[i] < fl[i - 1] else st_dir[i - 1]
        st_line[i] = fl[i] if st_dir[i] > 0 else fu[i]
    f["st_dir"], f["st_line"] = st_dir, st_line
    f["dhi20"], f["dlo20"] = h.rolling(20).max().shift(), l.rolling(20).min().shift()
    f["dhi10"], f["dlo10"] = h.rolling(10).max().shift(), l.rolling(10).min().shift()
    ha_c = (f.o + h + l + c) / 4
    ha_o = np.zeros(len(f))
    ha_o[0] = f.o.iloc[0]
    hc = ha_c.to_numpy()
    for i in range(1, len(f)):
        ha_o[i] = (ha_o[i - 1] + hc[i - 1]) / 2
    f["ha_o"], f["ha_c"] = ha_o, ha_c
    f["ha_l"] = np.minimum(l, np.minimum(ha_o, ha_c))
    f["ha_h"] = np.maximum(h, np.maximum(ha_o, ha_c))

    days, prev, ranges = [], None, []
    for d, g in f.groupby("d", sort=True):
        x = Day()
        x.date, x.raw = d, raw[d]
        for col in g.columns:
            if col != "d":
                setattr(x, col, g[col].to_numpy())
        x.n = len(g)
        x.tw = np.cumsum((x.h + x.l + x.c) / 3) / np.arange(1, x.n + 1)
        x.end = int(np.searchsorted(x.t, EXIT_AT))
        x.end = min(x.end, x.n - 1)
        x.expiry = raw[d]["expiry"]
        x.is_expiry = x.expiry == d
        x.prev = prev
        if prev is not None:
            x.pdh, x.pdl, x.pdc = prev.h.max(), prev.l.min(), prev.c[-1]
            x.nr7 = len(ranges) >= 7 and ranges[-1] == min(ranges[-7:])
        ranges.append(x.h.max() - x.l.min())
        days.append(x)
        prev = x
    return days


def at(day, minute):
    """Index of the first bar labelled at/after `minute` (bars are labelled by their start)."""
    return int(np.searchsorted(day.t, minute))


# ------------------------------------------------------------------ pricing and execution
def t_years(day, j):
    exp = datetime.combine(day.expiry, time(15, 30))
    now = datetime.combine(day.date, time(int(day.t[j]) // 60, int(day.t[j]) % 60))
    return max((exp - now).total_seconds() + 300, 60) / (365 * 24 * 3600)


def price(day, kind, strike, j):
    """Real print of that strike at bar j's close; modelled only if the strike has no print. -> (price, is_real)"""
    p = day.raw[kind][j].get(float(strike))
    if p:
        return p, True
    iv = day.raw["iv"][j]
    iv = (iv if iv == iv and iv > 0 else 15.0) / 100
    return max(0.05, bs(float(day.c[j]), float(strike), t_years(day, j), iv, kind.upper())["price"]), False


def leg_pnl(side, p_in, p_out):
    """side +1 = bought, -1 = sold. Charges and slippage on both ends."""
    return side * (p_out - p_in) * LOT - round_trip_cost((p_in + p_out) / 2, LOT) - SLIP * (p_in + p_out) * LOT


def run_long(day, sig):
    """sig = (bar i, direction, index stop, index target or None, forced exit bar or None)."""
    i, d, stop, target, exit_i = sig
    if i >= day.end or day.t[i] >= NO_ENTRY_AFTER or (day.c[i] - stop) * d <= 0:
        return None
    kind = "ce" if d > 0 else "pe"
    k0 = day.raw["atm"][i]
    if k0 != k0:
        return None
    p_in = day.raw[kind][i].get(float(k0))
    if not p_in or p_in < 1:
        return None
    j, why = day.end, "time"
    for b in range(i + 1, day.end + 1):
        if (day.l[b] <= stop) if d > 0 else (day.h[b] >= stop):
            j, why = b, "stop"
            break
        if target is not None and ((day.h[b] >= target) if d > 0 else (day.l[b] <= target)):
            j, why = b, "target"
            break
        if exit_i is not None and b >= exit_i:
            j, why = b, "signal"
            break
    p_out, real = price(day, kind, k0, j)
    return {"date": str(day.date), "pnl": round(leg_pnl(1, p_in, p_out), 2), "why": why, "real": real,
            "outlay": round(p_in * LOT)}


def run_short(day, i, legs, leg_sl=None, combined_sl=None, index_stop=None):
    """legs = [(kind, strike offset in steps from ATM, side)]. Short legs can carry a per-leg stop (premium up by
    leg_sl) or a combined stop (all shorts together up by combined_sl); index_stop = (direction, level)."""
    if i >= day.end:
        return None
    k0 = day.raw["atm"][i]
    if k0 != k0:
        return None
    book = []
    for kind, off, side in legs:
        strike = k0 + off * STEP
        p, real = price(day, kind, strike, i)
        if side < 0 and (not real or p < 1):
            return None                      # never sell a contract we have no real entry price for
        book.append({"kind": kind, "k": strike, "side": side, "in": p, "out": None})
    credit = sum(x["in"] for x in book if x["side"] < 0)
    reals = []
    j = day.end
    for b in range(i + 1, day.end + 1):
        stop_all = False
        if index_stop is not None:
            d, lvl = index_stop
            stop_all = (day.l[b] <= lvl) if d > 0 else (day.h[b] >= lvl)
        shorts_now = 0.0
        for x in book:
            if x["out"] is not None or x["side"] > 0:
                continue
            p, real = price(day, x["kind"], x["k"], b)
            shorts_now += p
            if leg_sl is not None and p >= x["in"] * (1 + leg_sl):
                x["out"] = p
                reals.append(real)
        open_shorts = [x for x in book if x["side"] < 0 and x["out"] is None]
        if combined_sl is not None and open_shorts and len(open_shorts) == sum(1 for x in book if x["side"] < 0) \
                and shorts_now >= credit * (1 + combined_sl):
            stop_all = True
        if stop_all or not open_shorts:
            j = b
            break
    pnl = 0.0
    for x in book:
        if x["out"] is None:
            x["out"], real = price(day, x["kind"], x["k"], j)
            reals.append(real)
        pnl += leg_pnl(x["side"], x["in"], x["out"])
    return {"date": str(day.date), "pnl": round(pnl, 2), "why": "", "real": all(reals), "outlay": round(credit * LOT)}


# ------------------------------------------------------------------ helpers for signals
def orb(day, minutes_, rr=2.0, prev_filter=False):
    n = at(day, 555 + minutes_)
    if n < 2:
        return None
    hi, lo = day.h[:n].max(), day.l[:n].min()
    for i in range(n, day.n):
        if day.t[i] >= NO_ENTRY_AFTER:
            return None
        c = day.c[i]
        d = 1 if c > hi else -1 if c < lo else 0
        if not d or (prev_filter and (c - day.pdc) * d <= 0):
            continue
        stop = lo if d > 0 else hi
        return i, d, stop, (c + d * rr * abs(c - stop)) if rr else None, None
    return None


def first_cross(a, b, start, stop_i, d):
    """First bar >= start where series a crosses series b in direction d."""
    for i in range(max(start, 1), stop_i):
        if d > 0 and a[i - 1] <= b[i - 1] and a[i] > b[i]:
            return i
        if d < 0 and a[i - 1] >= b[i - 1] and a[i] < b[i]:
            return i
    return None


def scan(day, start_min, fn):
    """First bar from start_min (before the no-entry cut-off) where fn(i) returns a signal."""
    for i in range(max(at(day, start_min), 2), day.n):
        if day.t[i] >= NO_ENTRY_AFTER:
            return None
        s = fn(i)
        if s:
            return s
    return None


def pct_stop(day, i, d, pct):
    return day.c[i] * (1 - d * pct / 100)


# ------------------------------------------------------------------ the 28 option-buying strategies
def a01(day): return orb(day, 15)
def a02(day): return orb(day, 30)
def a03(day): return orb(day, 60, prev_filter=True)
def a04(day): return orb(day, 30, rr=None)


def a05(day):
    i = at(day, 580)
    d = int(np.sign(day.c[i] - day.o[0]))
    return (i, d, (day.h[:i + 1].max() + day.l[:i + 1].min()) / 2, None, None) if d else None


def a06(day):
    d = int(np.sign(day.c[0] - day.o[0]))
    return (0, d, day.l[0] if d > 0 else day.h[0], None, None) if d else None


def a07(day):
    gap = (day.o[0] - day.pdc) / day.pdc * 100
    d = int(np.sign(gap))
    if abs(gap) < 0.3 or (day.c[2] - day.o[0]) * d <= 0:
        return None
    stop = day.l[:3].min() if d > 0 else day.h[:3].max()
    return 2, d, stop, day.c[2] + d * 2 * abs(day.c[2] - stop), None


def a08(day):
    gap = (day.o[0] - day.pdc) / day.pdc * 100
    g = int(np.sign(gap))
    if abs(gap) < 0.4 or (day.c[2] - day.o[0]) * g >= 0 or (day.pdc - day.c[2]) * -g <= 0:
        return None
    return 2, -g, day.h[:3].max() if g > 0 else day.l[:3].min(), day.pdc, None


def a09(day):
    def f(i):
        c = day.c[i]
        if c > day.pdh and day.c[i - 1] <= day.pdh and day.o[0] < day.pdh:
            return i, 1, pct_stop(day, i, 1, 0.25), c * 1.005, None
        if c < day.pdl and day.c[i - 1] >= day.pdl and day.o[0] > day.pdl:
            return i, -1, pct_stop(day, i, -1, 0.25), c * 0.995, None
    return scan(day, 570, f)


def a10(day):
    def f(i):
        if day.h[i] > day.pdh > day.c[i]:
            return i, -1, day.h[i], day.c[i] - 2 * (day.h[i] - day.c[i]), None
        if day.l[i] < day.pdl < day.c[i]:
            return i, 1, day.l[i], day.c[i] + 2 * (day.c[i] - day.l[i]), None
    return scan(day, 570, f)


def cpr(day):
    p = (day.pdh + day.pdl + day.pdc) / 3
    bc = (day.pdh + day.pdl) / 2
    tc = 2 * p - bc
    return p, max(tc, bc), min(tc, bc)


def a11(day):
    p, top, bot = cpr(day)

    def f(i):
        c = day.c[i]
        if c > top and day.c[i - 1] <= top and day.o[0] < top:
            return i, 1, min(bot, c * 0.9975), c + 2 * (c - min(bot, c * 0.9975)), None
        if c < bot and day.c[i - 1] >= bot and day.o[0] > bot:
            return i, -1, max(top, c * 1.0025), c - 2 * (max(top, c * 1.0025) - c), None
    return scan(day, 570, f)


def a12(day):
    p, _, _ = cpr(day)
    r1, s1 = 2 * p - day.pdl, 2 * p - day.pdh

    def f(i):
        c = day.c[i]
        if day.l[i] <= p < c and c > day.o[i] and day.c[i - 1] > p and r1 > c:
            return i, 1, day.l[i] - 0.5, r1, None
        if day.h[i] >= p > c and c < day.o[i] and day.c[i - 1] < p and s1 < c:
            return i, -1, day.h[i] + 0.5, s1, None
    return scan(day, 570, f)


def a13(day):
    def f(i):
        up = day.c[i - 1] <= day.tw[i - 1] and day.c[i] > day.tw[i] and day.ema20[i] > day.ema20[i - 3]
        dn = day.c[i - 1] >= day.tw[i - 1] and day.c[i] < day.tw[i] and day.ema20[i] < day.ema20[i - 3]
        d = 1 if up else -1 if dn else 0
        return (i, d, pct_stop(day, i, d, 0.2), None, None) if d else None
    return scan(day, 600, f)


def cross_trade(day, a, b, start_min, stop_pct):
    def f(i):
        d = 1 if (a[i - 1] <= b[i - 1] and a[i] > b[i]) else -1 if (a[i - 1] >= b[i - 1] and a[i] < b[i]) else 0
        if not d:
            return None
        return i, d, pct_stop(day, i, d, stop_pct), None, first_cross(a, b, i + 1, day.n, -d)
    return scan(day, start_min, f)


def a14(day): return cross_trade(day, day.ema9, day.ema21, 585, 0.25)


def a15(day):
    def f(i):
        c, e20, e50 = day.c[i], day.ema20[i], day.ema50[i]
        if c > e20 > e50 and day.l[i] <= e20 and c > day.o[i]:
            return i, 1, day.l[i] - 0.5, c + 2 * (c - day.l[i] + 0.5), None
        if c < e20 < e50 and day.h[i] >= e20 and c < day.o[i]:
            return i, -1, day.h[i] + 0.5, c - 2 * (day.h[i] + 0.5 - c), None
    return scan(day, 585, f)


def a16(day):
    def f(i):
        d = int(day.st_dir[i])
        if d == day.st_dir[i - 1]:
            return None
        ex = next((b for b in range(i + 1, day.n) if day.st_dir[b] != d), None)
        return i, d, day.st_line[i], None, ex
    return scan(day, 570, f)


def a17(day):
    def f(i):
        if day.rsi[i - 1] < 30 <= day.rsi[i]:
            lo = day.l[max(0, i - 5):i + 1].min()
            return i, 1, lo, day.c[i] + 1.5 * (day.c[i] - lo), None
        if day.rsi[i - 1] > 70 >= day.rsi[i]:
            hi = day.h[max(0, i - 5):i + 1].max()
            return i, -1, hi, day.c[i] - 1.5 * (hi - day.c[i]), None
    return scan(day, 570, f)


def a18(day):
    def f(i):
        if day.rsi[i - 1] <= 60 < day.rsi[i] and day.c[i] > day.tw[i]:
            return i, 1, pct_stop(day, i, 1, 0.25), None, None
        if day.rsi[i - 1] >= 40 > day.rsi[i] and day.c[i] < day.tw[i]:
            return i, -1, pct_stop(day, i, -1, 0.25), None, None
    return scan(day, 585, f)


def a19(day):
    def f(i):
        if not day.squeeze[i - 1]:
            return None
        c, m = day.c[i], day.bbm[i]
        if c > day.bbu[i]:
            return i, 1, m, c + 2 * (c - m), None
        if c < day.bbl[i]:
            return i, -1, m, c - 2 * (m - c), None
    return scan(day, 570, f)


def a20(day):
    def f(i):
        c, m = day.c[i], day.bbm[i]
        if day.c[i - 1] < day.bbl[i - 1] and c > day.bbl[i] and m > c:
            return i, 1, min(day.l[i - 1], day.l[i]) - 0.5, m, None
        if day.c[i - 1] > day.bbu[i - 1] and c < day.bbu[i] and m < c:
            return i, -1, max(day.h[i - 1], day.h[i]) + 0.5, m, None
    return scan(day, 570, f)


def a21(day): return cross_trade(day, day.macd, day.macds, 585, 0.25)


def a22(day):
    k = day.n // 3
    H = day.h[:k * 3].reshape(k, 3).max(axis=1)
    L = day.l[:k * 3].reshape(k, 3).min(axis=1)
    for b in range(1, k):
        if H[b] <= H[b - 1] and L[b] >= L[b - 1]:
            hi, lo = H[b - 1], L[b - 1]
            for i in range((b + 1) * 3, day.n):
                if day.t[i] >= NO_ENTRY_AFTER:
                    return None
                c = day.c[i]
                d = 1 if c > hi else -1 if c < lo else 0
                if d:
                    stop = lo if d > 0 else hi
                    return i, d, stop, c + d * 2 * abs(c - stop), None
            return None
    return None


def a23(day): return orb(day, 15) if day.nr7 else None


def a24(day):
    def f(i):
        if day.l[i - 1] > day.ema5[i - 1] and day.l[i] < day.l[i - 1] and day.h[i - 1] > day.c[i]:
            return i, -1, day.h[i - 1], day.c[i] - 3 * (day.h[i - 1] - day.c[i]), None
        if day.h[i - 1] < day.ema5[i - 1] and day.h[i] > day.h[i - 1] and day.l[i - 1] < day.c[i]:
            return i, 1, day.l[i - 1], day.c[i] + 3 * (day.c[i] - day.l[i - 1]), None
    return scan(day, 570, f)


def a25(day):
    i = at(day, 610)
    move = (day.c[i] - day.o[0]) / day.o[0] * 100
    d = int(np.sign(move))
    return (i, d, pct_stop(day, i, d, 0.3), None, None) if abs(move) >= 0.3 else None


def a26(day):
    a, b = at(day, 720), at(day, 810)
    if b - a < 6:
        return None
    hi, lo = day.h[a:b].max(), day.l[a:b].min()
    for i in range(b, day.n):
        if day.t[i] >= NO_ENTRY_AFTER:
            return None
        c = day.c[i]
        d = 1 if c > hi else -1 if c < lo else 0
        if d:
            return i, d, lo if d > 0 else hi, None, None
    return None


def a27(day):
    def f(i):
        if day.c[i] > day.dhi20[i]:
            return i, 1, day.dlo10[i], None, None
        if day.c[i] < day.dlo20[i]:
            return i, -1, day.dhi10[i], None, None
    return scan(day, 600, f)


def a28(day):
    def f(i):
        g = [day.ha_c[b] > day.ha_o[b] for b in (i - 2, i - 1, i)]
        flat_lo = all(day.ha_l[b] >= day.ha_o[b] - 0.01 for b in (i - 2, i - 1, i))
        flat_hi = all(day.ha_h[b] <= day.ha_o[b] + 0.01 for b in (i - 2, i - 1, i))
        d = 1 if (all(g) and flat_lo) else -1 if (not any(g) and flat_hi) else 0
        if not d:
            return None
        ex = next((b for b in range(i + 1, day.n) if (day.ha_c[b] > day.ha_o[b]) != (d > 0)), None)
        return i, d, day.ha_l[i - 2] if d > 0 else day.ha_h[i - 2], None, ex
    return scan(day, 585, f)


LONG = {
    "A01 Opening range 15 min breakout, 2R": a01, "A02 Opening range 30 min breakout, 2R": a02,
    "A03 First-hour breakout with yesterday's-close filter, 2R": a03, "A04 Opening range 30 min breakout, hold to close": a04,
    "A05 First-30 direction, stop at mid-range": a05, "A06 First 5-min candle direction": a06,
    "A07 Gap and go": a07, "A08 Gap fade back to yesterday's close": a08,
    "A09 Yesterday's high/low breakout": a09, "A10 Yesterday's high/low rejection (sweep)": a10,
    "A11 CPR breakout": a11, "A12 Pivot bounce to R1/S1": a12, "A13 Session average (VWAP-style) cross": a13,
    "A14 EMA 9/21 crossover": a14, "A15 EMA 20 pullback in trend": a15, "A16 Supertrend (10,3) flip": a16,
    "A17 RSI 30/70 reversal": a17, "A18 RSI 60/40 momentum": a18, "A19 Bollinger squeeze breakout": a19,
    "A20 Bollinger band mean reversion": a20, "A21 MACD crossover": a21, "A22 Inside bar (15 min) breakout": a22,
    "A23 NR7 day + opening range breakout": a23, "A24 5 EMA setup (Power of Stocks)": a24,
    "A25 First-hour trend continuation at 10:15": a25, "A26 Afternoon range breakout (after 13:30)": a26,
    "A27 Donchian 20-bar breakout": a27, "A28 Heikin-Ashi trend candles": a28,
}

# ------------------------------------------------------------------ the 11 option-selling strategies
STRADDLE = [("ce", 0, -1), ("pe", 0, -1)]


def b09(day):
    s = a05(day)
    if not s or day.is_expiry:
        return None
    i, d, stop, _, _ = s
    if (day.c[i] - stop) * d <= 0:
        return None
    legs = [("pe", 0, -1), ("pe", -4, 1)] if d > 0 else [("ce", 0, -1), ("ce", 4, 1)]
    return run_short(day, i, legs, index_stop=(d, stop))


SHORT = {
    "B01 09:20 short straddle, 25% stop per leg": lambda d: run_short(d, 0, STRADDLE, leg_sl=0.25),
    "B02 09:20 short straddle, no stop": lambda d: run_short(d, 0, STRADDLE),
    "B03 09:20 short strangle (150 pts out), 50% stop per leg": lambda d: run_short(d, 0, [("ce", 3, -1), ("pe", -3, -1)], leg_sl=0.5),
    "B04 09:20 iron fly (250-pt wings)": lambda d: run_short(d, 0, STRADDLE + [("ce", 5, 1), ("pe", -5, 1)]),
    "B05 09:20 iron condor (150 short, 300 long)": lambda d: run_short(d, 0, [("ce", 3, -1), ("pe", -3, -1), ("ce", 6, 1), ("pe", -6, 1)]),
    "B06 11:00 short straddle, 25% stop per leg": lambda d: run_short(d, at(d, 655), STRADDLE, leg_sl=0.25),
    "B07 Expiry-day short straddle, 30% stop per leg": lambda d: run_short(d, 0, STRADDLE, leg_sl=0.30) if d.is_expiry else None,
    "B08 Non-expiry short straddle, 25% stop per leg": lambda d: None if d.is_expiry else run_short(d, 0, STRADDLE, leg_sl=0.25),
    "B09 First-30 direction as a credit spread (200-pt hedge)": b09,
    "B10 09:20 short straddle, 20% combined stop": lambda d: run_short(d, 0, STRADDLE, combined_sl=0.20),
    "B11 13:00 short straddle to the close, 25% stop per leg": lambda d: run_short(d, at(d, 775), STRADDLE, leg_sl=0.25),
}
HEDGED = ("B04", "B05", "B09")


def main():
    days = prepare()
    out = {}
    for name, fn in LONG.items():
        trades = []
        for day in days[1:]:
            try:
                sig = fn(day)
            except (IndexError, ValueError):
                sig = None
            if sig and not any(x != x for x in sig[1:3]):
                t = run_long(day, sig)
                if t:
                    trades.append(t)
        out[name] = {"family": "Buy option intraday", "capital": 50000, "trades": trades}
        print(f"{name[:58]:58s} {len(trades):5d} trades  net {sum(t['pnl'] for t in trades):11,.0f}  real exits {np.mean([t['real'] for t in trades]) * 100:3.0f}%", flush=True)
    for name, fn in SHORT.items():
        trades = [t for t in (fn(day) for day in days[1:]) if t]
        hedged = name[:3] in HEDGED
        out[name] = {"family": "Sell options (hedged)" if hedged else "Sell options (naked)",
                     "capital": 60000 if hedged else 200000, "trades": trades}
        print(f"{name[:58]:58s} {len(trades):5d} trades  net {sum(t['pnl'] for t in trades):11,.0f}  real exits {np.mean([t['real'] for t in trades]) * 100:3.0f}%", flush=True)
    (ROOT / "zoo_intraday.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
