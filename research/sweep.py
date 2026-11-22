"""Everything set aside earlier in the project, tested now that the scope is wider than Indian options.

  A  Crypto (the Hyperliquid idea): the 15 prop_zoo strategies on BTC, ETH, SOL hourly bars, 2021-2026.
  B  Fair-value-gap entry (the ICT video), on forex, gold, US indices and crypto.
  C  The reel's 15-minute opening-range breakout, on the S&P 500 and Nasdaq 100 at the New York open.
  D  The surviving daily RSI-2 pullback, on every year of free daily history (back to the 1990s).
  E  Pairs trading (the reel's z-score rule) on US large caps.
  F  The NIFTY-or-gold rotation, on all the history there is, and the same rule on SPY and GLD.
  G  Copy-the-investor (the trader-skill repo): Berkshire and the two Congress-trade ETFs against the index.

Rules fixed before results. Intraday sets: picked on 2021-2024, judged on 2025-2026, costs in.
Writes research/SWEEP_RESULTS.md. Needs data/prop_hd (run prop_data.py first) and internet for the rest.
"""
import io
import pickle
import sys
import urllib.request
import zlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import prop_data, prop_zoo as Z  # noqa: E402
from research import zoo_daily  # noqa: E402

DATA = ROOT / "data"
SPLIT = pd.Timestamp("2025-01-01")
CRYPTO = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "SOLUSD": "SOLUSDT"}
OUT = []
w = OUT.append


# ---------------------------------------------------------------- data
def crypto_hourly():
    cache = DATA / "sweep_crypto.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    out = {}
    for sym, pair in CRYPTO.items():
        frames = []
        for y in range(2020, 2027):
            for m in range(1, 13):
                if (y, m) > (2026, 10):
                    continue
                url = f"https://data.binance.vision/data/spot/monthly/klines/{pair}/1h/{pair}-1h-{y}-{m:02d}.zip"
                try:
                    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=40).read()))
                except Exception:  # noqa: BLE001
                    continue
                df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), header=None, usecols=[0, 1, 2, 3, 4],
                                 names=["t", "open", "high", "low", "close"])
                df = df[pd.to_numeric(df["t"], errors="coerce").notna()].astype(float)
                t = df["t"].where(df["t"] < 1e14, df["t"] / 1000)          # 2025+ files are in microseconds
                df.index = pd.to_datetime(t, unit="ms")
                frames.append(df[["open", "high", "low", "close"]])
        out[sym] = pd.concat(frames).sort_index()
        print(sym, len(out[sym]), out[sym].index[0], out[sym].index[-1], flush=True)
    pickle.dump(out, open(cache, "wb"))
    return out


def yahoo_daily(tickers, start="1990-01-01"):
    import yfinance as yf
    tickers = list(tickers)
    key = "sweep_" + str(zlib.crc32(",".join(tickers).encode())) + ".pkl"
    if (DATA / key).exists():
        return pd.read_pickle(DATA / key)
    df = yf.download(list(tickers), start=start, progress=False, auto_adjust=True, threads=False)
    df.to_pickle(DATA / key)
    return df


def index_15m(pair):
    files = sorted((DATA / "prop_hd").glob(f"{pair}_*.zip"))
    m1 = pd.concat([prop_data.read(f) for f in files]).sort_index()
    m1 = m1[~m1.index.duplicated()]
    m1.index = m1.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    return m1.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


# ---------------------------------------------------------------- strategies added here
def fvg(sym, df):
    """S16: a three-bar gap in the trend's direction; enter when price comes back into the gap and holds it."""
    H, L, C = (df[k].values for k in ("high", "low", "close"))
    e200 = df["close"].ewm(span=200, adjust=False).mean().values
    n = len(df)
    for i in range(200, n - 40 if n > 5000 else n):          # short (live) frames are scanned to the last bar
        for side in (1, -1):
            if side > 0 and not (L[i] > H[i - 2] and C[i] > e200[i]):
                continue
            if side < 0 and not (H[i] < L[i - 2] and C[i] < e200[i]):
                continue
            top, bot = (L[i], H[i - 2]) if side > 0 else (L[i - 2], H[i])
            for j in range(i + 1, min(i + 13, n)):
                if side > 0 and C[j] < bot or side < 0 and C[j] > top:
                    break
                if (L[j] <= top) if side > 0 else (H[j] >= bot):
                    stop = L[i - 1] if side > 0 else H[i - 1]
                    Z.walk("S16 fair-value-gap retest", sym, df, j, side, stop, C[j] + 2 * (C[j] - stop), min(j + 24, n - 1))
                    break


