"""Self-learning decision engine, research half: can a model that has seen thousands of logged trades tell
the good ones from the bad ones BEFORE they happen?

Every candidate trade from the rule zoo (16 rules x 10 markets, about 100,000 trades) is logged with the market
state at entry: trend, volatility, recent move, where price sits in its range, time of day, and how that rule has
been doing lately on that market (the system's own previous state). A gradient-boosted model learns expected R
from that log. Walk-forward only: to decide trades in year Y it is trained on trades that closed before year Y.

Decision rule, fixed before any result: take a trade when the model expects more than +0.05R.
Pass mark on the unseen 2025-2026 decisions: at least 300 trades, profit factor >= 1.15, t-statistic >= 2.

Writes data/learn_log.pkl (the full decision log) and research/LEARN_RESULTS.md.
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import prop_zoo as Z, sweep  # noqa: E402

DATA = ROOT / "data"
EDGE = 0.05
FEATS = ["strat_id", "sym_id", "cls", "side", "hour", "dow", "vol", "vol_ratio", "trend200", "trend50", "slope50", "ret24", "ret120",
         "pos20d", "rsi", "a_trend200", "a_trend50", "a_slope50", "a_ret24", "a_ret120", "a_pos", "prior50", "prior_strat", "prior_n"]
DAILY = ("S10", "S11", "S12")
CLS = {"EURUSD": 0, "GBPUSD": 0, "USDJPY": 0, "AUDUSD": 0, "XAUUSD": 1, "US500": 2, "NAS100": 2, "BTCUSD": 3, "ETHUSD": 3, "SOLUSD": 3}


def market_state(df):
    """Hourly features, each known at the close of its own bar."""
    c = df["close"]
    a = Z.atr(df)
    e200, e50 = c.ewm(span=200, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    hi, lo = df["high"].rolling(480).max(), df["low"].rolling(480).min()
    f = pd.DataFrame({"vol": a / c, "vol_ratio": a / a.rolling(480).mean(), "trend200": (c - e200) / a, "trend50": (c - e50) / a,
                      "slope50": (e50 - e50.shift(24)) / a, "ret24": (c - c.shift(24)) / a, "ret120": (c - c.shift(120)) / a,
                      "pos20d": (c - lo) / (hi - lo), "rsi": Z.rsi(c, 14)}, index=df.index)
    return f


def add_state(t, data):
    out = []
    for sym, g in t.groupby("sym"):
        f = market_state(data[sym]).reset_index(names="bar")
        f["bar"] = f["bar"].astype("datetime64[ns]")
        g = g.copy()
        daily = g["strat"].str[:3].isin(DAILY)
        g["asof"] = g["t_in"] + pd.to_timedelta(np.where(daily, 23, 0), unit="h")     # a daily entry is at that day's last bar
        g["asof"] = g["asof"].astype("datetime64[ns]")
        g = pd.merge_asof(g.sort_values("asof"), f, left_on="asof", right_on="bar", direction="backward")
        out.append(g)
    t = pd.concat(out, ignore_index=True)
    t["hour"], t["dow"] = t["t_in"].dt.hour, t["t_in"].dt.dayofweek
    for k in ("trend200", "trend50", "slope50", "ret24", "ret120"):
        t["a_" + k] = t[k] * t["side"]                     # the same thing seen from the trade's side
    t["a_pos"] = np.where(t["side"] > 0, t["pos20d"], 1 - t["pos20d"])
    return t


def add_previous_state(t):
    """How has this rule been doing, using only trades that had CLOSED before this entry."""
    t = t.sort_values("t_in").reset_index(drop=True)
    t["t_in"], t["t_out"] = t["t_in"].astype("datetime64[ns]"), t["t_out"].astype("datetime64[ns]")
    t["prior50"], t["prior_strat"], t["prior_n"] = np.nan, np.nan, 0.0
    for keys, col, n in ((["strat", "sym"], "prior50", 50), (["strat"], "prior_strat", 300)):
        for _, g in t.groupby(keys):
            done = g.sort_values("t_out")
            roll = pd.DataFrame({"t_out": done["t_out"].values, "v": done["R"].rolling(n, min_periods=10).mean().values,
                                 "k": np.arange(1, len(done) + 1)})
            m = pd.merge_asof(g[["t_in"]].reset_index(), roll, left_on="t_in", right_on="t_out", direction="backward",
                              allow_exact_matches=False).set_index("index")
            t.loc[m.index, col] = m["v"]
            if col == "prior50":
                t.loc[m.index, "prior_n"] = m["k"].fillna(0)
    return t


def build_log():
    cache = DATA / "learn_log.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    prop = {s: df[df.index.dayofweek < 5] for s, df in pickle.load(open(DATA / "prop_cache.pkl", "rb")).items()}
    crypto = sweep.crypto_hourly()
    for s in crypto:
        Z.COST[s] = 0.0010
        Z.FRAC.add(s)
    fns = [Z.session, Z.hourly, Z.daily, sweep.fvg]
    t = pd.concat([sweep.run_zoo(prop, fns), sweep.run_zoo(crypto, fns)], ignore_index=True)
    t = add_previous_state(add_state(t, {**prop, **crypto}))
    t["strat_id"] = t["strat"].str[1:3].astype(int)
    t["sym_id"] = t["sym"].map({s: i for i, s in enumerate(CLS)})
    t["cls"] = t["sym"].map(CLS)
    t.to_pickle(cache)
    return t


def model():
    return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=200, min_samples_leaf=300, l2_regularization=1.0,
                                         categorical_features=[0, 1, 2], random_state=7)


def stats(r):
    r = np.asarray(r, dtype=float)
    if len(r) < 3:
        return {"n": len(r), "avg": 0, "pf": 0, "t": 0, "tot": float(r.sum()) if len(r) else 0}
    g, l = r[r > 0].sum(), -r[r <= 0].sum()
    return {"n": len(r), "avg": r.mean(), "pf": g / l if l else 0, "t": r.mean() / (r.std() / np.sqrt(len(r))), "tot": r.sum()}


def walk_forward(t, years=(2023, 2024, 2025, 2026)):
    t = t.copy()
    t["pred"] = np.nan
    for y in years:
        cut = pd.Timestamp(f"{y}-01-01")
        tr = t[t["t_out"] < cut]
        te = t[(t["t_in"] >= cut) & (t["t_in"] < cut + pd.DateOffset(years=1))]
        m = model().fit(tr[FEATS], tr["R"].clip(-3, 5))
        t.loc[te.index, "pred"] = m.predict(te[FEATS])
    return t


def main():
    t = build_log()
    out = []
    w = out.append
    w("# Self-learning decision engine: does the log teach it anything?\n")
    w(f"Generated by `learn.py`. Decision log: **{len(t):,} trades**, {t['strat'].nunique()} rules, {t['sym'].nunique()} markets, "
      f"{t['t_in'].min().date()} to {t['t_in'].max().date()}, each with {len(FEATS)} facts about the market and the rule's own recent record. "
      "The model deciding year Y has only seen trades that closed before year Y.\n")
    t = walk_forward(t)
    d = t.dropna(subset=["pred"])
    w("## 1. Taking every trade vs taking only what the model expects to pay (> +0.05R)\n")
    w("| Year decided | All trades: n / avg R / PF | Model's picks: n / avg R / PF / t-stat / total R | Share taken |")
    w("|---|---|---|---|")
    for y, g in list(d.groupby(d["t_in"].dt.year)) + [("2025-26 (the judge)", d[d["t_in"] >= "2025-01-01"]), ("2023-26", d)]:
        a, p = stats(g["R"]), stats(g[g["pred"] > EDGE]["R"])
        w(f"| {y} | {a['n']} / {a['avg']:+.3f} / {a['pf']:.2f} | {p['n']} / {p['avg']:+.3f} / {p['pf']:.2f} / {p['t']:.1f} / {p['tot']:+.0f} | "
          f"{100 * p['n'] / max(a['n'], 1):.0f}% |")
    j = stats(d[(d["t_in"] >= "2025-01-01") & (d["pred"] > EDGE)]["R"])
    ok = j["n"] >= 300 and j["pf"] >= 1.15 and j["t"] >= 2
    w(f"\nPass mark (300 trades, PF 1.15, t 2 on 2025-26): **{'PASSED' if ok else 'NOT PASSED'}** "
      f"({j['n']} trades, PF {j['pf']:.2f}, t {j['t']:.1f}).\n")

    w("## 2. Does a higher score mean a better trade? (2025-26, model never saw these)\n")
    w("| Model score band | Trades | Avg R | PF |")
    w("|---|---|---|---|")
    jd = d[d["t_in"] >= "2025-01-01"].copy()
    jd["band"] = pd.qcut(jd["pred"], 10, labels=False, duplicates="drop")
    for b, g in jd.groupby("band"):
        s = stats(g["R"])
        w(f"| {int(b) + 1} of 10 ({g['pred'].min():+.2f} to {g['pred'].max():+.2f}R expected) | {s['n']} | {s['avg']:+.3f} | {s['pf']:.2f} |")

    w("\n## 3. Where the model's 2025-26 picks came from\n")
    w("| Rule | Market group | Picks | Avg R | PF |")
    w("|---|---|---|---|---|")
    names = {0: "forex", 1: "gold", 2: "US indices", 3: "crypto"}
    pk = jd[jd["pred"] > EDGE]
    for (s_, c_), g in sorted(pk.groupby(["strat", "cls"]), key=lambda kv: -len(kv[1]))[:12]:
        s = stats(g["R"])
        w(f"| {s_} | {names[c_]} | {s['n']} | {s['avg']:+.3f} | {s['pf']:.2f} |")

    w("\n## 4. What it leans on\n")
    m = model().fit(t[t["t_out"] < "2025-01-01"][FEATS], t[t["t_out"] < "2025-01-01"]["R"].clip(-3, 5))
    base = jd[FEATS].copy()
    ref = np.corrcoef(m.predict(base), jd["R"])[0, 1]
    rng = np.random.default_rng(7)
    imp = []
    for f in FEATS:
        x = base.copy()
        x[f] = rng.permutation(x[f].values)
        imp.append((float(np.abs(m.predict(base) - m.predict(x)).mean()), f))
    w("Average change in the score when one input is scrambled (bigger = leaned on more): "
      + ", ".join(f"{f} {v:.3f}" for v, f in sorted(imp, reverse=True)[:8]) + f". Score-to-outcome correlation on 2025-26: {ref:+.3f}.")
    (ROOT / "research" / "LEARN_RESULTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
