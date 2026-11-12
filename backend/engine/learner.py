"""Self-learning decision engine, live half. PAPER ONLY: no broker, no account, no order.

Every hour it:
  1. pulls hourly prices for ten markets (forex, gold, US indices, crypto) from Yahoo,
  2. runs the 16 research rules (research/prop_zoo.py + the fair-value-gap rule) to find every NEW trade idea,
  3. writes each idea to the decision log with the market state at that moment (trend, volatility, recent move,
     place in range, time, and how that rule has been doing lately on that market),
  4. scores it with the model and decides: TAKE when the model expects more than +0.05R, otherwise SKIP,
     and writes down why (the facts that moved the score most),
  5. looks up how earlier ideas ended, taken AND skipped, and writes the outcome next to the decision.
Once a week the model is retrained on the research log (about 120,000 past trades) plus everything it has
logged itself, so its own results feed its next decisions.

Research verdict it starts from (research/LEARN_RESULTS.md): on unseen 2025-26 trades the model's picks had
profit factor 1.06 against 0.89 for taking everything. Better, not yet proven. This engine is the forward test.

Run as a subprocess (`python -m backend.engine.learner`) so the heavy work never blocks the main loop;
it prints one JSON line of events. `report()` only reads the state file and is safe to call from the app.
"""
from __future__ import annotations

import json
import logging
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("learner")
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STATE_FILE, LOG_FILE, MODEL_FILE, BASE_LOG = (DATA_DIR / n for n in
                                              ("learner_state.json", "learner_log.jsonl", "learner_model.pkl", "learn_log.pkl"))
MARKETS = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X", "AUDUSD": "AUDUSD=X", "XAUUSD": "GC=F", "US500": "ES=F",
           "NAS100": "NQ=F", "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD"}
CRYPTO = ("BTCUSD", "ETHUSD", "SOLUSD")
RULES = {"version": 1, "take_above_R": 0.05, "retrain_days": 7, "fresh_hours": 3, "need_taken": 200, "account": 100_000, "risk_pct": 0.5}
LABELS = {"strat_id": "which rule it is", "sym_id": "which market it is", "cls": "the market group", "hour": "time of day",
          "dow": "day of week", "vol": "how volatile the market is", "vol_ratio": "volatility vs its last 20 days",
          "a_trend200": "trade direction vs the 200-hour trend", "a_trend50": "trade direction vs the 50-hour trend",
          "a_slope50": "trade direction vs the trend's slope", "a_ret24": "trade direction vs the last day's move",
          "a_ret120": "trade direction vs the last week's move", "a_pos": "where price sits in its 20-day range",
          "rsi": "hourly RSI", "prior50": "this rule's last 50 trades on this market", "prior_strat": "this rule's last 300 trades overall",
          "prior_n": "how much history this rule has here", "side": "long or short"}


def _empty() -> dict:
    return {"version": RULES["version"], "started": None, "last_tick": None, "seen": {}, "pending": {}, "closed": [],
            "model": None, "ticks": 0}


def load_state(path: Path = STATE_FILE) -> dict:
    st = _empty()
    if path.exists():
        try:
            st.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            log.exception("learner state unreadable, starting empty")
    return st


def _save(st: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st), encoding="utf-8")
    tmp.replace(path)


def _journal(row: dict, path: Path = LOG_FILE) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0, "avg_R": None, "total_R": 0.0, "win_rate": None, "profit_factor": None}
    g, l = sum(r for r in rs if r > 0), -sum(r for r in rs if r <= 0)
    return {"n": len(rs), "avg_R": round(sum(rs) / len(rs), 3), "total_R": round(sum(rs), 2),
            "win_rate": round(100 * sum(r > 0 for r in rs) / len(rs), 1), "profit_factor": round(g / l, 2) if l else None}


def report(path: Path = STATE_FILE) -> dict:
    st = load_state(path)
    closed = st["closed"]
    taken, skipped = [c["R"] for c in closed if c["take"]], [c["R"] for c in closed if not c["take"]]
    pend = list(st["pending"].values())
    return {"paper_only": True, "rules": RULES, "markets": list(MARKETS), "started": st["started"], "last_tick": st["last_tick"],
            "ticks": st["ticks"], "model": st["model"],
            "decisions_logged": len(closed) + len(pend),
            "open_taken": [p for p in pend if p["take"]], "open_skipped": sum(not p["take"] for p in pend),
            "taken": _stats(taken), "skipped": _stats(skipped), "need_taken": RULES["need_taken"],
            "recent": closed[-30:],
            "research": {"judge_2025_26": {"model_picks_pf": 1.06, "all_trades_pf": 0.89, "t_stat": 0.8}, "passed": False},
            "reading": "The model earns its keep only if 'taken' ends clearly better than 'skipped' and above zero."}


