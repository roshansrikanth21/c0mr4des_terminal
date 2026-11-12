"""Two checks the gated learning engine had not faced.

A. Holding costs. The replay charged spread and commission but not financing. Here every trade also pays for the
   time it was held: crypto longs 0.03% a day (perp funding), index and gold longs 0.02% a day, index shorts and
   all forex 0.005% a day. Shorts in crypto and gold are charged nothing (they usually receive).
B. Markets it has never seen. The engine, trained only on the original ten markets, is run frozen on thirteen new
   ones (three forex majors, two yen crosses, silver, three foreign indices, four more coins). The market gate is
   the one the original replay produced, month by month. Nothing is fitted, chosen or tuned on the new markets.
   Pass mark, set before running: 300 trades, profit factor >= 1.15, t >= 2 over 2024-2026, financing included.

Writes research/LEARN_TRANSFER_RESULTS.md.
"""
import io
import pickle
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import learn, learn_online, prop_data, prop_zoo as Z, sweep  # noqa: E402

DATA = ROOT / "data"
NEW_HD = {"USDCAD": ("usdcad", 0.00014, 0), "NZDUSD": ("nzdusd", 0.00014, 0), "USDCHF": ("usdchf", 0.00014, 0),
          "EURJPY": ("eurjpy", 0.020, 0), "GBPJPY": ("gbpjpy", 0.030, 0), "XAGUSD": ("xagusd", 0.03, 1),
          "GER40": ("grxeur", 2.0, 2), "UK100": ("ukxgbp", 1.5, 2), "JPN225": ("jpxjpy", 10.0, 2)}
NEW_CR = {"BNBUSD": "BNBUSDT", "XRPUSD": "XRPUSDT", "ADAUSD": "ADAUSDT", "DOGEUSD": "DOGEUSDT"}
FIN = {0: (0.00005, 0.00005), 1: (0.0002, 0.0), 2: (0.0002, 0.00005), 3: (0.0003, 0.0)}      # per day: (long, short) by group


def record_with_extra(strat, sym, df, i, j, side, entry, exit_, risk):
    Z.TRADES.append((strat, sym, df.index[i], df.index[j], side, (side * (exit_ - entry) - Z.cost(sym, entry)) / risk))
    EXTRA.append(entry / risk)


EXTRA = []


def zoo(data):
    """Run all 16 rules; also keep price/risk for each trade so a holding cost can be charged."""
    Z.TRADES.clear()
    EXTRA.clear()
    old = Z.record
    Z.record = record_with_extra
    try:
        for sym, df in data.items():
            for fn in (Z.session, Z.hourly, Z.daily, sweep.fvg):
                fn(sym, df)
    finally:
        Z.record = old
    t = pd.DataFrame(Z.TRADES, columns=["strat", "sym", "t_in", "t_out", "side", "R"])
    t["px_risk"] = EXTRA
    return t[t["t_in"] >= "2021-01-01"].reset_index(drop=True)


def financed(t):
    days = (t["t_out"] - t["t_in"]).dt.total_seconds() / 86400
    rate = np.where(t["side"] > 0, t["cls"].map(lambda c: FIN[c][0]), t["cls"].map(lambda c: FIN[c][1]))
    return t["R"] - rate * days * t["px_risk"]


def new_markets():
    cache = DATA / "transfer_cache.pkl"
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    out = {}
    for sym, (pair, _, _) in NEW_HD.items():
        files = [prop_data.fetch(pair, y) for y in prop_data.YEARS] + [prop_data.fetch(pair, prop_data.THIS_YEAR, m) for m in prop_data.MONTHS]
        m1 = pd.concat([prop_data.read(f) for f in files if f]).sort_index()
        m1 = m1[~m1.index.duplicated()]
        h = m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        out[sym] = h[h.index.dayofweek < 5]
        print(sym, sum(f is not None for f in files), "files", len(out[sym]), "hours", flush=True)
    for sym, pair in NEW_CR.items():
        frames = []
        for y in range(2020, 2027):
            for m in range(1, 13):
                if (y, m) > (2026, 10):
                    continue
                try:
                    url = f"https://data.binance.vision/data/spot/monthly/klines/{pair}/1h/{pair}-1h-{y}-{m:02d}.zip"
                    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=40).read()))
                except Exception:  # noqa: BLE001
                    continue
                df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), header=None, usecols=[0, 1, 2, 3, 4],
                                 names=["t", "open", "high", "low", "close"])
                df = df[pd.to_numeric(df["t"], errors="coerce").notna()].astype(float)
                df.index = pd.to_datetime(df["t"].where(df["t"] < 1e14, df["t"] / 1000), unit="ms")
                frames.append(df[["open", "high", "low", "close"]])
        out[sym] = pd.concat(frames).sort_index()
        print(sym, len(out[sym]), "hours", flush=True)
    pickle.dump(out, open(cache, "wb"))
    return out


def line(w, lab, r):
    s = learn.stats(r)
    w(f"| {lab} | {s['n']} | {100 * (np.asarray(r) > 0).mean() if s['n'] else 0:.0f} | {s['avg']:+.3f} | {s['pf']:.2f} | {s['t']:.1f} | {s['tot']:+.0f} |")


