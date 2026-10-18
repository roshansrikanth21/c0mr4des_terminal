"""Candle anatomy and candlestick patterns, explained in plain English.

Research consensus (Marshall/Young/Rose 2006; Lu et al.; Bulkowski): patterns alone
have little edge. They matter only at a meaningful level (support/resistance) and in
the right trend context. So every pattern here reports `type` (reversal/continuation)
and whether its prior-trend requirement is met; the fusion layer adds location.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .indicators import atr


@dataclass
class Pattern:
    name: str
    direction: int        # +1 bullish, -1 bearish, 0 indecision
    kind: str             # reversal | continuation | indecision
    bars: int             # how many candles form it
    time: str             # timestamp of the completing candle
    price: float          # close of completing candle
    strength: float       # 0..1 base reliability before context
    context_ok: bool      # prior trend requirement satisfied
    meaning: str

    def dict(self):
        return asdict(self)


def anatomy(row: pd.Series, atr_value: float) -> dict:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    size = rng / atr_value if atr_value else 1.0
    color = "green" if c > o else "red" if c < o else "flat"
    close_pos = (c - l) / rng  # 1 = closed at the high
    if size >= 1.5:
        size_word = "a big"
    elif size <= 0.6:
        size_word = "a small"
    else:
        size_word = "an average"
    if body / rng >= 0.7:
        shape = "strong-bodied"
    elif body / rng <= 0.15:
        shape = "indecisive (tiny body)"
    elif upper > 2 * body and upper > lower:
        shape = "long upper wick"
    elif lower > 2 * body and lower > upper:
        shape = "long lower wick"
    else:
        shape = "balanced"
    who = "buyers" if close_pos >= 0.65 else "sellers" if close_pos <= 0.35 else "neither side"
    text = (f"Last candle is {size_word} {color} candle, {shape}. It closed at {close_pos:.0%} of its range, "
            f"so {who} controlled the close.")
    if shape == "long upper wick":
        text += " Price was pushed up but rejected - sellers are active above."
    elif shape == "long lower wick":
        text += " Price was pushed down but bought back - buyers are defending below."
    return {
        "color": color, "body_pct": round(body / rng * 100, 1), "upper_wick_pct": round(upper / rng * 100, 1),
        "lower_wick_pct": round(lower / rng * 100, 1), "range_vs_atr": round(size, 2),
        "close_position": round(close_pos, 2), "shape": shape, "text": text,
    }


def detect(df: pd.DataFrame, lookback: int = 6) -> list[Pattern]:
    """Patterns completed on any of the last `lookback` closed candles (newest last)."""
    if len(df) < 20:
        return []
    a = atr(df, 14)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    out: list[Pattern] = []
    n = len(df)

    def prior_trend(i, bars=5):
        if i - bars - 1 < 0:
            return 0
        move = c[i - 1] - c[i - 1 - bars]
        thr = 0.5 * a.iloc[i - 1] if not np.isnan(a.iloc[i - 1]) else 0
        return 1 if move > thr else -1 if move < -thr else 0

    def add(i, name, d, kind, bars, strength, ctx, meaning):
        out.append(Pattern(name, d, kind, bars, df.index[i].isoformat(), float(c[i]), strength, bool(ctx), meaning))

    for i in range(max(3, n - lookback), n):
        rng = max(h[i] - l[i], 1e-9)
        body = abs(c[i] - o[i])
        up_w = h[i] - max(o[i], c[i])
        lo_w = min(o[i], c[i]) - l[i]
        av = a.iloc[i] if not np.isnan(a.iloc[i]) else rng
        tr = prior_trend(i)
        pb = abs(c[i - 1] - o[i - 1])
        bull, bear = c[i] > o[i], c[i] < o[i]
        pbull, pbear = c[i - 1] > o[i - 1], c[i - 1] < o[i - 1]

        # --- single candle ---
        if body <= 0.1 * rng and rng >= 0.5 * av:
            if lo_w >= 0.65 * rng:
                add(i, "Dragonfly Doji", 1, "reversal", 1, 0.45, tr < 0,
                    "Sellers pushed price down hard but buyers dragged it all the way back. Possible bottom if at support.")
            elif up_w >= 0.65 * rng:
                add(i, "Gravestone Doji", -1, "reversal", 1, 0.45, tr > 0,
                    "Buyers pushed price up but sellers slammed it back down. Possible top if at resistance.")
            else:
                add(i, "Doji", 0, "indecision", 1, 0.3, True,
                    "Open and close are almost equal: buyers and sellers are balanced. Wait for the next candle.")
        elif lo_w >= 2 * body and up_w <= 0.25 * max(body, 1e-9) + 0.1 * rng and body > 0:
            if tr < 0:
                add(i, "Hammer", 1, "reversal", 1, 0.55, True,
                    "After a fall, price dipped and got bought back strongly. Buyers are stepping in.")
            elif tr > 0:
                add(i, "Hanging Man", -1, "reversal", 1, 0.4, True,
                    "After a rise, a long lower wick shows selling pressure appeared. A warning, needs confirmation.")
        elif up_w >= 2 * body and lo_w <= 0.25 * max(body, 1e-9) + 0.1 * rng and body > 0:
            if tr > 0:
                add(i, "Shooting Star", -1, "reversal", 1, 0.55, True,
                    "After a rise, price spiked up and got sold off. Sellers are rejecting higher prices.")
            elif tr < 0:
                add(i, "Inverted Hammer", 1, "reversal", 1, 0.4, True,
                    "After a fall, buyers tried to push up. Weak signal by itself, needs a green follow-through candle.")
        if body >= 0.85 * rng and rng >= 1.2 * av:
            add(i, "Bullish Marubozu" if bull else "Bearish Marubozu", 1 if bull else -1, "continuation", 1, 0.5, True,
                ("A big full-body green candle: buyers were in control from open to close." if bull else
                 "A big full-body red candle: sellers were in control from open to close."))

        # --- two candles ---
        if bull and pbear and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body > pb:
            add(i, "Bullish Engulfing", 1, "reversal", 2, 0.6, tr < 0,
                "A green candle completely swallowed the previous red one. Buyers took over.")
        if bear and pbull and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body > pb:
            add(i, "Bearish Engulfing", -1, "reversal", 2, 0.6, tr > 0,
                "A red candle completely swallowed the previous green one. Sellers took over.")
        if pbear and bull and pb >= 0.6 * av and o[i] < c[i - 1] and c[i] > (o[i - 1] + c[i - 1]) / 2 and c[i] < o[i - 1]:
            add(i, "Piercing Line", 1, "reversal", 2, 0.5, tr < 0,
                "After a strong red candle, price opened lower but closed above its midpoint. Buyers fighting back.")
        if pbull and bear and pb >= 0.6 * av and o[i] > c[i - 1] and c[i] < (o[i - 1] + c[i - 1]) / 2 and c[i] > o[i - 1]:
            add(i, "Dark Cloud Cover", -1, "reversal", 2, 0.5, tr > 0,
                "After a strong green candle, price opened higher but closed below its midpoint. Sellers fighting back.")
        if pb >= 0.6 * av and max(o[i], c[i]) <= max(o[i - 1], c[i - 1]) and min(o[i], c[i]) >= min(o[i - 1], c[i - 1]) and body <= 0.5 * pb:
            d = 1 if pbear else -1
            add(i, "Bullish Harami" if d > 0 else "Bearish Harami", d, "reversal", 2, 0.35, tr == -d,
                "A small candle inside the previous big one: the move is losing steam.")
        if h[i] <= h[i - 1] and l[i] >= l[i - 1]:
            add(i, "Inside Bar", 0, "indecision", 2, 0.3, True,
                f"Range is contracting inside the previous candle ({l[i - 1]:.0f}-{h[i - 1]:.0f}). "
                "A break above or below that range often starts the next move.")
        tol = 0.1 * av
        if tr > 0 and abs(h[i] - h[i - 1]) <= tol and pbull and bear:
            add(i, "Tweezer Top", -1, "reversal", 2, 0.4, True, "Two candles hit the same high and got rejected. Resistance is holding.")
        if tr < 0 and abs(l[i] - l[i - 1]) <= tol and pbear and bull:
            add(i, "Tweezer Bottom", 1, "reversal", 2, 0.4, True, "Two candles hit the same low and bounced. Support is holding.")

        # --- three candles ---
        b2 = abs(c[i - 2] - o[i - 2])
        if c[i - 2] < o[i - 2] and b2 >= 0.6 * av and pb <= 0.4 * b2 and bull and c[i] > (o[i - 2] + c[i - 2]) / 2:
            add(i, "Morning Star", 1, "reversal", 3, 0.65, prior_trend(i - 1) < 0,
                "Big red candle, then a small pause, then a strong green candle: a classic bottom pattern.")
        if c[i - 2] > o[i - 2] and b2 >= 0.6 * av and pb <= 0.4 * b2 and bear and c[i] < (o[i - 2] + c[i - 2]) / 2:
            add(i, "Evening Star", -1, "reversal", 3, 0.65, prior_trend(i - 1) > 0,
                "Big green candle, then a small pause, then a strong red candle: a classic top pattern.")
        if all(c[j] > o[j] and abs(c[j] - o[j]) >= 0.5 * av and c[j] > c[j - 1] and (h[j] - c[j]) <= 0.3 * (h[j] - l[j]) for j in (i - 2, i - 1, i)):
            add(i, "Three White Soldiers", 1, "continuation", 3, 0.55, True,
                "Three strong green candles in a row, each closing higher: steady buying pressure.")
        if all(c[j] < o[j] and abs(c[j] - o[j]) >= 0.5 * av and c[j] < c[j - 1] and (c[j] - l[j]) <= 0.3 * (h[j] - l[j]) for j in (i - 2, i - 1, i)):
            add(i, "Three Black Crows", -1, "continuation", 3, 0.55, True,
                "Three strong red candles in a row, each closing lower: steady selling pressure.")
    return out
