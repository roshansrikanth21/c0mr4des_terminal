"""Our own decision engine - the local alternative to a hosted one like Jev.

The contract is the same shape a hosted decision engine gives you, without the dependency:

    structured state in  ->  typed probabilistic output out  ->  policy stays in code

It answers exactly one question - *given what is observable at the entry bar, what is the
probability this trade finishes green?* - and compares that to the win rate the payoff needs.
It never sizes, never picks a direction, never moves a stop. Those stay deterministic, in
`trader.py` / `options.py`, where they can be read and tested.

Three rules keep it honest, because a probability model on ~60 sessions is mostly a machine for
manufacturing confidence:

1. SHADOW until the sample floor. Below `MIN_LIVE` rows it reports its number and nothing else:
   it cannot block a trade and it cannot allow one. `action` is always "SHADOW".
2. Promotion needs out-of-sample evidence, not in-sample fit: walk-forward AUC >= `MIN_AUC` AND a
   filter that beats taking every trade, measured only on days the model was not fitted to.
3. Refit is explicit. Nothing retunes itself inside the trading loop; `refit()` is called by hand
   or by a weekly job, and it records what it found even when it finds nothing.

Why logistic regression and not a forest or a booster: ~60 sessions x ~2 rules is under 200 rows
with a dozen features. A tree ensemble would memorise the training days and report a beautiful
in-sample AUC. A regularised linear model at least fails visibly, and its coefficients can be
read and argued with.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .config import IST
from .dataset import FEATURES, build, matrix

log = logging.getLogger("engine.decision")

MODEL_FILE = Path(__file__).resolve().parents[1] / "data" / "decision_model.json"

MIN_TRAIN = 120   # rows needed before a fit is even attempted
MIN_LIVE = 200    # rows needed before the model may gate a real trade
MIN_AUC = 0.55    # out-of-sample discrimination worth acting on
L2 = 4.0          # strong on purpose: a dozen features on ~200 rows overfits instantly at L2=0
FOLDS = 4

# Which rule fired is part of the state, not a market feature. Without it the model just reads
# `risk_atr` as a proxy for "this is First-30", and every other coefficient becomes noise.
STRATEGY_FEATURE = "is_first30"
MODEL_FEATURES = FEATURES + (STRATEGY_FEATURE,)

# The two rules the desk actually trades, in their live form.
TRAINED = (
    ("First-Hour", "first_hour_breakout", {"rr": 2.0}),
    ("First-30", "first30_direction", {"stop_mode": "mid", "rr": None}),
)


# ------------------------------------------------------------------ maths
def _sig(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _fit(X: np.ndarray, y: np.ndarray, l2: float = L2, iters: int = 60) -> np.ndarray:
    """L2 logistic regression by Newton steps. Bias is not penalised."""
    w = np.zeros(X.shape[1])
    pen = l2 * np.r_[0.0, np.ones(X.shape[1] - 1)]
    for _ in range(iters):
        p = _sig(X @ w)
        g = X.T @ (p - y) + pen * w
        H = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        w = w - step
        if np.abs(step).max() < 1e-9:
            break
    return w


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    """Rank AUC with ties averaged - the probability a winner scores above a loser."""
    pos, neg = y == 1, y == 0
    if pos.sum() == 0 or neg.sum() == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2.0) / (pos.sum() * neg.sum()))


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _fit_lin(X: np.ndarray, y: np.ndarray, l2: float = L2) -> np.ndarray:
    """Ridge on the R-multiple. Closed form, bias unpenalised."""
    pen = l2 * np.r_[0.0, np.ones(X.shape[1] - 1)]
    try:
        return np.linalg.solve(X.T @ X + np.diag(pen), X.T @ y)
    except np.linalg.LinAlgError:
        return np.zeros(X.shape[1])


def _design(train: pd.DataFrame, test: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Standardise on train only, then apply the same mu/sd to test."""
    Xtr, ytr = matrix(train, MODEL_FEATURES)
    mu, sd = Xtr[:, 1:].mean(axis=0), Xtr[:, 1:].std(axis=0)
    sd[sd == 0] = 1.0
    Ztr = np.column_stack([np.ones(len(Xtr)), (Xtr[:, 1:] - mu) / sd])
    Xte, yte = matrix(test, MODEL_FEATURES)
    Zte = np.column_stack([np.ones(len(Xte)), (Xte[:, 1:] - mu) / sd])
    return Ztr, ytr, Zte, yte