def orb(sym, df):
    """S17/S18: first 15 minutes after the 09:30 New York open; first 15-minute close outside it before 11:00."""
    H, L, C = (df[k].values for k in ("high", "low", "close"))
    pos = pd.Series(np.arange(len(df)), index=df.index)
    for day, idx in pos.groupby(df.index.normalize()):
        t = idx.index
        r = idx[(t.hour == 9) & (t.minute == 30)]
        end = idx[(t.hour == 15) & (t.minute == 45)]
        if not len(r) or not len(end):
            continue
        r, end = int(r.iloc[0]), int(end.iloc[0])
        for i in idx[(t.hour * 60 + t.minute >= 585) & (t.hour * 60 + t.minute < 660)]:
            if C[i] > H[r] or C[i] < L[r]:
                s = 1 if C[i] > H[r] else -1
                stop = L[r] if s > 0 else H[r]
                Z.walk("S17 15-min ORB, small fixed target (the reel)", sym, df, i, s, stop, C[i] * (1 + s * 0.0004), end)
                Z.walk("S18 15-min ORB, 2R target", sym, df, i, s, stop, C[i] + 2 * (C[i] - stop), end)
                break


# ---------------------------------------------------------------- reporting
def stats(r):
    r = np.asarray(r, dtype=float)
    if not len(r):
        return {"n": 0, "win": 0, "avg": 0, "pf": 0, "tot": 0, "t": 0}
    g, l = r[r > 0].sum(), -r[r <= 0].sum()
    return {"n": len(r), "win": 100 * (r > 0).mean(), "avg": r.mean(), "pf": g / l if l else 0, "tot": r.sum(),
            "t": r.mean() / (r.std() / np.sqrt(len(r))) if len(r) > 2 and r.std() else 0}


