"""Market structure: swings, HH/HL/LH/LL, break of structure, key levels, fair-value gaps.

All swing points are confirmed only after `k` later bars exist, so nothing here
looks into the future relative to the last closed candle.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr


def swings(df: pd.DataFrame, k: int = 2, min_atr: float = 0.6) -> list[dict]:
    """Confirmed alternating swing highs/lows (fractal pivots, ATR-filtered zigzag)."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    a = atr(df, 14).bfill().to_numpy()
    raw = []
    for i in range(k, len(df) - k):
        if h[i] == max(h[i - k:i + k + 1]) and h[i] > max(h[i - k:i]):
            raw.append({"i": i, "type": "H", "price": float(h[i])})
        if l[i] == min(l[i - k:i + k + 1]) and l[i] < min(l[i - k:i]):
            raw.append({"i": i, "type": "L", "price": float(l[i])})
    piv: list[dict] = []
    for p in raw:
        if piv and piv[-1]["type"] == p["type"]:
            better = p["price"] > piv[-1]["price"] if p["type"] == "H" else p["price"] < piv[-1]["price"]
            if better:
                piv[-1] = p
            continue
        if piv and abs(p["price"] - piv[-1]["price"]) < min_atr * a[p["i"]]:
            continue
        piv.append(p)
    last_h = last_l = None
    for p in piv:
        p["time"] = df.index[p["i"]].isoformat()
        if p["type"] == "H":
            p["label"] = "HH" if last_h is None or p["price"] > last_h else "LH"
            last_h = p["price"]
        else:
            p["label"] = "HL" if last_l is None or p["price"] > last_l else "LL"
            last_l = p["price"]
    return piv


def trend_from_swings(piv: list[dict]) -> tuple[int, str]:
    highs = [p for p in piv if p["type"] == "H"][-2:]
    lows = [p for p in piv if p["type"] == "L"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return 0, "Not enough swings yet to read structure."
    hh, hl = highs[-1]["price"] > highs[-2]["price"], lows[-1]["price"] > lows[-2]["price"]
    if hh and hl:
        return 1, "Higher highs and higher lows: the structure is UP."
    if not hh and not hl:
        return -1, "Lower highs and lower lows: the structure is DOWN."
    return 0, "Mixed highs and lows: price is ranging / undecided."


def break_of_structure(df: pd.DataFrame, piv: list[dict], s_trend: int) -> dict | None:
    """Latest close beyond the most recent confirmed swing. CHoCH = break against the trend."""
    if not piv:
        return None
    c = float(df["close"].iloc[-1])
    last_h = next((p for p in reversed(piv) if p["type"] == "H"), None)
    last_l = next((p for p in reversed(piv) if p["type"] == "L"), None)
    if last_h and c > last_h["price"]:
        kind = "CHoCH" if s_trend < 0 else "BOS"
        return {"direction": 1, "kind": kind, "level": last_h["price"],
                "text": (f"Price closed above the last swing high {last_h['price']:.0f}. " +
                         ("This breaks the downtrend (change of character) - early sign of reversal UP." if kind == "CHoCH"
                          else "Uptrend continues (break of structure)."))}
    if last_l and c < last_l["price"]:
        kind = "CHoCH" if s_trend > 0 else "BOS"
        return {"direction": -1, "kind": kind, "level": last_l["price"],
                "text": (f"Price closed below the last swing low {last_l['price']:.0f}. " +
                         ("This breaks the uptrend (change of character) - early sign of reversal DOWN." if kind == "CHoCH"
                          else "Downtrend continues (break of structure)."))}
    return None


def key_levels(intraday: pd.DataFrame, daily: pd.DataFrame, step: int) -> list[dict]:
    """Previous-day H/L/C, CPR, today's open, 15-min opening range, round numbers."""
    levels: list[dict] = []
    today = intraday.index[-1].date()
    prev_days = daily[daily.index.date < today] if not daily.empty else daily
    if len(prev_days):
        pd_row = prev_days.iloc[-1]
        H, L, C = float(pd_row["high"]), float(pd_row["low"]), float(pd_row["close"])
        P = (H + L + C) / 3
        BC = (H + L) / 2
        TC = 2 * P - BC
        levels += [
            {"name": "Prev Day High", "price": H, "weight": 3},
            {"name": "Prev Day Low", "price": L, "weight": 3},
            {"name": "Prev Close", "price": C, "weight": 2},
            {"name": "CPR Pivot", "price": round(P, 2), "weight": 2},
            {"name": "CPR Top", "price": round(max(TC, BC), 2), "weight": 1},
            {"name": "CPR Bottom", "price": round(min(TC, BC), 2), "weight": 1},
        ]
    today_bars = intraday[intraday.index.date == today]
    if len(today_bars):
        levels.append({"name": "Today Open", "price": float(today_bars["open"].iloc[0]), "weight": 1})
        orb = today_bars[today_bars.index.time < pd.Timestamp("09:30").time()]
        if len(orb) and today_bars.index[-1].time() >= pd.Timestamp("09:30").time():
            levels.append({"name": "Opening Range High", "price": float(orb["high"].max()), "weight": 2})
            levels.append({"name": "Opening Range Low", "price": float(orb["low"].min()), "weight": 2})
    price = float(intraday["close"].iloc[-1])
    rnd = step * 2
    base = round(price / rnd) * rnd
    for r in (base - rnd, base, base + rnd):
        levels.append({"name": "Round Number", "price": float(r), "weight": 1})
    return levels


def swing_zones(piv: list[dict], atr_value: float) -> list[dict]:
    """Cluster swing prices into support/resistance zones; more touches = stronger."""
    prices = sorted(p["price"] for p in piv)
    zones, cur = [], []
    for p in prices:
        if cur and p - cur[0] > 0.5 * atr_value:
            zones.append(cur)
            cur = []
        cur.append(p)
    if cur:
        zones.append(cur)
    return [{"name": f"Swing zone ({len(z)} touches)", "price": round(float(np.mean(z)), 2), "weight": min(3, len(z))}
            for z in zones if len(z) >= 2]


def nearest(levels: list[dict], price: float) -> tuple[dict | None, dict | None]:
    sup = max((lv for lv in levels if lv["price"] < price), key=lambda lv: lv["price"], default=None)
    res = min((lv for lv in levels if lv["price"] > price), key=lambda lv: lv["price"], default=None)
    return sup, res


def fair_value_gaps(df: pd.DataFrame, lookback: int = 40) -> list[dict]:
    """Unfilled 3-candle imbalances in the recent window."""
    out = []
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    start = max(2, len(df) - lookback)
    for i in range(start, len(df)):
        if l[i] > h[i - 2] and (l[i] - h[i - 2]) / c[i] > 0.0002:
            lo, hi, d = h[i - 2], l[i], 1
        elif h[i] < l[i - 2] and (l[i - 2] - h[i]) / c[i] > 0.0002:
            lo, hi, d = h[i], l[i - 2], -1
        else:
            continue
        after = df.iloc[i + 1:]
        filled = (after["low"] <= lo).any() if d > 0 else (after["high"] >= hi).any()
        if not filled:
            out.append({"direction": d, "low": float(lo), "high": float(hi), "time": df.index[i - 1].isoformat()})
    return out[-4:]
