"""Fifteen textbook strategies on the markets a prop-firm account trades, scored in R (multiples of the risk taken).

Rules were fixed before any result was looked at. Every trade risks 1R (entry to stop); results are net of a
round-trip cost per instrument (spread + commission, COST below). Stops fill at the stop, or at the bar's open
if it gaps through; if a bar touches both stop and target, the stop is taken. Overnight financing is ignored.
Hours are UTC. Build = 2021-2024, judge = 2025-2026.

Writes data/prop_trades.pkl: DataFrame[strat, sym, t_in, t_out, side, R].
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "prop_cache.pkl"
OUT = ROOT / "data" / "prop_trades.pkl"

# round-trip cost in price units: typical prop-firm raw spread plus commission
COST = {"EURUSD": 0.00010, "GBPUSD": 0.00014, "USDJPY": 0.014, "AUDUSD": 0.00012, "XAUUSD": 0.40, "US500": 0.7, "NAS100": 2.5}
FRAC = set()          # symbols whose COST is a fraction of price (crypto), not price units
MIN_RISK = 4          # skip a trade whose stop is closer than 4x the cost
TRADES = []


def cost(sym, price):
    return COST[sym] * price if sym in FRAC else COST[sym]


def atr(df, n=14):
    pc = df["close"].shift()
    tr = np.maximum(df["high"] - df["low"], np.maximum((df["high"] - pc).abs(), (df["low"] - pc).abs()))
    return tr.rolling(n).mean()


def rsi(c, n):
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def record(strat, sym, df, i, j, side, entry, exit_, risk):
    TRADES.append((strat, sym, df.index[i], df.index[j], side, (side * (exit_ - entry) - cost(sym, entry)) / risk))


def walk(strat, sym, df, i, side, stop, target, last):
    """Enter at the close of bar i; manage on bars i+1..last; time exit at the close of `last`."""
    O, H, L, C = (df[k].values for k in ("open", "high", "low", "close"))
    entry = C[i]
    risk = side * (entry - stop)
    if risk < MIN_RISK * cost(sym, entry) or last <= i:
        return
    for j in range(i + 1, last + 1):
        if side * (O[j] - stop) <= 0:
            return record(strat, sym, df, i, j, side, entry, O[j], risk)
        if (L[j] <= stop) if side > 0 else (H[j] >= stop):
            return record(strat, sym, df, i, j, side, entry, stop, risk)
        if target is not None and ((H[j] >= target) if side > 0 else (L[j] <= target)):
            return record(strat, sym, df, i, j, side, entry, target, risk)
    record(strat, sym, df, i, last, side, entry, C[last], risk)


def machine(strat, sym, df, go, out_long, out_short, a, stop_k, tgt_k=None, max_bars=None):
    """One position at a time: enter on go (+1/-1) at the close, ATR stop, optional target, signal or time exit."""
    O, H, L, C = (df[k].values for k in ("open", "high", "low", "close"))
    go, out_long, out_short, a = (np.asarray(x) for x in (go, out_long, out_short, a))
    pos = 0
    for i in range(len(df)):
        if pos:
            px = None
            if pos * (O[i] - stop) <= 0:
                px = O[i]
            elif (L[i] <= stop) if pos > 0 else (H[i] >= stop):
                px = stop
            elif tgt is not None and ((H[i] >= tgt) if pos > 0 else (L[i] <= tgt)):
                px = tgt
            elif (out_long[i] if pos > 0 else out_short[i]) or (max_bars and i - i0 >= max_bars):
                px = C[i]
            if px is not None:
                record(strat, sym, df, i0, i, pos, entry, px, risk)
                pos = 0
            continue
        if go[i] and a[i] == a[i] and stop_k * a[i] >= MIN_RISK * cost(sym, C[i]):
            pos, i0, entry, risk = int(go[i]), i, C[i], stop_k * a[i]
            stop = entry - pos * risk
            tgt = entry + pos * tgt_k * risk if tgt_k else None


def days_of(df):
    """Yield (prev_day_frame_or_None, {hour: bar index}) for each weekday with a full session."""
    dates = df.index.normalize()
    pos = np.arange(len(df))
    prev = None
    for _, idx in pd.Series(pos).groupby(dates.values):
        idx = idx.values
        if len(idx) < 18:
            continue
        yield prev, {int(h): int(k) for h, k in zip(df.index.hour[idx], idx)}, idx
        prev = idx


def session(sym, df):
    H, L, C, O = (df[k].values for k in ("high", "low", "close", "open"))
    prev_inside = False
    week = None
    for prev, hr, idx in days_of(df):
        last = hr.get(20, idx[-1])
        asia = [hr[h] for h in range(0, 7) if h in hr]
        # S01 London breakout of the Asian range / S02 its failure (sweep and close back inside)
        if len(asia) >= 5:
            hi, lo = H[asia].max(), L[asia].min()
            done1 = done2 = False
            for h in range(7, 12):
                i = hr.get(h)
                if i is None:
                    continue
                if not done1 and (C[i] > hi or C[i] < lo):
                    s = 1 if C[i] > hi else -1
                    walk("S01 London breakout", sym, df, i, s, lo if s > 0 else hi, C[i] + s * (hi - lo), last)
                    done1 = True
                if not done2 and H[i] > hi and C[i] < hi:
                    walk("S02 London sweep fade", sym, df, i, -1, H[i], lo, last)
                    done2 = True
                elif not done2 and L[i] < lo and C[i] > lo:
                    walk("S02 London sweep fade", sym, df, i, 1, L[i], hi, last)
                    done2 = True
        # S03 New York opening-range breakout (13:00-14:00 bar)
        if 13 in hr:
            r = hr[13]
            for h in (14, 15, 16):
                i = hr.get(h)
                if i is not None and (C[i] > H[r] or C[i] < L[r]):
                    s = 1 if C[i] > H[r] else -1
                    stop = L[r] if s > 0 else H[r]
                    walk("S03 NY open breakout", sym, df, i, s, stop, C[i] + 2 * (C[i] - stop), last)
                    break
        # S15 first London hour sets the direction for the day
        if 7 in hr and 16 in hr:
            i = hr[7]
            if C[i] != O[i]:
                s = 1 if C[i] > O[i] else -1
                walk("S15 London first hour", sym, df, i, s, L[i] if s > 0 else H[i], None, hr[16])
        if prev is not None:
            ph, pl = H[prev].max(), L[prev].min()
            d4 = d5 = d13 = False
            for h in range(7, 18):
                i = hr.get(h)
                if i is None:
                    continue
                # S04 previous-day high/low breakout, S13 the same only after an inside day
                if C[i] > ph or C[i] < pl:
                    s = 1 if C[i] > ph else -1
                    stop = C[i] - s * 0.5 * (ph - pl)
                    if not d4:
                        walk("S04 prev-day breakout", sym, df, i, s, stop, C[i] + s * (ph - pl), last)
                        d4 = True
                    if prev_inside and not d13:
                        walk("S13 inside-day breakout", sym, df, i, s, pl if s > 0 else ph, None, last)
                        d13 = True
                # S05 previous-day high/low sweep and rejection (the "liquidity grab")
                if not d5 and H[i] > ph and C[i] < ph:
                    walk("S05 prev-day sweep fade", sym, df, i, -1, H[i], C[i] - 2 * (H[i] - C[i]), last)
                    d5 = True
                elif not d5 and L[i] < pl and C[i] > pl:
                    walk("S05 prev-day sweep fade", sym, df, i, 1, L[i], C[i] + 2 * (C[i] - L[i]), last)
                    d5 = True
        # S14 Monday-range breakout, held to Friday
        wd = df.index[idx[0]].dayofweek
        if wd == 0:
            week = {"hi": H[idx].max(), "lo": L[idx].min(), "done": False}
        elif week and not week["done"] and wd in (1, 2, 3):
            for h in range(7, 18):
                i = hr.get(h)
                if i is not None and (C[i] > week["hi"] or C[i] < week["lo"]):
                    s = 1 if C[i] > week["hi"] else -1
                    fri = df.index[i].normalize() + pd.Timedelta(days=4 - wd, hours=20)
                    end = int(df.index.searchsorted(fri, side="right")) - 1
                    walk("S14 Monday-range breakout", sym, df, i, s, (week["hi"] + week["lo"]) / 2, None, end)
                    week["done"] = True
                    break
        if prev is not None:
            pp_hi, pp_lo = H[prev].max(), L[prev].min()
            prev_inside = False
            prev_prev = getattr(session, "_pp", None)
            if prev_prev is not None:
                prev_inside = pp_hi <= prev_prev[0] and pp_lo >= prev_prev[1]
            session._pp = (pp_hi, pp_lo)
    session._pp = None


def hourly(sym, df):
    c = df["close"]
    a = atr(df).values
    e20, e50, e200 = (c.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    up, dn = (e20 > e50) & (e20.shift() <= e50.shift()), (e20 < e50) & (e20.shift() >= e50.shift())
    go = np.where(up & (c > e200), 1, np.where(dn & (c < e200), -1, 0))
    machine("S06 hourly EMA cross", sym, df, go, dn, up, a, 2)
    hi55, lo55 = df["high"].rolling(55).max().shift(), df["low"].rolling(55).min().shift()
    hi20, lo20 = df["high"].rolling(20).max().shift(), df["low"].rolling(20).min().shift()
    machine("S07 hourly Donchian 55", sym, df, np.where(c > hi55, 1, np.where(c < lo55, -1, 0)), c < lo20, c > hi20, a, 2)
    r = rsi(c, 14)
    machine("S08 hourly RSI fade", sym, df, np.where(r < 25, 1, np.where(r > 75, -1, 0)), r > 50, r < 50, a, 2, max_bars=24)
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    machine("S09 hourly Bollinger fade", sym, df, np.where(c < m - 2.5 * sd, 1, np.where(c > m + 2.5 * sd, -1, 0)), c >= m, c <= m, a, 2,
            max_bars=24)


def daily(sym, df):
    d = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d = d[df["close"].resample("1D").count().reindex(d.index) >= 18]
    daily_strats(sym, d)


def daily_strats(sym, d):
    c = d["close"]
    a = atr(d).values
    hi20, lo20 = d["high"].rolling(20).max().shift(), d["low"].rolling(20).min().shift()
    hi10, lo10 = d["high"].rolling(10).max().shift(), d["low"].rolling(10).min().shift()
    machine("S10 daily Donchian 20", sym, d, np.where(c > hi20, 1, np.where(c < lo20, -1, 0)), c < lo10, c > hi10, a, 2)
    s50, s200, s5 = c.rolling(50).mean(), c.rolling(200).mean(), c.rolling(5).mean()
    up, dn = (s50 > s200) & (s50.shift() <= s200.shift()), (s50 < s200) & (s50.shift() >= s200.shift())
    machine("S11 daily 50/200 cross", sym, d, np.where(up, 1, np.where(dn, -1, 0)), dn, up, a, 3)
    r2 = rsi(c, 2)
    go = np.where((r2 < 10) & (c > s200), 1, np.where((r2 > 90) & (c < s200), -1, 0))
    machine("S12 daily RSI-2 pullback", sym, d, go, c > s5, c < s5, a, 2, max_bars=5)


if __name__ == "__main__":
    data = pickle.load(open(CACHE, "rb"))
    for sym, df in data.items():
        df = df[df.index.dayofweek < 5]
        session(sym, df)
        hourly(sym, df)
        daily(sym, df)
    t = pd.DataFrame(TRADES, columns=["strat", "sym", "t_in", "t_out", "side", "R"])
    t = t[t["t_in"] >= "2021-01-01"].sort_values("t_out").reset_index(drop=True)
    t.to_pickle(OUT)
    print(len(t), "trades,", t["strat"].nunique(), "strategies,", t["sym"].nunique(), "symbols")