def money(w, p, col):
    e = learn_online.equity(p.assign(R=p[col]))
    w(f"\nAt {learn_online.RISK}% risk a trade: {e['per_year']:+.1f}% a year, worst drawdown {e['dd']:.1f}%, "
      f"{e['months_up']} of {e['months']} months up, worst month {e['worst_month']:+.1f}%.")


def main():
    out = []
    w = out.append
    w("# Learning engine: holding costs, and markets it has never seen\n")
    w("Generated by `learn_transfer.py`.\n")
    head = "| | Trades | Win % | Avg R | PF | t-stat | Total R |\n|---|---|---|---|---|---|---|"

    # ---- A. financing on the original replay
    base = learn.build_log()
    replay = learn_online.replay(base)
    prop = {s: df[df.index.dayofweek < 5] for s, df in pickle.load(open(DATA / "prop_cache.pkl", "rb")).items()}
    crypto = sweep.crypto_hourly()
    for s in crypto:
        Z.COST[s] = 0.0010
        Z.FRAC.add(s)
    ex = zoo({**prop, **crypto})[["strat", "sym", "t_in", "px_risk"]].drop_duplicates(["strat", "sym", "t_in"])
    ex["t_in"] = ex["t_in"].astype("datetime64[ns]")
    replay = replay.merge(ex, on=["strat", "sym", "t_in"], how="left")
    replay["px_risk"] = replay["px_risk"].fillna(replay["px_risk"].median())
    replay["Rf"] = financed(replay)
    picks = replay[replay["pred"] > 0.05]
    kept, hist = learn_online.gated(picks)
    w("## A. The gated engine on its original ten markets, with holding costs charged\n")
    w(head)
    for lab, g in (("2025-26, as reported before", kept[kept["t_in"] >= "2025-01-01"]["R"]),
                   ("2025-26, financing charged", kept[kept["t_in"] >= "2025-01-01"]["Rf"]),
                   ("2024-26, financing charged", kept["Rf"])):
        line(w, lab, g)
    money(w, kept, "Rf")
    w(f"\nAverage holding cost per taken trade: {(kept['R'] - kept['Rf']).mean():.3f}R (average hold "
      f"{((kept['t_out'] - kept['t_in']).dt.total_seconds() / 86400).mean():.1f} days).")

    # ---- B. transfer to unseen markets
    new = new_markets()
    for sym, (_, c, _) in NEW_HD.items():
        Z.COST[sym] = c
    for sym in NEW_CR:
        Z.COST[sym] = 0.0010
        Z.FRAC.add(sym)
    cls = {**{s: v[2] for s, v in NEW_HD.items()}, **{s: 3 for s in NEW_CR}}
    t = zoo(new)
    t = learn.add_previous_state(learn.add_state(t, new))        # px_risk rides along as a column
    t["strat_id"], t["sym_id"], t["cls"] = t["strat"].str[1:3].astype(int), np.nan, t["sym"].map(cls)
    t["pred"] = np.nan
    allowed = dict(hist)
    t["ok"] = False
    for start in pd.date_range("2024-01-01", t["t_in"].max(), freq="MS"):
        te = t[(t["t_in"] >= start) & (t["t_in"] < start + pd.DateOffset(months=1))]
        if not len(te):
            continue
        tr = base[base["t_out"] < start]                                    # original markets only
        m = learn.model().fit(tr[learn.FEATS], tr["R"].clip(-3, 5))
        t.loc[te.index, "pred"] = m.predict(te[learn.FEATS])
        t.loc[te.index, "ok"] = te["cls"].isin(allowed.get(str(start.date())[:7], []))
        print("transfer", start.date(), len(te), flush=True)
    d = t.dropna(subset=["pred"]).copy()
    d["Rf"] = financed(d)
    eng = d[(d["pred"] > 0.05) & d["ok"]]
    w(f"\n## B. The same engine, frozen, on thirteen markets it never saw (2024-2026)\n")
    w(f"{', '.join(new)}. {len(d):,} ideas scored; the model was trained only on the original ten markets, and the market gate is the "
      "original replay's.\n")
    w(head)
    line(w, "Every idea, no engine (financing charged)", d["Rf"])
    line(w, "Engine's picks, before financing", eng["R"])
    line(w, "**Engine's picks, financing charged**", eng["Rf"])
    for y in (2024, 2025, 2026):
        line(w, f"&nbsp;&nbsp;{y}", eng[eng["t_in"].dt.year == y]["Rf"])
    names = learn_online.NAMES
    for c in sorted(eng["cls"].unique()):
        line(w, f"&nbsp;&nbsp;{names[c]} only", eng[eng["cls"] == c]["Rf"])
    s = learn.stats(eng["Rf"])
    ok = s["n"] >= 300 and s["pf"] >= 1.15 and s["t"] >= 2
    w(f"\nPass mark (300 trades, PF 1.15, t 2, financing included): **{'PASSED' if ok else 'NOT PASSED'}** "
      f"({s['n']} trades, PF {s['pf']:.2f}, t {s['t']:.1f}).")
    if len(eng):
        money(w, eng, "Rf")

    both = pd.concat([kept[["t_in", "t_out", "Rf"]], eng[["t_in", "t_out", "Rf"]]])
    w("\n## C. Both together: all 23 markets, 2024-2026, financing charged\n")
    w(head)
    line(w, "Engine's picks", both["Rf"])
    money(w, both, "Rf")
    (ROOT / "research" / "LEARN_TRANSFER_RESULTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
