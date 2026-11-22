"""Strategy zoo, part 2: 11 positional strategies on daily data (index ETF, NIFTY 50 stocks, gold ETF, pairs).

Prices are Yahoo daily closes adjusted for dividends and splits. A signal at today's close is traded at that close.
Cash strategies pay 0.18% a side (delivery charges 0.111% + brokerage + 0.05% slippage); the pairs book pays
0.05% a side per leg (futures charges + slippage). Everything is stated on Rs 1,00,000 of capital.

    python research/zoo_daily.py     ->  data/zoo_daily.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.zoo_data import ROOT  # noqa: E402

CAPITAL, COST, PAIR_COST = 100000.0, 0.0018, 0.0005
START, END = "2021-01-01", "2026-11-09"
NIFTY50 = """ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL BPCL
BRITANNIA CIPLA COALINDIA DRREDDY EICHERMOT GRASIM HCLTECH HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HINDUNILVR
ICICIBANK INDUSINDBK INFY ITC JSWSTEEL KOTAKBANK LT M&M MARUTI NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE
SBIN SHRIRAMFIN SUNPHARMA TATACONSUM TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO DIVISLAB""".split()


def fetch() -> pd.DataFrame:
    cache = ROOT / "zoo_daily_prices.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    import yfinance as yf
    tickers = ["NIFTYBEES.NS", "GOLDBEES.NS"] + [t + ".NS" for t in NIFTY50]
    px = yf.download(tickers, start="2017-06-01", end="2026-11-10", auto_adjust=True, progress=False, threads=False)["Close"]
    px = px.dropna(axis=1, thresh=int(len(px) * 0.9)).ffill()
    px.to_pickle(cache)
    return px


def book(pos: pd.Series, ret: pd.Series, cost: float = COST) -> pd.Series:
    """Daily rupee P&L of a 0..1 position held from each close to the next, costs on every change."""
    held = pos.shift().fillna(0)
    return (held * ret - pos.diff().abs().fillna(0) * cost) * CAPITAL


def supertrend_dir(h, l, c, n=10, m=3.0):
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    ub, lb, cl = ((h + l) / 2 + m * atr).to_numpy().copy(), ((h + l) / 2 - m * atr).to_numpy().copy(), c.to_numpy()
    d = np.ones(len(c), int)
    for i in range(1, len(c)):
        ub[i] = ub[i] if (ub[i] < ub[i - 1] or cl[i - 1] > ub[i - 1]) else ub[i - 1]
        lb[i] = lb[i] if (lb[i] > lb[i - 1] or cl[i - 1] < lb[i - 1]) else lb[i - 1]
        d[i] = 1 if cl[i] > ub[i - 1] else -1 if cl[i] < lb[i - 1] else d[i - 1]
    return pd.Series(d, index=c.index)


def stateful(enter: pd.Series, leave: pd.Series, max_days: int | None = None) -> pd.Series:
    pos, held, out = 0, 0, []
    for e, x in zip(enter.to_numpy(), leave.to_numpy()):
        if pos and (x or (max_days and held >= max_days)):
            pos = 0
        elif not pos and e:
            pos, held = 1, 0
        held += pos
        out.append(pos)
    return pd.Series(out, index=enter.index, dtype=float)


def rotation(px: pd.DataFrame, score: pd.DataFrame, top: int, largest: bool = True) -> pd.Series:
    """Equal-weight the best `top` names by `score`, rebalanced on the last trading day of each month."""
    ret = px.pct_change()
    month_end = px.index.to_series().groupby(px.index.to_period("M")).max()
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    cur = pd.Series(0.0, index=px.columns)
    for d in px.index:
        if d in set(month_end):
            s = score.loc[d].dropna()
            if len(s) >= top:
                pick = (s.nlargest(top) if largest else s.nsmallest(top)).index
                cur = pd.Series(0.0, index=px.columns)
                cur[pick] = 1.0 / top
        w.loc[d] = cur
    held = w.shift().fillna(0)
    turnover = w.diff().abs().sum(axis=1).fillna(0)
    return ((held * ret).sum(axis=1) - turnover * COST) * CAPITAL


def df_stat(resid: np.ndarray) -> float:
    """Dickey-Fuller t-statistic of a residual series (more negative = more mean-reverting)."""
    y, x = np.diff(resid), resid[:-1]
    b = (x @ y) / (x @ x)
    e = y - b * x
    se = np.sqrt((e @ e) / (len(y) - 1) / (x @ x))
    return b / se


def pairs(px: pd.DataFrame, n_pairs: int = 15) -> pd.Series:
    """The reel's rule: spread = log A - beta * log B, enter at z = +-2, exit at 0, stop at 3.5 or 30 days.
    Pairs are chosen each January from the previous two years only, then traded for that year."""
    logp = np.log(px)
    pnl = pd.Series(0.0, index=px.index)
    alloc = CAPITAL / n_pairs
    for year in range(2021, 2027):
        form = logp[(logp.index >= f"{year - 2}-01-01") & (logp.index < f"{year}-01-01")].dropna(axis=1)
        trade_idx = logp.index[(logp.index >= f"{year}-01-01") & (logp.index < f"{year + 1}-01-01")]
        if len(form) < 300 or not len(trade_idx):
            continue
        r = form.diff().dropna()
        corr = r.corr()
        cands = []
        cols = list(form.columns)
        for a_i, a in enumerate(cols):
            for b in cols[a_i + 1:]:
                if corr.loc[a, b] < 0.5:
                    continue
                x, y = form[b].to_numpy(), form[a].to_numpy()
                beta = np.cov(x, y)[0, 1] / np.var(x)
                if not 0.3 < beta < 3:
                    continue
                resid = y - beta * x
                cands.append((df_stat(resid - resid.mean()), a, b, beta))
        used, chosen = set(), []
        for stat, a, b, beta in sorted(cands):
            if a in used or b in used:
                continue
            chosen.append((a, b, beta))
            used |= {a, b}
            if len(chosen) == n_pairs:
                break
        for a, b, beta in chosen:
            spread = logp[a] - beta * logp[b]
            z = (spread - spread.rolling(60).mean()) / spread.rolling(60).std()
            ra, rb = px[a].pct_change(), px[b].pct_change()
            pos, held = 0, 0
            for d in trade_idx:
                zi = z.get(d)
                if pos:
                    pnl[d] += alloc * pos * (ra[d] - beta * rb[d])
                    held += 1
                    if zi != zi or (pos > 0 and zi >= 0) or (pos < 0 and zi <= 0) or abs(zi) > 3.5 or held >= 30:
                        pnl[d] -= alloc * (1 + beta) * PAIR_COST
                        pos = 0
                if not pos and zi == zi and 2 < abs(zi) <= 3.5:
                    pos, held = (-1 if zi > 0 else 1), 0
                    pnl[d] -= alloc * (1 + beta) * PAIR_COST
    return pnl


def main():
    px = fetch()
    stocks = px.drop(columns=[c for c in ("NIFTYBEES.NS", "GOLDBEES.NS") if c in px.columns])
    n = px["NIFTYBEES.NS"]
    ret = n.pct_change()
    sma = lambda k: n.rolling(k).mean()  # noqa: E731
    delta = n.diff()
    rsi2 = 100 - 100 / (1 + delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
                        / (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean())
    down3 = (n < n.shift()) & (n.shift() < n.shift(2)) & (n.shift(2) < n.shift(3))
    dom = pd.Series(n.index.to_series().groupby(n.index.to_period("M")).cumcount().to_numpy(), index=n.index)
    last_of_month = pd.Series(n.index.to_period("M") != pd.Series(n.index, index=n.index).shift(-1).dt.to_period("M"), index=n.index)
    tom = (last_of_month | (dom < 2)).astype(float)
    mom_n, mom_g = n / n.shift(252) - 1, px["GOLDBEES.NS"] / px["GOLDBEES.NS"].shift(252) - 1
    month_end = set(n.index.to_series().groupby(n.index.to_period("M")).max())
    dual, cur = [], (0.0, 0.0)
    for d in n.index:
        if d in month_end and mom_n[d] == mom_n[d]:
            cur = (1.0, 0.0) if (mom_n[d] >= mom_g[d] and mom_n[d] > 0) else (0.0, 1.0) if mom_g[d] > 0 else (0.0, 0.0)
        dual.append(cur)
    dual = pd.DataFrame(dual, index=n.index, columns=["n", "g"])
    dual_pnl = book(dual.n, ret) + book(dual.g, px["GOLDBEES.NS"].pct_change())

    books = {
        "C01 NIFTY above its 200-day average": book((n > sma(200)).astype(float), ret),
        "C02 Golden cross (50-day above 200-day)": book((sma(50) > sma(200)).astype(float), ret),
        "C03 RSI(2) dip buy above the 200-day average": book(stateful((rsi2 < 10) & (n > sma(200)), n > sma(5)), ret),
        "C04 Donchian 55-day breakout, 20-day exit": book(stateful(n > n.rolling(55).max().shift(), n < n.rolling(20).min().shift()), ret),
        "C05 Supertrend (10,3) on daily, long only": book((supertrend_dir(n, n, n) > 0).astype(float), ret),
        "C06 Buy after 3 down days, sell first up day": book(stateful(down3, n > n.shift(), max_days=5), ret),
        "C07 Turn of the month (last day to day 2)": book(tom, ret),
        "C08 Momentum: top 5 NIFTY 50 stocks, 12-1 month": rotation(stocks, stocks.shift(21) / stocks.shift(252) - 1, 5),
        "C09 Low volatility: 10 calmest NIFTY 50 stocks": rotation(stocks, stocks.pct_change().rolling(252).std(), 10, largest=False),
        "C10 Dual momentum: NIFTY vs gold vs cash": dual_pnl,
        "C11 Pairs trading, z-score 2 in / 0 out (15 pairs)": pairs(stocks),
        "ZZ Benchmark: buy and hold NIFTY ETF": book(pd.Series(1.0, index=n.index), ret),
    }
    out = {}
    for name, s in books.items():
        s = s[(s.index >= START) & (s.index <= END)].fillna(0)
        monthly = s.groupby(s.index.to_period("M")).sum()
        out[name] = {"family": "Pairs (needs futures)" if name.startswith("C11") else "Benchmark" if name.startswith("ZZ") else "Positional (cash)",
                     "capital": CAPITAL, "daily": True,
                     "trades": [{"date": str(d.date()), "pnl": round(float(v), 2)} for d, v in s.items() if v],
                     "periods": [round(float(v), 2) for v in monthly]}
        print(f"{name[:52]:52s} net {s.sum():10,.0f}  ({s.sum() / CAPITAL * 100:6.1f}% on Rs 1L over the period)", flush=True)
    print("stocks used:", len(stocks.columns), "| prices", px.index[0].date(), "->", px.index[-1].date())
    (ROOT / "zoo_daily.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