# ------------------------------------------------------------------ the hourly tick (heavy imports stay inside)
def train(base, live_rows: list[dict], feats, model_fn) -> dict:
    import pandas as pd
    frames = [base[feats + ["R"]]] if base is not None else []
    if live_rows:
        frames.append(pd.DataFrame([{**r["features"], "R": r["R"]} for r in live_rows])[feats + ["R"]])
    d = pd.concat(frames, ignore_index=True)
    m = model_fn().fit(d[feats], d["R"].clip(-3, 5))
    return {"model": m, "medians": d[feats].median().to_dict(), "feats": feats, "trained_at": datetime.now(timezone.utc).isoformat(),
            "rows": int(len(d)), "live_rows": len(live_rows)}


def explain(bundle: dict, row) -> list[str]:
    """Which facts moved this score most: swap each for its usual value and see how far the score moves."""
    import pandas as pd
    x = pd.DataFrame([row[bundle["feats"]].astype(float)])
    base = float(bundle["model"].predict(x)[0])
    moves = []
    for f in bundle["feats"]:
        if f not in LABELS:
            continue
        y = x.copy()
        y[f] = bundle["medians"][f]
        moves.append((base - float(bundle["model"].predict(y)[0]), f))
    return [f"{LABELS[f]} ({'helps' if d > 0 else 'hurts'} {abs(d):.2f}R)" for d, f in sorted(moves, key=lambda m: -abs(m[0]))[:3]]