def table(t, title, note=""):
    w(f"\n## {title}\n")
    if note:
        w(note + "\n")
    w("| Strategy | Trades | Win % | Avg R | PF 2021-24 | Years + | PF 2025-26 | Total R 2025-26 | t-stat 2025-26 | Picked on build | Held up |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    picked = held = 0
    for name, g in sorted(t.groupby("strat")):
        b, j = g[g["t_in"] < SPLIT], g[g["t_in"] >= SPLIT]
        sb, sj, sa = stats(b["R"]), stats(j["R"]), stats(g["R"])
        yrs = int((b.groupby(b["t_in"].dt.year)["R"].sum() > 0).sum())
        ok = sb["n"] >= 100 and sb["pf"] >= 1.10 and yrs >= 3
        picked += ok
        held += ok and sj["pf"] > 1.0
        w(f"| {name} | {sa['n']} | {sa['win']:.0f} | {sa['avg']:+.3f} | {sb['pf']:.2f} | {yrs}/4 | {sj['pf']:.2f} | {sj['tot']:+.0f} | {sj['t']:.1f} | "
          f"{'yes' if ok else ''} | {'yes' if ok and sj['pf'] > 1.0 else ''} |")
    w(f"\nPicked on 2021-24: **{picked}**. Held up on 2025-26: **{held}**.")


def run_zoo(data, fns):
    Z.TRADES.clear()
    for sym, df in data.items():
        for fn in fns:
            fn(sym, df)
    t = pd.DataFrame(Z.TRADES, columns=["strat", "sym", "t_in", "t_out", "side", "R"])
    return t[t["t_in"] >= "2021-01-01"].reset_index(drop=True)


def yearly(pnl, capital):
    y = pnl.groupby(pnl.index.year).sum() / capital * 100
    eq = pnl.cumsum()
    return y, float((eq - eq.cummax()).min() / capital * 100)


def main():
    w("# Sweep: everything set aside earlier, tested\n")
    w("Generated by `sweep.py`. R = multiples of the amount risked. Costs included everywhere. See `SWEEP_NOTES.md` for the reading.")

    # A crypto
    crypto = crypto_hourly()
    for s in crypto:
        Z.COST[s] = 0.0010                      # 0.045% taker each side on Hyperliquid plus slippage
        Z.FRAC.add(s)
    t = run_zoo(crypto, [Z.session, Z.hourly, Z.daily, fvg])
    table(t, "A. Crypto: BTC, ETH, SOL (hourly, 24x7)", "Round-trip cost 0.10% of price. Funding payments ignored.")

    # B FVG on the prop markets
    prop = {s: df[df.index.dayofweek < 5] for s, df in pickle.load(open(DATA / "prop_cache.pkl", "rb")).items()}
    table(run_zoo(prop, [fvg]), "B. Fair-value-gap retest (ICT), forex + gold + US indices")

    # C ORB
    idx15 = {"US500": index_15m("spxusd"), "NAS100": index_15m("nsxusd")}
    table(run_zoo(idx15, [orb]), "C. 15-minute opening-range breakout at the New York open",
          "S17 is the reel's version: bank a small fixed profit (0.04% of the index, the same proportion as 10 NIFTY points).")

    # D S12 long history
    tick = {"US500": "^GSPC", "NAS100": "^NDX", "XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
            "AUDUSD": "AUDUSD=X"}
    raw = yahoo_daily(tick.values())
    Z.TRADES.clear()
    for sym, tk in tick.items():
        d = pd.DataFrame({k: raw[k.capitalize()][tk] for k in ("open", "high", "low", "close")}).dropna()
        d = d[(d["high"] > d["low"]) & (d.index.dayofweek < 5)]
        Z.daily_strats(sym, d)
    t = pd.DataFrame(Z.TRADES, columns=["strat", "sym", "t_in", "t_out", "side", "R"])
    t = t[t["strat"].str.startswith("S12")]
    w("\n## D. The surviving daily RSI-2 pullback on all free daily history\n")
    w("Daily bars from Yahoo (cash indices, gold futures, spot forex). Same rule, same costs.\n")
    w("| Period | Trades | Win % | Avg R | PF | Total R | t-stat | Indices only: trades / PF | Forex + gold only: trades / PF |")
    w("|---|---|---|---|---|---|---|---|---|")
    for a, b in (("1990", "1999"), ("2000", "2009"), ("2010", "2020"), ("2021", "2024"), ("2025", "2026"), ("1990", "2026")):
        g = t[(t["t_in"] >= f"{a}-01-01") & (t["t_in"] <= f"{b}-12-31")]
        s, si, sf = stats(g["R"]), stats(g[g["sym"].isin(["US500", "NAS100"])]["R"]), stats(g[~g["sym"].isin(["US500", "NAS100"])]["R"])
        w(f"| {a}-{b} | {s['n']} | {s['win']:.0f} | {s['avg']:+.3f} | {s['pf']:.2f} | {s['tot']:+.0f} | {s['t']:.1f} | "
          f"{si['n']} / {si['pf']:.2f} | {sf['n']} / {sf['pf']:.2f} |")
    w("\nBy side, whole history: " + ", ".join(
        f"{lab} {stats(g['R'])['n']} trades PF {stats(g['R'])['pf']:.2f}" for lab, g in (("longs", t[t['side'] > 0]), ("shorts", t[t['side'] < 0]))) + ".")

    # E US pairs
    us = ["KO", "PEP", "XOM", "CVX", "V", "MA", "HD", "LOW", "JPM", "BAC", "GS", "MS", "WMT", "TGT", "UPS", "FDX", "PG", "CL", "MRK",
          "PFE", "T", "VZ", "CSCO", "INTC", "MCD", "YUM", "UNH", "CI", "BA", "LMT", "C", "WFC", "COP", "OXY", "DUK", "SO", "MO", "PM",
          "AXP", "COF"]
    px = yahoo_daily(us, start="2018-06-01")["Close"].dropna(axis=1, thresh=1500).ffill()
    pnl = zoo_daily.pairs(px)
    y, dd = yearly(pnl[pnl.index >= "2021-01-01"], zoo_daily.CAPITAL)
    w("\n## E. Pairs trading on 40 US large caps (the reel's rule, 15 pairs re-picked each January)\n")
    w("| " + " | ".join(str(k) for k in y.index) + " | Average a year | Max drawdown |")
    w("|" + "---|" * (len(y) + 2))
    w("| " + " | ".join(f"{v:+.1f}%" for v in y) + f" | {y.mean():+.1f}% | {dd:.1f}% |")
    w("\nReturn on per-side capital, 0.05% a side per leg. Needs shorting (CFDs or margin).")

    # F rotation, long history
    w("\n## F. Index-or-gold rotation on all available history\n")
    w("Month-end rule from the Indian study: hold whichever of index and gold has the better 12-month return, cash if both are negative.\n")
    w("| Market | Years | Rotation a year | Buy-and-hold index a year | Rotation max drawdown | Index max drawdown | Years rotation beat the index |")
    w("|---|---|---|---|---|---|---|")
    for label, a, g_, cost in (("India: NIFTY ETF / gold ETF", "NIFTYBEES.NS", "GOLDBEES.NS", 0.0018), ("US: SPY / GLD", "SPY", "GLD", 0.0005)):
        p = yahoo_daily([a, g_], start="2004-01-01")["Close"].dropna()
        r_ = p.pct_change().fillna(0)
        r_ = r_.where(r_.abs() < 0.15, 0)            # Yahoo has bad ticks and unadjusted splits in the Indian ETFs
        p = (1 + r_).cumprod()
        n, g = p[a], p[g_]
        mom_n, mom_g = n / n.shift(252) - 1, g / g.shift(252) - 1
        month_end = set(n.index.to_series().groupby(n.index.to_period("M")).max())
        cur, rows = (0.0, 0.0), []
        for d in n.index:
            if d in month_end and mom_n[d] == mom_n[d]:
                cur = (1.0, 0.0) if (mom_n[d] >= mom_g[d] and mom_n[d] > 0) else (0.0, 1.0) if mom_g[d] > 0 else (0.0, 0.0)
            rows.append(cur)
        pos = pd.DataFrame(rows, index=n.index, columns=["n", "g"])
        start = n.index[252]
        rot = (zoo_daily.book(pos.n, n.pct_change(), cost) + zoo_daily.book(pos.g, g.pct_change(), cost))[start:]
        bh = zoo_daily.book(pd.Series(1.0, index=n.index), n.pct_change(), cost)[start:]
        (yr, ddr), (yb, ddb) = yearly(rot, zoo_daily.CAPITAL), yearly(bh, zoo_daily.CAPITAL)
        w(f"| {label} | {yr.index[0]}-{yr.index[-1]} | {yr.mean():+.1f}% | {yb.mean():+.1f}% | {ddr:.0f}% | {ddb:.0f}% | {int((yr > yb).sum())} of {len(yr)} |")
        for lab, lo, hi in (("to 2020", 1900, 2020), ("2021 on", 2021, 2100)):
            m = (yr.index >= lo) & (yr.index <= hi)
            w(f"| &nbsp;&nbsp;{lab} | | {yr[m].mean():+.1f}% | {yb[m].mean():+.1f}% | | | {int((yr[m] > yb[m]).sum())} of {int(m.sum())} |")
    w("\nSimple (not compounded) yearly returns on fixed capital, costs on every switch.")

    # G copycat
    w("\n## G. Copy the investor (the trader-skill repo's idea)\n")
    w("| What | Period | Total return | S&P 500 ETF, same period |")
    w("|---|---|---|---|")
    p = yahoo_daily(["BRK-B", "NANC", "KRUZ", "SPY"], start="2005-01-01")["Close"]
    for label, tk, start in (("Berkshire Hathaway itself", "BRK-B", "2005-01-01"), ("Berkshire, last 10 years", "BRK-B", "2016-11-01"),
                             ("Congress Democrats' trades ETF (NANC)", "NANC", "2023-02-10"), ("Congress Republicans' trades ETF (KRUZ)", "KRUZ", "2023-02-10")):
        q = p[[tk, "SPY"]].dropna()
        q = q[q.index >= start]
        if q.empty:
            w(f"| {label} | no longer listed on Yahoo | | |")
            continue
        w(f"| {label} | {q.index[0].date()} to {q.index[-1].date()} | {100 * (q[tk].iloc[-1] / q[tk].iloc[0] - 1):+.0f}% | "
          f"{100 * (q['SPY'].iloc[-1] / q['SPY'].iloc[0] - 1):+.0f}% |")
    w("\nDividends included. The two Congress ETFs copy disclosed trades after the filing delay, which is what the skill would do.")

    (ROOT / "research" / "SWEEP_RESULTS.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
