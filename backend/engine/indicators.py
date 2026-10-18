"""Core indicators, Wilder-smoothed where the standard definition says so. All causal."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, dn = rma(d.clip(lower=0), n), rma((-d).clip(lower=0), n)
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = rma(true_range(df), n)
    plus_di = 100 * rma(plus_dm, n) / tr
    minus_di = 100 * rma(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx.fillna(0), n), plus_di, minus_di


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> pd.Series:
    """+1 when price is above the Supertrend line, -1 below."""
    a = atr(df, n)
    hl2 = (df["high"] + df["low"]) / 2
    upper, lower = (hl2 + mult * a).to_numpy(), (hl2 - mult * a).to_numpy()
    close = df["close"].to_numpy()
    direction = np.ones(len(df))
    fu, fl = upper.copy(), lower.copy()
    for i in range(1, len(df)):
        if np.isnan(upper[i]):
            continue
        fu[i] = upper[i] if (np.isnan(fu[i - 1]) or upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (np.isnan(fl[i - 1]) or lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        if close[i] > fu[i - 1]:
            direction[i] = 1
        elif close[i] < fl[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
    return pd.Series(direction, index=df.index)


def linreg_slope(s: pd.Series, n: int = 20) -> tuple[float, float]:
    """Slope (points per bar) and R^2 of the last n closes."""
    y = s.tail(n).to_numpy()
    if len(y) < n:
        return 0.0, 0.0
    x = np.arange(n)
    slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    ss_res = ((y - fit) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    return float(slope), float(1 - ss_res / ss_tot) if ss_tot else 0.0