def tick(now: datetime | None = None, fetch=None, state_path: Path = STATE_FILE, log_path: Path = LOG_FILE,
         model_path: Path = MODEL_FILE, base_path: Path = BASE_LOG) -> dict:
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(ROOT))
    from research import learn, prop_zoo as Z, sweep
    if fetch is None:
        from .propbook import _yahoo_hourly as fetch

    now = now or datetime.now(timezone.utc)
    st = load_state(state_path)
    this_hour = pd.Timestamp(now.replace(tzinfo=None)).floor("1h")
    data = {}
    for sym, tk in MARKETS.items():
        h = fetch(tk)
        if h is None or len(h) < 24 * 250:
            continue
        h = h[h.index < this_hour]                                  # drop the bar still forming
        data[sym] = h if sym in CRYPTO else h[h.index.dayofweek < 5]
    if not data:
        return {"events": [], "note": "no data"}

    for s in CRYPTO:
        Z.COST[s] = 0.0010
        Z.FRAC.add(s)
    Z.TRADES.clear(); Z.OPEN.clear()
    Z.DAY_BARS = 1
    try:
        for sym, df in data.items():
            Z.session(sym, df)
            Z.hourly(sym, df)
            Z.daily(sym, df[df.index < this_hour.normalize()])      # daily rules only see completed UTC days
            sweep.fvg(sym, df)
    finally:
        Z.DAY_BARS = 18
    t = pd.DataFrame(Z.TRADES, columns=["strat", "sym", "t_in", "t_out", "side", "R"])
    o = pd.DataFrame([(a, b, c, pd.Timestamp("2200-01-01"), d, np.nan) for a, b, c, d in Z.OPEN], columns=t.columns)
    end = {s: df.index[-1] for s, df in data.items()}
    t["final"] = t["t_out"] < t["sym"].map(end)                     # an exit on the very last bar may just be "data ran out"
    t.loc[t["strat"].str[:3].isin(("S06", "S07", "S08", "S09") + learn.DAILY), "final"] = True     # these rules only record real exits
    o["final"] = False
    allt = pd.concat([t, o], ignore_index=True)
    allt["R_known"] = allt["R"].where(allt["final"])
    work = allt.assign(R=allt["R_known"])
    work = learn.add_previous_state(learn.add_state(work, data))
    work["strat_id"] = work["strat"].str[1:3].astype(int)
    work["sym_id"] = work["sym"].map({s: i for i, s in enumerate(learn.CLS)})
    work["cls"] = work["sym"].map(learn.CLS)
    work["key"] = work["strat"].str[:3] + "|" + work["sym"] + "|" + work["t_in"].dt.strftime("%Y-%m-%dT%H")

    events = []
    # 5. outcomes of earlier decisions, taken and skipped
    done = work[work["final"]].drop_duplicates("key").set_index("key")
    for key in list(st["pending"]):
        p = st["pending"][key]
        if key in done.index:
            row = done.loc[key]
            c = {**p, "R": round(float(row["R_known"]), 4), "closed_at": str(row["t_out"])}
            st["closed"].append(c)
            del st["pending"][key]
            _journal({"event": "outcome", "at": now.isoformat(), "key": key, "take": p["take"], "R": c["R"], "closed_at": c["closed_at"]},
                     log_path)
            if p["take"]:
                dollars = c["R"] * RULES["account"] * RULES["risk_pct"] / 100
                tk = _stats([x["R"] for x in st["closed"] if x["take"]])
                events.append({"type": "learner_exit", "text": f"LEARNER (paper): closed {p['strat']} {p['sym']} "
                               f"{'long' if p['side'] > 0 else 'short'}: {c['R']:+.2f}R = ${dollars:+,.0f}. "
                               f"Taken so far: {tk['n']} trades, {tk['total_R']:+.1f}R. No real order."})
        elif pd.Timestamp(p["entry_bar"]) < this_hour - pd.Timedelta(days=20):
            del st["pending"][key]
            _journal({"event": "void", "at": now.isoformat(), "key": key}, log_path)

    # 6. the model: load, or (re)train on the research log plus everything this engine has logged itself
    bundle = None
    if model_path.exists():
        try:
            bundle = pickle.load(open(model_path, "rb"))
        except Exception:  # noqa: BLE001
            bundle = None
    stale = bundle is None or datetime.fromisoformat(bundle["trained_at"]) < now - timedelta(days=RULES["retrain_days"])
    if stale:
        base = pd.read_pickle(base_path) if base_path.exists() else None
        if base is None:
            base = work[work["final"]].dropna(subset=["R"])            # no research log here: learn from the last two years
        bundle = train(base, [c for c in st["closed"] if "features" in c], learn.FEATS, learn.model)
        pickle.dump(bundle, open(model_path, "wb"))
        st["model"] = {k: bundle[k] for k in ("trained_at", "rows", "live_rows")}
        _journal({"event": "retrain", "at": now.isoformat(), **st["model"]}, log_path)

    # 2-4. new ideas: log the market, score, decide, say why
    fresh = this_hour - pd.Timedelta(hours=RULES["fresh_hours"])
    new = work[(work["asof"] >= fresh) & ~work["key"].isin(st["seen"])].drop_duplicates("key")
    if len(new):
        new = new.assign(score=bundle["model"].predict(new[learn.FEATS]))
    for _, row in new.iterrows():
        key, take = row["key"], bool(row["score"] > RULES["take_above_R"])
        feats = {f: (None if row[f] != row[f] else round(float(row[f]), 5)) for f in learn.FEATS}
        why = explain(bundle, row.fillna(pd.Series(bundle["medians"])))
        price = float(data[row["sym"]]["close"].asof(row["asof"]))
        d = {"key": key, "strat": row["strat"], "sym": row["sym"], "side": int(row["side"]), "entry_bar": str(row["asof"]),
             "price": price, "score": round(float(row["score"]), 4), "take": take, "why": why, "features": feats,
             "decided_at": now.isoformat()}
        st["seen"][key] = str(row["asof"])
        st["pending"][key] = d
        _journal({"event": "decision", **d}, log_path)
        if take:
            events.append({"type": "learner_entry", "text": f"LEARNER (paper): TAKE {row['strat']} on {row['sym']}, "
                           f"{'long' if row['side'] > 0 else 'short'} at {price:,.5g}. Model expects {row['score']:+.2f}R. "
                           f"Why: {'; '.join(why)}. No real order."})
    cutoff = str(this_hour - pd.Timedelta(days=40))
    st["seen"] = {k: v for k, v in st["seen"].items() if v >= cutoff}
    st["started"] = st["started"] or now.isoformat()
    st["last_tick"], st["ticks"] = now.isoformat(), st["ticks"] + 1
    _save(st, state_path)
    return {"events": events, "new": int(len(new)), "taken": int(new["score"].gt(RULES["take_above_R"]).sum()) if len(new) else 0,
            "pending": len(st["pending"]), "closed": len(st["closed"])}


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        print(json.dumps(tick()))
    except Exception as exc:  # noqa: BLE001
        log.exception("learner tick failed")
        print(json.dumps({"events": [], "error": str(exc)}))
