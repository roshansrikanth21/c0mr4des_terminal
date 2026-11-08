"""Monte Carlo range + Bayesian daily-rate read (owner request, 9 Nov).

What it answers, in the owner's words: "use Bayesian and Monte Carlo ... a prediction
model as a panel in the UI ... a predicted range".

- Monte Carlo: re-plays the index's OWN last bars. Each path picks one past session at
  random and walks its final N five-minute returns forward from the current price, so the
  cone carries real intraday rhythm (open drive, mid-day chop, afternoon trend) without
  assuming a distribution black box. N paths give the percentiles (the predicted range)
  and how often each barrier (the plan's stop / target) gets touched.
- Bayesian: P(an up close) from the daily record with a Laplace (Beta(1,1)) posterior:
  the mean and its 95% credible interval come from k up-days in n days, shrunk one
  step toward uncertainty.
Nothing here decides a trade: it is the range the desk stands in, not a promise.
"""
from __future__ import annotations

from datetime import date, datetime, time

import numpy as np

from .config import IST, MARKET_OPEN, SQUARE_OFF_BY
from .timeline import is_trading_day

N_PATHS = 2400
MIN_SESSION_BARS = 10       # a real session on 5m; throws away single ghost rows
SESSION_LOOKBACK = 40       # sessions offered to the intraday bootstrap (bounded by feed history)
DAILY_LOOKBACK = 120        # daily completions used for the Bayesian rate
M5 = 5                      # minutes per bar