def walk_forward(df: pd.DataFrame, folds: int = FOLDS) -> dict:
    """Expanding-window validation: train on every day before a block, test on the block.

    Two heads, because they answer different questions and only one of them can pay:
      * win head  - P(this trade finishes green). Easy to fit, and the wrong objective here.
      * R head    - expected R-multiple (P&L / what the stop risked). This is the one that pays,
                    because the record is asymmetric: First-30 wins 32% of the time and still
                    makes money, so dropping "low probability" trades throws away the winners.
    """
    days = sorted(df["day"].unique())
    if len(days) < folds * 4:
        return {"ok": False, "reason": f"only {len(days)} sessions; need at least {folds * 4}"}
    edges = [int(round(len(days) * k / folds)) for k in range(folds + 1)]
    oos_p, oos_ev, oos_y, oos_pnl, oos_key, blocks = [], [], [], [], [], []
    for k in range(folds):
        test_days = set(days[edges[k]:edges[k + 1]])
        train = df[~df["day"].isin(test_days)]
        test = df[df["day"].isin(test_days)]
        if len(train) < 40 or test.empty:
            continue
        Ztr, ytr, Zte, yte = _design(train, test)
        w = _fit(Ztr, ytr)
        r_tr = np.clip(train["r"].to_numpy(dtype=float), -3, 3)
        w_ev = _fit_lin(Ztr, r_tr)
        oos_p.append(_sig(Zte @ w))
        oos_ev.append(Zte @ w_ev)
        oos_y.append(yte)
        oos_pnl.append(test["pnl"].to_numpy(dtype=float))
        oos_key.append(test["slice"].to_numpy() if "slice" in test else np.array(["all"] * len(test)))
        blocks.append({"fold": k + 1, "train": len(train), "test": len(test),
                       "train_days": int(train["day"].nunique()), "test_days": len(test_days),
                       "auc": round(_auc(yte, _sig(Zte @ w)), 3),
                       "r_corr": round(float(np.corrcoef(Zte @ w_ev, test["r"].clip(-3, 3))[0, 1]), 3)
                       if len(test) > 2 else None})
    if not oos_p:
        return {"ok": False, "reason": "no fold had enough training rows"}
    p, ev, y, pnl = (np.concatenate(a) for a in (oos_p, oos_ev, oos_y, oos_pnl))
    key = np.concatenate(oos_key)
    by_p, by_ev = [], []
    for thr in (0.0, 0.30, 0.35, 0.40, 0.45, 0.50):
        keep = p >= thr
        by_p.append({"threshold": round(thr, 2), "trades": int(keep.sum()),
                     "net": round(float(pnl[keep].sum())),
                     "win_rate": round(float(y[keep].mean() * 100), 1) if keep.any() else None})
    for thr in (-0.5, -0.25, 0.0, 0.15, 0.3):
        keep = ev >= thr
        by_ev.append({"threshold": round(thr, 2), "trades": int(keep.sum()),
                      "net": round(float(pnl[keep].sum())),
                      "win_rate": round(float(y[keep].mean() * 100), 1) if keep.any() else None})
    best_p = max(by_p, key=lambda f: f["net"])
    best_ev = max(by_ev, key=lambda f: f["net"])
    slices = {}
    for s in sorted(set(key.tolist())):
        m = key == s
        slices[s] = {"trades": int(m.sum()), "win_rate": round(float(y[m].mean() * 100), 1),
                     "net": round(float(pnl[m].sum())), "auc": round(_auc(y[m], p[m]), 3)}
    return {"ok": True, "oos_trades": int(len(y)), "oos_auc": round(_auc(y, p), 3),
            "oos_brier": round(_brier(y, p), 4), "oos_logloss": round(_logloss(y, p), 4),
            "base_rate": round(float(y.mean() * 100), 1),
            "all_net": round(float(pnl.sum())),
            "win_filters": by_p, "best_win_filter": best_p,
            "ev_filters": by_ev, "best_ev_filter": best_ev,
            "slices": slices, "folds": blocks}


