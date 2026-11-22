"""Monte Carlo range + Bayesian daily-rate read (owner request, 9 Nov; upgraded to
percentile fan paths with per-step up/down odds after the owner asked for a true
forecast: "a forecast like a probability showing it will move up or down with the
chart"; then made structure-aware after the owner said the blind fan was not good
and asked for it to "use the actual chart pattern").

What it answers:
- TODAY: each path re-plays one past session's final bars forward from the current
  price (5-minute steps to the 15:15 square-off). The path cloud gives, at every
  step: the 10/25/50/75/90 percentile prices (the fan chart) and the share of paths
  ABOVE the current price ("the probability it moves up rather than down").
  CONDITIONING: every sampled session is tagged with its own day direction
  (close vs open), and the sampling weight tilts by the Bayesian daily P(up) -
  an up-structure chart replays up-day afternoons, a down one replays down days.
- NEXT SESSION: same walk over whole-day tails, anchored 09:15 -> 15:15 of the next
  trading day.
- KEY LEVELS: the exact list the Key Levels panel shows (prev-day H/L/C, CPR, ORB,
  round numbers, swing zones) is deduped by price and returned, so the fan can be
  read against the chart's own line in the sand.
- PATTERN: the newest candlestick pattern the signal engine's detector sees on the
  5m bars (engulfing, pins, indecision and friends), carried into the panel.
- Barrier stats: how often the CURRENT plan's stop and target get touched, and which
  one first.
- Bayesian: P(an up close) from the daily record with a Beta(1,1) posterior and a 95%
  credible interval, plus the daily HH/HL high-low read.
Nothing here decides a trade: it is the envelope the desk stands in, not a promise.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np

from . import candles as C
from .config import IST, MARKET_OPEN, SQUARE_OFF_BY
from .timeline import is_trading_day

N_PATHS = 2400
MIN_SESSION_BARS = 10       # a real session on 5m; throws away single ghost rows
SESSION_LOOKBACK = 40       # sessions offered to the intraday bootstrap (bounded by feed history)
DAILY_LOOKBACK = 120        # daily completions used for the Bayesian rate
M5 = 5                      # minutes per bar
SESSION_STEPS = ((SQUARE_OFF_BY.hour * 60 + SQUARE_OFF_BY.minute)
                 - (MARKET_OPEN.hour * 60 + MARKET_OPEN.minute)) // M5   # 72: 09:15 -> 15:15 in 5m steps

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


def _session_walks(df5, upto_bars: int, today: date) -> list[dict]:
    """Per-session step-return tails, each tagged with the day's own direction
    (close vs open) - the day-type the bootstrap can be conditioned on."""
    hist = df5[df5.index.date < today]
    if hist.empty:
        return []
    idx = hist.index.date
    out: list[dict] = []
    for d in np.unique(idx):  # ascending order
        closes = hist[idx == d]["close"].to_numpy(dtype=float)
        if len(closes) < MIN_SESSION_BARS:
            continue  # a feed ghost row, not a session
        r = closes[1:] / closes[:-1] - 1.0
        tail = r[-upto_bars:]
        if len(tail) < upto_bars:
            tail = np.concatenate([np.zeros(upto_bars - len(tail)), tail])  # shorter session
        direction = 1 if closes[-1] > closes[0] else -1 if closes[-1] < closes[0] else 0
        out.append({"date": d, "dir": direction, "tail": tail})
    return out


def _sample_probs(walks: list[dict], p_up: float) -> np.ndarray:
    """Per-session sampling weights. tilt = p_up - 0.5: an up-session gets 0.5+tilt,
    a down-session 0.5-tilt, a flat one stays 0.5. 0.5 back to the pooled bootstrap."""
    tilt = float(p_up) - 0.5
    w = np.array([0.5 + (tilt if x["dir"] > 0 else (-tilt if x["dir"] < 0 else 0.0))
                  for x in walks], dtype=float)
    return w / w.sum()


def _qtl(v: np.ndarray) -> dict[str, float]:
    q = np.quantile(v, [0.10, 0.25, 0.50, 0.75, 0.90])
    return {"q10": round(float(q[0]), 2), "q25": round(float(q[1]), 2), "median": round(float(q[2]), 2),
            "q75": round(float(q[3]), 2), "q90": round(float(q[4]), 2),
            "exp_move": round(float(q[4] - q[0]), 2)}


def _walk(spot: float, walks: list[dict], rng: np.random.Generator, n_bars: int,
          start: datetime, p_up: float = 0.5) -> tuple[list[dict], dict[str, float], np.ndarray]:
    """One Monte Carlo walk to n_bars steps from `start`, sampling whole past
    day-tails with the structure tilt.

    Returns the per-step percentile rows + p_up (paths above spot), the end-of-walk
    cone, and the per-path (min, max, end) prices for barrier maths.
    """
    probs = _sample_probs(walks, p_up)
    pick = rng.choice(len(walks), size=N_PATHS, p=probs)
    tails = [w["tail"] for w in walks]
    logs = np.cumsum(np.stack([tails[i] for i in pick]), axis=1)  # (paths, n_bars)
    steps = []
    for k in range(n_bars):
        prices = spot * np.exp(logs[:, k])
        q = np.quantile(prices, [0.10, 0.25, 0.50, 0.75, 0.90])
        steps.append({"t": (start + timedelta(minutes=M5 * (k + 1))).isoformat(),
                      "q10": round(float(q[0]), 2), "q25": round(float(q[1]), 2),
                      "median": round(float(q[2]), 2), "q75": round(float(q[3]), 2),
                      "q90": round(float(q[4]), 2),
                      "p_up": round(float(np.mean(prices > spot)), 4)})
    ends = spot * np.exp(logs[:, -1]) if n_bars else np.full(N_PATHS, spot)
    path_min = spot * np.exp(logs.min(axis=1)) if n_bars else np.full(N_PATHS, spot)
    path_max = spot * np.exp(logs.max(axis=1)) if n_bars else np.full(N_PATHS, spot)
    return steps, _qtl(ends), path_min, path_max, ends


def _barriers(direction: int, spot: float, path_min: np.ndarray, path_max: np.ndarray,
              stop_points: float | None, target_points: float | None) -> dict:
    """How often the plan's stop and target get touched, and which one first.
    For a BUY (long CE) the stop is below and the target above; a SELL (long PE) mirrors it."""
    out: dict = {"touch_stop": None, "touch_target": None, "target_before_stop": None}
    if not stop_points or not target_points or stop_points <= 0 or target_points <= 0:
        return out
    if direction < 0:
        stop_edge, tgt_edge = spot + stop_points, spot - target_points
        touch_stop = float(np.mean(path_max >= stop_edge))
        touch_tgt = float(np.mean(path_min <= tgt_edge))
        both = float(np.mean((path_max >= stop_edge) & (path_min <= tgt_edge)))
        return {"touch_stop": round(touch_stop, 4), "touch_target": round(touch_tgt, 4),
                "target_before_stop": round(max(0.0, touch_tgt - both), 4)}
    out["touch_stop"] = round(float(np.mean(path_min <= spot - stop_points)), 4)
    out["touch_target"] = round(float(np.mean(path_max >= spot + target_points)), 4)
    out["target_before_stop"] = round(float(np.mean((path_max >= spot + target_points)
                                                    & (path_min > spot - stop_points))), 4)
    return out


def _dedupe_levels(levels, spot: float) -> list[dict]:
    """The Key Levels list can name the same price twice (prev close on a round
    number); collapse to the strongest tag, keep the 8 nearest spot."""
    best: dict[int, dict] = {}
    for lv in levels or []:
        try:
            price = float(lv.get("price"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(price) or price <= 0:
            continue
        tag = {"name": str(lv.get("name") or "Level"), "price": round(price, 2),
               "weight": int(lv.get("weight") or 1)}
        slot = int(round(price * 2.0))  # 0.5-point grid
        cur = best.get(slot)
        if cur is None or tag["weight"] > cur["weight"]:
            best[slot] = tag
    return sorted(best.values(), key=lambda x: abs(x["price"] - spot))[:8]


def _timesfm_push(now: datetime, key: str) -> dict | None:
    """A TimesFM fan computed on the owner's PC and pushed here (owner's option A, 11 Nov).

    The PC worker (tools/timesfm_worker.py) forecasts on the same 5-minute closes and
    scp-pushes a JSON file to the VM. A section is used only when its own `asof` is
    fresh (two 5m bars of tolerance, so a slow Yahoo refresh cannot slip in); anything
    stale, malformed or for another key is ignored - never fatal, the Monte Carlo below
    always stands behind it.
    """
    path = os.environ.get("TIMESFM_PUSH_PATH") or str(Path.home() / "timesfm_push.json")
    try:
        raw = json.loads(Path(path).read_text())
    except Exception:
        return None
    if not isinstance(raw, dict) or raw.get("key") != key:
        return None
    out = {}
    for section in ("today", "next"):
        sec = raw.get(section)
        if not isinstance(sec, dict) or not isinstance(sec.get("fan"), list) or not sec["fan"]:
            continue
        try:
            asof = datetime.fromisoformat(str(sec["asof"]))
            if asof.tzinfo is None:
                asof = asof.replace(tzinfo=IST)
            age = (now - asof).total_seconds()
            if age > 660 or age < -300:
                continue
            first = sec["fan"][0]
            if not all(k in first for k in ("q10", "q25", "median", "q75", "q90", "p_up", "t")):
                continue
            out[section] = sec
        except Exception:
            continue
    return out or None


def pattern_read(df5) -> dict | None:
    """The newest candlestick pattern the signal engine sees on the 5m bars -
    the same detector that feeds the score, so the panel and the engine agree."""
    if df5 is None or len(df5) < 20:
        return None
    pats = C.detect(df5, lookback=3)
    if not pats:
        return None
    for p in reversed(pats):  # newest direction-bearing pattern first
        if p.direction != 0:
            return {"name": p.name, "dir": p.direction, "kind": p.kind,
                    "meaning": p.meaning, "time": p.time, "strength": round(float(p.strength), 2)}
    p = pats[-1]
    return {"name": p.name, "dir": 0, "kind": p.kind,
            "meaning": p.meaning, "time": p.time, "strength": round(float(p.strength), 2)}


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


def next_trading_day(now: datetime) -> date:
    d = now.date() + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def predict(key: str, df5, dfd, now: datetime, spot: float | None = None,
            stop_points: float | None = None, target_points: float | None = None,
            direction: int = 0, minutes_left: int | None = None, seed: int | None = None,
            levels: list | None = None) -> dict:
    now = now if now.tzinfo else now.replace(tzinfo=IST)
    trading_day = is_trading_day(now.date())
    if minutes_left is None:
        minutes_left = minutes_left_in_session(now) if trading_day else 0
    if not spot:
        spot = float(df5["close"].iloc[-1]) if not df5.empty else None
    if not spot:
        return {"key": key, "asof": now.isoformat(), "error": "no price"}

    rng = np.random.default_rng(seed if seed is not None else int(now.timestamp()) // 300)

    # ---- Bayesian P(up) FIRST: it is the tilt the whole bootstrap is conditioned on ----
    rets_d: np.ndarray = np.array([])
    n = 0
    bayes = None
    if not dfd.empty and len(dfd) >= 30:
        closes = dfd["close"].to_numpy(dtype=float)
        r = closes[1:] / closes[:-1] - 1.0
        rets_d = r[-DAILY_LOOKBACK:]
        n = int(len(rets_d))
    if n > 0:
        k = int(np.sum(rets_d > 0))
        lo, hi = _beta_ci(k, n)
        bayes = {"k": k, "n": n, "mean": round((k + 1.0) / (n + 2.0), 4), "ci95": [round(lo, 4), round(hi, 4)]}
    tilt_p = float(bayes["mean"]) if bayes else 0.5

    # ---- TODAY: intraday bootstrap, per-step percentile fan from now to square-off ----
    m5 = max(0, int(round(minutes_left / M5)))
    intraday_sessions = 0
    day_types = {"up": 0, "down": 0}
    fan_today: list[dict] = []
    today_cone = None
    day_open = None
    p_close_up_mc = None
    p_end_above_spot = None
    exit_stats = None
    if m5 > 0 and trading_day:
        walks = _session_walks(df5, m5, now.date())
        intraday_sessions = len(walks)
        day_types = {"up": sum(1 for w in walks if w["dir"] > 0), "down": sum(1 for w in walks if w["dir"] < 0)}
        if walks:
            fan_today, today_cone, path_min, path_max, ends = _walk(spot, walks, rng, m5, now, p_up=tilt_p)
            session = df5[df5.index.date == now.date()]
            day_open = float(session["open"].iloc[0]) if not session.empty else spot
            p_close_up_mc = round(float(np.mean(ends > day_open)), 4)
            p_end_above_spot = round(float(np.mean(ends > spot)), 4)
            exit_stats = (_barriers(direction, spot, path_min, path_max, stop_points, target_points)
                          if direction else
                          {"touch_stop": None, "touch_target": None, "target_before_stop": None})

    # ---- NEXT SESSION: same walk, whole-day tails, anchored at the next trading day's 09:15 ----
    fan_next: list[dict] = []
    next_cone = None
    day_walks = _session_walks(df5, SESSION_STEPS, now.date())
    if day_walks:
        start = datetime.combine(next_trading_day(now), MARKET_OPEN, tzinfo=IST)
        fan_next, next_cone, *_rest = _walk(spot, day_walks, rng, SESSION_STEPS, start, p_up=tilt_p)
    elif n > 0:  # no usable 5m history: fall back to whole daily returns
        next_cone = _qtl(spot * (1.0 + rets_d[rng.integers(0, n, size=N_PATHS)]))

    # ---- TimesFM overlay (owner's PC worker, option A, 11 Nov): a fresh pushed fan wins
    # for the fan/cone/probability fields; barrier odds and levels stay Monte Carlo, since
    # quantile fans cannot count barrier touches. A stale/missing push = pure Monte Carlo.
    push = _timesfm_push(now, key)
    engine = None
    if push:
        t = push.get("today")
        if t:
            fan_today = t["fan"]
            if isinstance(t.get("cone"), dict):
                today_cone = t["cone"]
            if isinstance(t.get("p_close_up"), dict):
                pcu = t["p_close_up"]
                p_close_up_mc = pcu.get("mc", p_close_up_mc)
                p_end_above_spot = pcu.get("from_now", p_end_above_spot)
                if pcu.get("day_open") is not None:
                    day_open = pcu["day_open"]
            engine = {"name": str(push.get("engine") or "TimesFM"),
                      "asof": str(t["asof"]),
                      "age_s": int((now - datetime.fromisoformat(str(t["asof"]))).total_seconds())}
        nx = push.get("next")
        if nx:
            fan_next = nx["fan"]
            if isinstance(nx.get("cone"), dict):
                next_cone = nx["cone"]
            if engine is None:
                engine = {"name": str(push.get("engine") or "TimesFM"),
                          "asof": str(nx["asof"]),
                          "age_s": int((now - datetime.fromisoformat(str(nx["asof"]))).total_seconds())}

    base_method = ("Monte Carlo that re-plays the index's own past afternoon bars, tilted by "
                   "the Bayesian daily P(up): up-structure samples up-day afternoons, down-structure "
                   "down ones. Key levels and the newest 5m candle pattern ride along. It describes "
                   "what usually follows this chart shape; it is not a promise.")
    method = (f"Forecast fan from {engine['name']} (computed on the owner's PC, pushed "
              f"{max(engine['age_s'], 0) // 60} min ago); barrier odds and key levels: {base_method}"
              if engine else base_method)

    return {
        "key": key, "asof": now.isoformat(), "price": round(spot, 2), "trading_day": trading_day,
        "minutes_left": minutes_left,
        "today": today_cone,
        "today_p_close_up": ({"mc": p_close_up_mc, "from_now": p_end_above_spot,
                              "day_open": round(day_open, 2) if day_open else None}
                             if trading_day else None),
        "barriers": exit_stats or {"touch_stop": None, "touch_target": None, "target_before_stop": None},
        "direction": direction,
        "fan": {"today": fan_today, "next": fan_next},
        "next_session": next_cone,
        "bayes_up": bayes,
        "levels": _dedupe_levels(levels, spot),
        "pattern": pattern_read(df5),
        "daily": daily_read(dfd, spot, now.date()),
        "size": {"paths": N_PATHS, "intraday_sessions": intraday_sessions,
                 "day_types": day_types, "daily_days": n},
        "method": method,
        "forecast_engine": engine["name"] if engine else "Monte Carlo (on this server)",
        "caveats": [
            "The fan says where price USUALLY drifts step by step, not what WILL happen.",
            "Barrier odds assume the plan's stop and target hold all afternoon - news breaks them.",
            "Levels are magnets, not walls: a strong candle goes straight through them.",
        ],
    }