try:  # scipy ships with scikit-learn; do not hard-require the whole ML stack here
    from scipy.stats import beta as _beta_dist

    def _beta_ci(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
        if n <= 0:
            return (0.5, 0.5)
        tail = (1.0 - conf) / 2.0
        a, b = k + 1.0, n - k + 1.0
        return (float(_beta_dist.ppf(tail, a, b)), float(_beta_dist.ppf(1.0 - tail, a, b)))
except ImportError:  # normal approximation to the Beta posterior
    def _beta_ci(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
        if n <= 0:
            return (0.5, 0.5)
        p = (k + 1.0) / (n + 2.0)
        z = 1.959964
        half = z * np.sqrt(p * (1.0 - p) / (n + 3.0))
        return (max(0.0, p - half), min(1.0, p + half))


def minutes_left_in_session(now: datetime, square_off_by: time | None = None) -> int:
    """Minutes from now to 15:15 square-off on a trading day; 0 when closed or after the close."""
    if not is_trading_day(now.date()):
        return 0
    t = now.astimezone(IST).time()
    end = square_off_by or SQUARE_OFF_BY
    if t <= MARKET_OPEN:
        return int((datetime.combine(now.date(), end) - datetime.combine(now.date(), MARKET_OPEN)).total_seconds() // 60)
    if t >= end:
        return 0
    return int((datetime.combine(now.date(), end) - datetime.combine(now.date(), t)).total_seconds() // 60)


def _session_returns(df5, upto_bars: int, today: date) -> list[np.ndarray]:
    """Per-session, per-bar log-scale returns for the LAST `upto_bars` bars, one entry per session."""
    hist = df5[df5.index.date < today]
    if hist.empty:
        return []
    idx = hist.index.date
    out = []
    for d in np.unique(idx):  # ascending order
        closes = hist[idx == d]["close"].to_numpy(dtype=float)
        if len(closes) < MIN_SESSION_BARS:
            continue  # a feed ghost row, not a session
        r = closes[1:] / closes[:-1] - 1.0
        tail = r[-upto_bars:]
        if len(tail) < upto_bars:
            tail = np.concatenate([np.zeros(upto_bars - len(tail)), tail])  # shorter session
        out.append(tail)
    return out


def _qtl(v: np.ndarray) -> dict[str, float]:
    q = np.quantile(v, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {"q10": round(float(q[0]), 2), "q25": round(float(q[1]), 2), "median": round(float(q[2]), 2),
            "q75": round(float(q[3]), 2), "q90": round(float(q[4]), 2),
            "exp_move": round(float(q[4] - q[0]), 2)}


def _barrier_stats(path_min: np.ndarray, path_max: np.ndarray,
                   spot: float, stop_points: float | None, target_points: float | None) -> dict:
    out: dict = {"touch_stop": None, "touch_target": None, "target_before_stop": None}
    if stop_points and stop_points > 0:
        out["touch_stop"] = round(float(np.mean(path_min <= spot - stop_points)), 4)
    if target_points and target_points > 0:
        out["touch_target"] = round(float(np.mean(path_max >= spot + target_points)), 4)
    if out["touch_stop"] is not None and out["touch_target"] is not None:
        out["target_before_stop"] = round(float(np.mean((path_max >= spot + target_points)
                                                        & (path_min > spot - stop_points))), 4)
    return out


def daily_read(dfd, spot: float | None, today: date) -> dict:
    """The owner's daily high/low trend: HH/HL chain over the last completions and where spot sits."""
    hist = dfd[dfd.index.date < today]
    if hist.empty or len(hist) < 8:
        return {"score": 0, "days": int(len(hist)), "text": "Not enough daily history for the high/low read."}
    last6 = hist.tail(6)
    labels = []
    for i in range(1, len(last6)):
        hh = last6["high"].iloc[i] > last6["high"].iloc[i - 1]
        hl = last6["low"].iloc[i] > last6["low"].iloc[i - 1]
        labels.append("HH/HL" if hh and hl else "LH/LL" if (not hh and not hl) else "HH/LL" if hh else "LH/HL")
    chain = sum(2 if l == "HH/HL" else -2 if l == "LH/LL" else 0 for l in labels)
    chain = max(-6, min(6, chain))  # bounded like a score the UI can colour
    y_hi, y_lo = float(last6["high"].iloc[-1]), float(last6["low"].iloc[-1])
    pos = ("above yesterday's high" if spot and spot > y_hi
           else "below yesterday's low" if spot and spot < y_lo
           else "inside yesterday's range")
    trend_word = "up" if chain > 0 else "down" if chain < 0 else "flat"
    return {"score": chain, "days": int(len(hist)),
            "text": f"Daily structure {trend_word} ({' > '.join(labels[-3:])}); spot {pos}."}


def predict(key: str, df5, dfd, now: datetime, spot: float | None = None,
            stop_points: float | None = None, target_points: float | None = None,
            direction: int = 0, minutes_left: int | None = None, seed: int | None = None) -> dict:
    now = now if now.tzinfo else now.replace(tzinfo=IST)
    trading_day = is_trading_day(now.date())
    if minutes_left is None:
        minutes_left = minutes_left_in_session(now) if trading_day else 0
    if not spot:
        spot = float(df5["close"].iloc[-1]) if not df5.empty else None
    if not spot:
        return {"key": key, "asof": now.isoformat(), "error": "no price"}

    rng = np.random.default_rng(seed if seed is not None else int(now.timestamp()) // 300)

    # ---- TODAY: intraday bootstrap, walk forward from now to the square-off ----
    m5 = max(0, int(round(minutes_left / M5)))
    intraday_sessions = 0
    today_cone = None
    barriers = {"touch_stop": None, "touch_target": None, "target_before_stop": None}
    day_open = None
    p_close_up_mc = None
    if m5 > 0 and trading_day:
        tails = _session_returns(df5, m5, now.date())
        intraday_sessions = len(tails)
        if tails:
            pick = rng.integers(0, len(tails), size=N_PATHS)
            logs = np.cumsum(np.stack([tails[i] for i in pick]), axis=1)  # (paths, m5) log cum
            ends = spot * np.exp(logs[:, -1])
            path_min = spot * np.exp(logs.min(axis=1))
            path_max = spot * np.exp(logs.max(axis=1))
            session = df5[df5.index.date == now.date()]
            day_open = float(session["open"].iloc[0]) if not session.empty else spot
            p_close_up_mc = round(float(np.mean(ends > day_open)), 4)
            if direction:
                # for a SELL plan the stop sits ABOVE and the target BELOW - mirror the distances
                s_pts, t_pts = (stop_points, target_points)
                if direction < 0:
                    lo_stop = spot + s_pts if s_pts else None
                    hi_tgt = spot - t_pts if t_pts else None
                    if lo_stop and hi_tgt:
                        touch_stop = float(np.mean(path_max >= lo_stop))
                        touch_tgt = float(np.mean(path_min <= hi_tgt))
                        both = float(np.mean((path_max >= lo_stop) & (path_min <= hi_tgt)))
                        barriers = {"touch_stop": round(touch_stop, 4), "touch_target": round(touch_tgt, 4),
                                    "target_before_stop": round(max(0.0, touch_tgt - both), 4)}
                else:
                    barriers = _barrier_stats(path_min, path_max, spot, s_pts, t_pts)
            today_cone = _qtl(ends)

    # ---- NEXT SESSION: whole daily returns resampled, one per path ----
    rets_d: np.ndarray = np.array([])
    n = 0
    next_cone = None
    if not dfd.empty and len(dfd) >= 30:
        closes = dfd["close"].to_numpy(dtype=float)
        r = closes[1:] / closes[:-1] - 1.0
        rets_d = r[-DAILY_LOOKBACK:]
        sample = rets_d[rng.integers(0, len(rets_d), size=N_PATHS)]
        next_cone = _qtl(spot * (1.0 + sample))

    # ---- Bayesian: P(up close) posterior from the same daily record ----
    bayes = None
    if (n := int(len(rets_d))) > 0:
        k = int(np.sum(rets_d > 0))
        lo, hi = _beta_ci(k, n)
        bayes = {"k": k, "n": n, "mean": round((k + 1.0) / (n + 2.0), 4), "ci95": [round(lo, 4), round(hi, 4)]}

    return {
        "key": key, "asof": now.isoformat(), "price": round(spot, 2), "trading_day": trading_day,
        "minutes_left": minutes_left,
        "today": today_cone,
        "today_p_close_up": ({"mc": p_close_up_mc, "day_open": round(day_open, 2) if day_open else None}
                             if trading_day else None),
        "barriers": barriers if direction else {k: None for k in barriers},
        "direction": direction,
        "next_session": next_cone,
        "bayes_up": bayes,
        "daily": daily_read(dfd, spot, now.date()),
        "size": {"paths": N_PATHS, "intraday_sessions": intraday_sessions, "daily_days": n},
        "method": ("Monte Carlo (bootstrap of the index's own intraday bars) for the range; "
                   "Bayesian Beta posterior (Laplace) for the daily up-rate. Both read the past: "
                   "they narrow what to expect, they do not promise it."),
        "caveats": [
            "The cone says where price USUALLY ends up from here, not what WILL happen tomorrow.",
            "Barrier odds assume the plan's stop and target hold all afternoon - news breaks them.",
            "Weekend and holiday reads have no intraday cone; daily numbers come from the same record.",
        ],
    }