# ------------------------------------------------------------------ training
def refit(keys=("NIFTY", "SENSEX")) -> dict:
    """Build the dataset, fit, validate, and save. Records a failure as loudly as a success."""
    from . import lab

    frames = []
    for key in keys:
        for label, fn_name, kw in TRAINED:
            try:
                d = build(key, getattr(lab, fn_name), f"{key} {label}", **kw)
            except Exception as exc:  # noqa: BLE001
                log.warning("dataset build failed for %s %s: %s", key, label, exc)
                continue
            if d.empty:
                continue
            d["instrument"] = key
            d["slice"] = f"{key} {label}"
            d[STRATEGY_FEATURE] = 1.0 if label == "First-30" else 0.0
            frames.append(d)
    if not frames:
        return {"ok": False, "reason": "no training rows - no intraday history available"}
    source = frames[0].attrs.get("source") or "unknown"
    df = pd.concat(frames, ignore_index=True).sort_values(["day", "time"]).reset_index(drop=True)
    card = {
        "version": f"lr-{date.today().isoformat()}",
        "fitted_at": pd.Timestamp.now(tz=IST).isoformat(),
        "samples": int(len(df)), "sessions": int(df["day"].nunique()),
        "span": f"{df['day'].min()} .. {df['day'].max()}", "source": source,
        "base_rate": round(float(df["win"].mean() * 100), 1),
        "features": list(MODEL_FEATURES), "l2": L2,
    }
    if len(df) < MIN_TRAIN:
        card.update({"ok": False, "status": "shadow", "w": None,
                     "reason": f"{len(df)} rows < {MIN_TRAIN}: not enough to fit anything honest"})
        _save(card)
        return card

    X, y = matrix(df, MODEL_FEATURES)
    mu, sd = X[:, 1:].mean(axis=0), X[:, 1:].std(axis=0)
    sd[sd == 0] = 1.0
    Z = np.column_stack([np.ones(len(X)), (X[:, 1:] - mu) / sd])
    w = _fit(Z, y)
    w_ev = _fit_lin(Z, np.clip(df["r"].to_numpy(dtype=float), -3, 3))
    # Break-even win rate the payoff actually needs, from the training set's own win/loss sizes.
    win_avg = float(df.loc[df.win == 1, "pnl"].mean() or 0)
    loss_avg = float(df.loc[df.win == 0, "pnl"].mean() or 0)
    breakeven = (abs(loss_avg) / (win_avg + abs(loss_avg))) if win_avg > 0 and loss_avg < 0 else 0.5

    wf = walk_forward(df)
    # Promotion needs BOTH heads, and the EV head must show a *material* gain, not a rounding error.
    # +1,790 on +151,687 is noise: a filter has to earn at least 10% more while actually dropping
    # trades (<=85% kept), and the R ranking has to be right in at least 3 of 4 folds.
    folds_pos = sum(1 for f in (wf.get("folds") or []) if (f.get("r_corr") or 0) > 0)
    best_ev = wf.get("best_ev_filter") or {}
    promoted = bool(wf.get("ok") and len(df) >= MIN_LIVE and wf["oos_auc"] >= MIN_AUC
                    and best_ev.get("net", 0) >= wf["all_net"] * 1.10
                    and best_ev.get("trades", 0) >= 40
                    and best_ev.get("trades", 0) <= 0.85 * wf["oos_trades"]
                    and folds_pos >= 3)
    card.update({
        "ok": True, "status": "active" if promoted else "shadow",
        "w": [round(float(x), 6) for x in w],
        "w_ev": [round(float(x), 6) for x in w_ev],
        "mu": [round(float(x), 6) for x in mu], "sd": [round(float(x), 6) for x in sd],
        "coefficients": {f: round(float(c), 4) for f, c in zip(MODEL_FEATURES, w[1:])},
        "ev_coefficients": {f: round(float(c), 4) for f, c in zip(MODEL_FEATURES, w_ev[1:])},
        "breakeven": round(breakeven, 4),
        "threshold": float(wf["best_ev_filter"]["threshold"]) if wf.get("ok") else 0.0,
        "walk_forward": wf,
        "promotion": (("promoted: OOS AUC %.2f, EV filter %+.0f vs %+.0f taking all"
                       % (wf["oos_auc"], best_ev["net"], wf["all_net"])) if promoted else
                      (("stays SHADOW: %d rows (need %d), OOS AUC %s. Best EV filter %+.0f on %d "
                        "trades vs %+.0f taking all (need +10%% and <=85%% kept); R ranking right "
                        "in %d/4 folds. No filter earns its keep"
                        % (len(df), MIN_LIVE, wf.get("oos_auc"), best_ev.get("net", 0),
                           best_ev.get("trades", 0), wf["all_net"], folds_pos)) if wf.get("ok") else
                       f"stays SHADOW: {wf.get('reason')}")),
    })
    _save(card)
    return card


def _save(card: dict) -> None:
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.write_text(json.dumps(card, indent=2), encoding="utf-8")


