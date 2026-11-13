"""The one edge with decades of evidence here (buy a sharp dip in an uptrend, daily bars), tested as a plain
cash strategy on ETFs: no leverage, no shorting, nothing a small account cannot do.

Rule, unchanged from S12's long side: close above the 200-day average and RSI(2) below 10 -> buy at the close.
Sell at the close when price is back above its 5-day average, after 5 days, or at a 2-ATR stop.
Universe fixed before running: 34 liquid US-listed ETFs (broad indices, sectors, countries, bonds, metals),
all the history Yahoo has from 2000. ETFs, not stocks, so there is no survivorship bias from picking today's winners.
Cost 0.05% a side.

Pass marks, fixed before running:
  rule      at least 2,000 trades, t-statistic >= 3, at least 75% of calendar years positive
  portfolio (5 slots of 20%, lowest RSI first): beats cash in at least 75% of years, worst drawdown under 25%
  learning  walk-forward model (each year trained only on earlier years): its picks must average more per trade than
            the trades it skips in at least 70% of years from 2010

Writes research/DIP_ETF_RESULTS.md and data/dip_trades.pkl.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import sweep  # noqa: E402

US = ["SPY", "QQQ", "IWM", "DIA", "MDY", "EFA", "EEM", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "VNQ", "GLD",
      "SLV", "TLT", "IEF", "LQD", "HYG", "EWJ", "EWZ", "FXI", "EWG", "EWU", "EWC", "EWA", "EWT", "EWY", "SMH", "XBI"]
INDIA = ["NIFTYBEES.NS", "JUNIORBEES.NS", "BANKBEES.NS", "GOLDBEES.NS", "MON100.NS"]
COST = 0.0005
FEATS = ["rsi2", "trend", "vol", "ret5", "ret20", "vol_ratio", "mkt_trend", "mkt_rsi2", "mkt_ret20", "breadth", "month", "grp"]
GRP = {**{s: 0 for s in ["SPY", "QQQ", "IWM", "DIA", "MDY", "SMH", "XBI"]}, **{s: 1 for s in US if s.startswith("XL")}, "VNQ": 1,
       **{s: 2 for s in ["EFA", "EEM", "EWJ", "EWZ", "FXI", "EWG", "EWU", "EWC", "EWA", "EWT", "EWY"]},
       **{s: 3 for s in ["TLT", "IEF", "LQD", "HYG"]}, "GLD": 4, "SLV": 4}


def frames(tickers, clean=False):
    raw = sweep.yahoo_daily(tickers, start="2000-01-01")
    out = {}
    for tk in tickers:
        d = pd.DataFrame({k: raw[k.capitalize()][tk] for k in ("open", "high", "low", "close")}).dropna()
        if clean:                                   # Yahoo's Indian ETF history has bad ticks and unadjusted splits
            r = d["close"].pct_change()
            d = d[(r.abs() < 0.15) | r.isna()]
            scale = (1 + d["close"].pct_change().fillna(0).where(lambda x: x.abs() < 0.15, 0)).cumprod() / d["close"] * d["close"].iloc[0]
            d = d.mul(scale, axis=0)
        if len(d) > 400:
            out[tk] = d[d["high"] >= d["low"]]
    return out


def indicators(d):
    c = d["close"]
    pc = c.shift()
    tr = np.maximum(d["high"] - d["low"], np.maximum((d["high"] - pc).abs(), (d["low"] - pc).abs()))
    diff = c.diff()
    up, dn = diff.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(), (-diff.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    f = pd.DataFrame(index=d.index)
    f["atr"], f["s200"], f["s5"] = tr.rolling(14).mean(), c.rolling(200).mean(), c.rolling(5).mean()
    f["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    f["trend"], f["vol"] = (c - f["s200"]) / f["atr"], f["atr"] / c
    f["ret5"], f["ret20"] = (c - c.shift(5)) / f["atr"], (c - c.shift(20)) / f["atr"]
    f["vol_ratio"] = f["atr"] / f["atr"].rolling(120).mean()
    return f


def trades(data, market="SPY"):
    ind = {s: indicators(d) for s, d in data.items()}
    mk = ind[market]
    rows = []
    for sym, d in data.items():
        f = ind[sym]
        O, H, L, C = (d[k].values for k in ("open", "high", "low", "close"))
        go = ((d["close"] > f["s200"]) & (f["rsi2"] < 10) & f["atr"].notna()).values
        out_sig, atr = (d["close"] > f["s5"]).values, f["atr"].values
        i, n = 0, len(d)
        while i < n - 1:
            if not go[i]:
                i += 1
                continue
            entry, stop, j, px = C[i], C[i] - 2 * atr[i], i, None
            while px is None and j < n - 1:
                j += 1
                if O[j] <= stop:
                    px = O[j]
                elif L[j] <= stop:
                    px = stop
                elif out_sig[j] or j - i >= 5:
                    px = C[j]
            if px is None:
                break
            day = d.index[i]
            m = mk.loc[:day].iloc[-1] if day >= mk.index[0] else None
            rows.append({"sym": sym, "t_in": day, "t_out": d.index[j], "ret": px / entry - 1 - 2 * COST,
                         "R": (px - entry - 2 * COST * entry) / (2 * atr[i]), "rsi2": f["rsi2"].iloc[i], "trend": f["trend"].iloc[i],
                         "vol": f["vol"].iloc[i], "ret5": f["ret5"].iloc[i], "ret20": f["ret20"].iloc[i], "vol_ratio": f["vol_ratio"].iloc[i],
                         "mkt_trend": m["trend"] if m is not None else np.nan, "mkt_rsi2": m["rsi2"] if m is not None else np.nan,
                         "mkt_ret20": m["ret20"] if m is not None else np.nan, "month": day.month, "grp": GRP.get(sym, 5)})
            i = j
    t = pd.DataFrame(rows).sort_values("t_in").reset_index(drop=True)
    t["breadth"] = t.groupby("t_in")["sym"].transform("count")
    return t


def stats(r):
    r = np.asarray(r, dtype=float)
    if len(r) < 3:
        return {"n": len(r), "avg": 0.0, "pf": 0.0, "t": 0.0, "win": 0.0}
    g, l = r[r > 0].sum(), -r[r <= 0].sum()
    return {"n": len(r), "avg": r.mean(), "pf": g / l if l else 0, "t": r.mean() / (r.std() / np.sqrt(len(r))), "win": 100 * (r > 0).mean()}


def portfolio(t, slots=5, order="rsi2"):
    """Equal slots; a new signal takes a free slot (lowest `order` first). Returns yearly % and worst drawdown."""
    days = pd.date_range(t["t_in"].min(), t["t_out"].max(), freq="B")
    eq, open_, curve = 1.0, [], []
    by_in = {k: g.sort_values(order) for k, g in t.groupby("t_in")}
    for day in days:
        for p in [p for p in open_ if p["t_out"] <= day]:
            eq += p["size"] * p["ret"]
            open_.remove(p)
        for _, r in (by_in.get(day, pd.DataFrame()).iterrows() if day in by_in else []):
            if len(open_) < slots and r["sym"] not in {p["sym"] for p in open_}:
                open_.append({"sym": r["sym"], "t_out": r["t_out"], "ret": r["ret"], "size": eq / slots})
        curve.append(eq)
    c = pd.Series(curve, index=days)
    yearly = c.groupby(c.index.year).last().pct_change()
    yearly.iloc[0] = c.groupby(c.index.year).last().iloc[0] - 1
    return yearly * 100, float((c / c.cummax() - 1).min() * 100), float((c.iloc[-1] ** (252 / len(c)) - 1) * 100), c


def learn_walk(t, first=2010):
    t = t.copy()
    t["pred"] = np.nan
    for y in range(first, int(t["t_in"].dt.year.max()) + 1):
        tr, te = t[t["t_out"] < f"{y}-01-01"], t[t["t_in"].dt.year == y]
        if len(tr) < 500 or not len(te):
            continue
        m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=100, l2_regularization=1.0,
                                          random_state=7).fit(tr[FEATS], tr["ret"].clip(-0.1, 0.1))
        t.loc[te.index, "pred"] = m.predict(te[FEATS])
        t.loc[te.index, "cut"] = float(np.median(m.predict(tr[FEATS])))        # take the better half, as judged on its own past
    return t


def main():
    out = []
    w = out.append
    w("# Buying dips in an uptrend, on ETFs, as a plain cash strategy\n")
    w("Generated by `dip_etf.py`. Rule, universe, costs and pass marks were fixed before the first run.\n")
    t = trades(frames(US))
    t.to_pickle(ROOT / "data" / "dip_trades.pkl")
    s = stats(t["ret"])
    yr = t.groupby(t["t_in"].dt.year)["ret"].sum()
    w("## 1. The rule itself, every signal, 34 US-listed ETFs\n")
    w(f"**{s['n']:,} trades**, {t['t_in'].min().date()} to {t['t_out'].max().date()}. Win rate {s['win']:.0f}%, average {100 * s['avg']:+.2f}% a trade "
      f"after costs, profit factor {s['pf']:.2f}, t-statistic {s['t']:.1f}. Average hold "
      f"{(t['t_out'] - t['t_in']).dt.days.mean():.1f} days. Calendar years positive: **{int((yr > 0).sum())} of {len(yr)}**.\n")
    ok1 = s["n"] >= 2000 and s["t"] >= 3 and (yr > 0).mean() >= 0.75
    w(f"Pass mark (2,000 trades, t 3, 75% of years positive): **{'PASSED' if ok1 else 'NOT PASSED'}**.\n")
    w("| Period | Trades | Win % | Avg % a trade | PF | t-stat |")
    w("|---|---|---|---|---|---|")
    for a, b in ((2000, 2009), (2010, 2019), (2020, 2022), (2023, 2026)):
        g = t[(t["t_in"].dt.year >= a) & (t["t_in"].dt.year <= b)]
        x = stats(g["ret"])
        w(f"| {a}-{b} | {x['n']} | {x['win']:.0f} | {100 * x['avg']:+.2f} | {x['pf']:.2f} | {x['t']:.1f} |")
    w("\n| Group | Trades | Avg % a trade | PF | t-stat |")
    w("|---|---|---|---|---|")
    for g_, lab in enumerate(["US broad and tech", "US sectors and property", "Other countries", "Bonds", "Gold and silver"]):
        x = stats(t[t["grp"] == g_]["ret"])
        w(f"| {lab} | {x['n']} | {100 * x['avg']:+.2f} | {x['pf']:.2f} | {x['t']:.1f} |")

    w("\n## 2. As a portfolio: five slots of 20% each, most oversold first, cash otherwise\n")
    yearly, dd, cagr, curve = portfolio(t)
    w(f"Compound return **{cagr:+.1f}% a year**, worst drawdown **{dd:.1f}%**, years positive {int((yearly > 0).sum())} of {len(yearly)}, "
      f"worst year {yearly.min():+.1f}%, best year {yearly.max():+.1f}%. No interest is credited on idle cash.\n")
    spy = frames(["SPY"])["SPY"]["close"]
    spy = spy[spy.index >= curve.index[0]]
    spy_y = spy.groupby(spy.index.year).last().pct_change().mul(100)
    spy_y.iloc[0] = (spy.groupby(spy.index.year).last().iloc[0] / spy.iloc[0] - 1) * 100
    w(f"For scale, holding SPY over the same period: {((spy.iloc[-1] / spy.iloc[0]) ** (252 / len(spy)) - 1) * 100:+.1f}% a year, "
      f"worst drawdown {float((spy / spy.cummax() - 1).min() * 100):.1f}%.\n")
    w("| Year | " + " | ".join(str(y) for y in yearly.index) + " |")
    w("|" + "---|" * (len(yearly) + 1))
    w("| Dip portfolio | " + " | ".join(f"{v:+.0f}%" for v in yearly) + " |")
    w("| SPY held | " + " | ".join(f"{spy_y.get(y, float('nan')):+.0f}%" for y in yearly.index) + " |")
    ok2 = (yearly > 0).mean() >= 0.75 and dd > -25
    w(f"\nPass mark (positive in 75% of years, drawdown under 25%): **{'PASSED' if ok2 else 'NOT PASSED'}**.\n")

    w("## 3. The learning layer: does a model trained on its own past pick the better dips?\n")
    d = learn_walk(t).dropna(subset=["pred"])
    d["take"] = d["pred"] > d["cut"]
    w("Each year's model has only seen trades that closed before that year. It takes a dip when its score beats the middle score of its own past.\n")
    w("| Year | Trades | Taken | Taken avg % | Skipped avg % | Taken better? |")
    w("|---|---|---|---|---|---|")
    wins = 0
    years = sorted(d["t_in"].dt.year.unique())
    for y in years:
        g = d[d["t_in"].dt.year == y]
        a, b = g[g["take"]]["ret"].mean() * 100, g[~g["take"]]["ret"].mean() * 100
        wins += a > b
        w(f"| {y} | {len(g)} | {int(g['take'].sum())} | {a:+.2f} | {b:+.2f} | {'yes' if a > b else 'no'} |")
    a, b = stats(d[d["take"]]["ret"]), stats(d[~d["take"]]["ret"])
    w(f"\nAll years: taken {a['n']} trades, {100 * a['avg']:+.2f}% a trade, PF {a['pf']:.2f}, t {a['t']:.1f}; "
      f"skipped {b['n']} trades, {100 * b['avg']:+.2f}% a trade, PF {b['pf']:.2f}, t {b['t']:.1f}.")
    ok3 = wins / len(years) >= 0.70
    w(f"\nPass mark (taken beats skipped in 70% of years): **{'PASSED' if ok3 else 'NOT PASSED'}** ({wins} of {len(years)} years).\n")
    yl, ddl, cagrl, _ = portfolio(d[d["take"]], order="rsi2")
    ya, dda, cagra, _ = portfolio(d, order="rsi2")
    w(f"Portfolio from {years[0]}: model's picks {cagrl:+.1f}% a year (drawdown {ddl:.1f}%), every signal {cagra:+.1f}% a year (drawdown {dda:.1f}%).\n")

    w("## 4. Not tested: ETFs listed in India\n")
    w("Yahoo's price history for the NSE-listed ETFs has bad ticks and unadjusted splits that a 5-day strategy cannot be cleaned of, "
      "so no figure is reported. It would need exchange data.")
    (ROOT / "research" / "DIP_ETF_RESULTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