def load() -> dict | None:
    try:
        return json.loads(MODEL_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ decision
def _vector(feats: dict, strategy: str | None, m: dict) -> np.ndarray:
    row = {**feats, STRATEGY_FEATURE: 1.0 if strategy == "First-30" else 0.0}
    return np.array([1.0] + [(float(row.get(f, 0.0)) - mu) / sd
                             for f, mu, sd in zip(MODEL_FEATURES, m["mu"], m["sd"])])


def decide(feats: dict | None, strategy: str | None = None) -> dict:
    """Typed output. `action` is SHADOW unless the model was promoted on out-of-sample evidence."""
    m = load()
    if not m or not m.get("w") or not feats:
        return {"action": "SHADOW", "p_win": None, "edge": None, "confidence": "none",
                "model": (m or {}).get("version"), "samples": (m or {}).get("samples"),
                "reasons": ["no fitted model - the rule engine decides"]}
    x = _vector(feats, strategy, m)
    p = float(_sig(np.array(m["w"]) @ x))
    ev = float(np.array(m.get("w_ev") or m["w"]) @ x)  # expected R-multiple
    be = float(m.get("breakeven") or 0.5)
    edge = p - be
    conf = ("none" if m["samples"] < MIN_TRAIN else
            "low" if m["samples"] < MIN_LIVE else
            "medium" if m.get("status") == "active" else "low")
    active = m.get("status") == "active" and m["samples"] >= MIN_LIVE
    action = "SHADOW"
    if active:
        action = "GO" if ev >= float(m.get("threshold") or 0.0) else "NO_GO"
    reasons = [f"P(green) {p:.0%} vs break-even {be:.0%} -> edge {edge:+.0%}",
               f"expected {ev:+.2f}R per trade",
               f"model {m['version']} on {m['samples']} rows, OOS AUC "
               f"{(m.get('walk_forward') or {}).get('oos_auc')}"]
    if not active:
        reasons.append(f"SHADOW: {m.get('promotion') or 'not promoted'} - it records, it does not decide")
    return {"action": action, "p_win": round(p, 4), "ev_r": round(ev, 3),
            "breakeven": round(be, 4), "edge": round(edge, 4), "confidence": conf,
            "model": m["version"], "samples": m["samples"], "threshold": m.get("threshold"),
            "status": m.get("status"), "reasons": reasons, "features": feats}


def live_features(a: dict, direction: int, stop: float, entry: float,
                  expiry: str | None = None) -> dict | None:
    """The same feature vector `dataset.features` computes, from a live analysis payload.

    Uses only bars that had already closed, so the live number and the trained number come from
    the same information set.
    """
    try:
        from .dataset import features as _features

        bars = pd.DataFrame(a["candles"])
        if bars.empty:
            return None
        df = bars[["open", "high", "low", "close"]].astype(float)
        df["volume"] = 0.0  # index volume is always 0 on both feeds; chart_payload omits the column
        df.index = pd.DatetimeIndex(pd.to_datetime(bars["time"], unit="s", utc=True).dt.tz_convert(IST))
        df = df.sort_index()
        today = date.fromisoformat(a["generated_at"][:10])
        day = df[df.index.date == today]
        if len(day) < 6:
            return None
        levels = {lv["name"]: lv["price"] for lv in (a.get("levels") or [])}
        before_today = df[df.index.date < today]
        ctx = {"hist": df, "day_start": int(np.argmax(df.index.date == today)),
               "pdh": levels.get("Prev Day High"), "pdl": levels.get("Prev Day Low"),
               "pdc": float(before_today.close.iloc[-1]) if len(before_today) else float(day.open.iloc[0]),
               "vix": (a.get("vix") or {}).get("value"),
               "expiry": date.fromisoformat(expiry) if expiry else None}
        return _features(day, len(day), ctx, direction, stop, entry)  # len(day) = "next bar"
    except Exception as exc:  # noqa: BLE001
        log.warning("live features failed: %s", exc)
        return None


def card() -> dict:
    """What the desk and the API show: the model, its evidence, and nothing dressed up."""
    m = load()
    if not m:
        return {"status": "none", "reason": "not fitted yet - run refit",
                "min_live": MIN_LIVE, "min_auc": MIN_AUC}
    wf = m.get("walk_forward") or {}
    return {"version": m.get("version"), "status": m.get("status"), "samples": m.get("samples"),
            "sessions": m.get("sessions"), "span": m.get("span"), "base_rate": m.get("base_rate"),
            "source": m.get("source"),
            "breakeven": m.get("breakeven"), "threshold": m.get("threshold"),
            "coefficients": m.get("coefficients"), "ev_coefficients": m.get("ev_coefficients"),
            "promotion": m.get("promotion"),
            "oos_auc": wf.get("oos_auc"), "oos_trades": wf.get("oos_trades"),
            "all_net": wf.get("all_net"),
            "best_win_filter": wf.get("best_win_filter"),
            "best_ev_filter": wf.get("best_ev_filter"),
            "ev_filters": wf.get("ev_filters"),
            "slices": wf.get("slices"), "folds": wf.get("folds"),
            "min_live": MIN_LIVE, "min_auc": MIN_AUC}
