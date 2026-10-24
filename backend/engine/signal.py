"""The brain: fuse trend, structure, momentum, candles, levels, news and global cues into
one verdict - BUY (buy CE), SELL (buy PE) or NO TRADE - with reasons in plain English.

`evaluate()` is a pure function of candles (+ optional news/cue bias) so the exact same
logic runs live and in the walk-forward backtest. No randomness, no hidden state.
"""
from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd

from . import candles as C
from . import structure as S
from .indicators import adx, atr, ema, linreg_slope, rsi, supertrend

WEIGHTS = {"trend": 2.5, "structure": 2.0, "momentum": 1.5, "candles": 1.5, "levels": 1.0, "news": 0.75, "global": 0.5}
BASE_THRESHOLD = 0.35
MIN_REWARD_RISK = 1.5


def _word(x: float) -> str:
    return "bullish" if x > 0.15 else "bearish" if x < -0.15 else "neutral"


def resample_15m(df5: pd.DataFrame) -> pd.DataFrame:
    g = df5.resample("15min", label="left", closed="left")
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    counts = g["close"].count()
    out = out[counts.reindex(out.index).fillna(0) >= 3]  # only fully formed 15m bars
    return out


def _trend(df15: pd.DataFrame) -> tuple[float, str, dict]:
    if len(df15) < 60:
        return 0.0, "Not enough 15-minute history for the bigger trend.", {}
    c = df15["close"]
    e20, e50 = ema(c, 20).iloc[-1], ema(c, 50).iloc[-1]
    st = supertrend(df15).iloc[-1]
    adx_v, pdi, mdi = (x.iloc[-1] for x in adx(df15))
    last = c.iloc[-1]
    s = 0.0
    s += 0.35 if e20 > e50 else -0.35
    s += 0.25 if last > e20 else -0.25
    s += 0.25 * st
    s += 0.15 if pdi > mdi else -0.15
    strength = min(1.0, max(0.3, adx_v / 30))  # weak ADX shrinks the trend vote
    s *= strength
    if adx_v < 18:
        txt = f"15-min trend is weak/sideways (ADX {adx_v:.0f}). Market is not trending cleanly."
    else:
        d = "UP" if s > 0 else "DOWN"
        txt = (f"15-min trend is {d} (ADX {adx_v:.0f}): price is {'above' if last > e20 else 'below'} the 20 EMA, "
               f"20 EMA is {'above' if e20 > e50 else 'below'} the 50 EMA, Supertrend is {'green' if st > 0 else 'red'}.")
    return float(np.clip(s, -1, 1)), txt, {"ema20": round(e20, 2), "ema50": round(e50, 2), "adx": round(adx_v, 1),
                                          "supertrend": int(st)}


def _momentum(df5: pd.DataFrame) -> tuple[float, str, dict]:
    c = df5["close"]
    r = rsi(c).iloc[-1]
    e9, e21 = ema(c, 9).iloc[-1], ema(c, 21).iloc[-1]
    slope, r2 = linreg_slope(c, 12)
    a = atr(df5).iloc[-1]
    s = 0.0
    s += 0.4 if r > 55 else -0.4 if r < 45 else 0
    s += 0.3 if e9 > e21 else -0.3
    norm = slope / a if a else 0
    s += 0.3 * float(np.clip(norm * 4, -1, 1)) * r2
    txt = (f"5-min momentum: RSI {r:.0f} ({'buyers stronger' if r > 55 else 'sellers stronger' if r < 45 else 'balanced'}), "
           f"9 EMA {'above' if e9 > e21 else 'below'} 21 EMA, last hour's slope is "
           f"{'up' if slope > 0 else 'down'}{' and steady' if r2 > 0.6 else ' but choppy'}.")
    return float(np.clip(s, -1, 1)), txt, {"rsi": round(r, 1), "ema9": round(e9, 2), "ema21": round(e21, 2)}


def evaluate(df5: pd.DataFrame, daily: pd.DataFrame, step: int, now: datetime | None = None,
             news_bias: float = 0.0, cue_bias: float = 0.0, session: dict | None = None, use_htf: bool = True) -> dict:
    """Score the last CLOSED 5m bar. df5 must contain only closed bars."""
    if len(df5) < 10:
        raise RuntimeError(f"Not enough candles to analyse yet ({len(df5)} bar(s), need 10)")
    df5 = df5.tail(600)
    price = float(df5["close"].iloc[-1])
    a5 = float(atr(df5).iloc[-1])
    df15 = resample_15m(df5)
    reasons, factors = [], {}

    t_s, t_txt, t_info = _trend(df15)
    factors["trend"] = t_s
    reasons.append({"factor": "Big-picture trend (15m)", "signal": _word(t_s), "text": t_txt})

    piv = S.swings(df5)
    s_dir, s_txt = S.trend_from_swings(piv)
    bos = S.break_of_structure(df5, piv, s_dir)
    st_s = 0.6 * s_dir
    if bos:
        st_s += 0.4 * bos["direction"]
        s_txt += " " + bos["text"]
    factors["structure"] = float(np.clip(st_s, -1, 1))
    reasons.append({"factor": "Market structure (5m swings)", "signal": _word(st_s), "text": s_txt})

    m_s, m_txt, m_info = _momentum(df5)
    factors["momentum"] = m_s
    reasons.append({"factor": "Momentum (5m)", "signal": _word(m_s), "text": m_txt})

    levels = S.key_levels(df5, daily, step) + S.swing_zones(piv[-20:], a5)
    if use_htf:
        levels += S.htf_levels(df5, daily)
    sup, res = S.nearest(levels, price)

    pats = C.detect(df5, lookback=3)
    c_s, used = 0.0, []
    for p in pats:
        if p.direction == 0:
            continue
        w = p.strength * (1.0 if p.context_ok else 0.4)
        lvl = sup if p.direction > 0 else res
        at_level = lvl is not None and abs(price - lvl["price"]) <= 0.6 * a5
        if p.kind == "reversal" and at_level:
            w *= 1.5
        age = len(df5) - 1 - df5.index.get_loc(pd.Timestamp(p.time))
        w *= 1.0 if age == 0 else 0.6 if age == 1 else 0.35
        c_s += p.direction * w
        used.append(p.name + (f" at {lvl['name']}" if p.kind == "reversal" and at_level else ""))
    c_s = float(np.clip(c_s, -1, 1))
    factors["candles"] = c_s
    anat = C.anatomy(df5.iloc[-1], a5)
    c_txt = anat["text"] + (f" Patterns: {', '.join(used)}." if used else " No meaningful candlestick pattern right now.")
    reasons.append({"factor": "Candles & patterns", "signal": _word(c_s), "text": c_txt})

    # Location: breaking out of key levels vs. stuck under/over them
    l_s, l_txt = 0.0, []
    for lv in levels:
        if lv["name"] in ("Prev Day High", "Opening Range High", "Prev Week High") and df5["close"].iloc[-2] <= lv["price"] < price:
            l_s += 0.5
            l_txt.append(f"just broke above {lv['name']} ({lv['price']:.0f})")
        if lv["name"] in ("Prev Day Low", "Opening Range Low", "Prev Week Low") and df5["close"].iloc[-2] >= lv["price"] > price:
            l_s -= 0.5
            l_txt.append(f"just broke below {lv['name']} ({lv['price']:.0f})")
    pdh = next((lv["price"] for lv in levels if lv["name"] == "Prev Day High"), None)
    pdl = next((lv["price"] for lv in levels if lv["name"] == "Prev Day Low"), None)
    if pdh and price > pdh:
        l_s += 0.3
        l_txt.append("trading above yesterday's high (bullish day)")
    elif pdl and price < pdl:
        l_s -= 0.3
        l_txt.append("trading below yesterday's low (bearish day)")
    elif pdh and pdl:
        l_txt.append("inside yesterday's range")
    l_s = float(np.clip(l_s, -1, 1))
    factors["levels"] = l_s
    loc = (f"Nearest support {sup['name']} {sup['price']:.0f} ({(price - sup['price']) / a5:.1f} ATR below)" if sup else "No support level below")
    loc += "; " + (f"nearest resistance {res['name']} {res['price']:.0f} ({(res['price'] - price) / a5:.1f} ATR above)" if res else "no resistance above")
    reasons.append({"factor": "Key levels", "signal": _word(l_s), "text": "Price is " + ", ".join(l_txt) + ". " + loc + "."})

    factors["news"] = float(np.clip(news_bias, -1, 1))
    factors["global"] = float(np.clip(cue_bias, -1, 1))

    score = sum(WEIGHTS[k] * v for k, v in factors.items()) / sum(WEIGHTS.values())
    direction = 1 if score > 0 else -1 if score < 0 else 0

    # ---------- trade plan on the underlying ----------
    if direction > 0:
        swing_lows = [p["price"] for p in piv if p["type"] == "L" and p["price"] < price]
        stop_ref = max(swing_lows[-1] if swing_lows else price - a5, sup["price"] if sup else price - a5)
        stop = min(price - 1.0 * a5, max(stop_ref - 0.25 * a5, price - 2.5 * a5))
        tgt_lvl = res
    else:
        swing_highs = [p["price"] for p in piv if p["type"] == "H" and p["price"] > price]
        stop_ref = min(swing_highs[-1] if swing_highs else price + a5, res["price"] if res else price + a5)
        stop = max(price + 1.0 * a5, min(stop_ref + 0.25 * a5, price + 2.5 * a5))
        tgt_lvl = sup
    risk_pts = abs(price - stop)
    room = abs(tgt_lvl["price"] - price) if tgt_lvl else 3 * risk_pts
    # Aim at the next level, never past it: if that is under 1.5R the trade is gated off below.
    target_pts = room
    target = price + direction * target_pts
    rr = target_pts / risk_pts if risk_pts else 0

    # ---------- gates ----------
    gates = []
    threshold = BASE_THRESHOLD
    t = (now or df5.index[-1].to_pydatetime()).time()
    if session:
        if session.get("phase") == "midday_chop":
            threshold = 0.45
        if session.get("is_expiry_day") and t >= time(13, 30):
            threshold = 0.5
        if not session.get("can_enter"):
            gates.append("Outside the entry window (09:30-15:00 on a trading day). This is the lean for when the market opens, not a live entry.")
    if abs(score) < threshold:
        gates.append(f"Signals are not aligned enough (score {abs(score):.2f} < {threshold:.2f} needed). Mixed evidence = no edge.")
    if factors["trend"] * direction < -0.25:
        gates.append("This would be against the 15-minute trend. Counter-trend option buys lose to time decay most of the time.")
    if t_info and t_info.get("adx", 30) < 15 and not bos:
        gates.append("No trend and no breakout: choppy market where option buyers bleed premium.")
    # Entry trigger: something must HAPPEN now (not just "trend is up") - avoids buying the middle of a move.
    prev_close = float(df5["close"].iloc[-2])
    triggers = []
    if bos and bos["direction"] == direction and (prev_close - bos["level"]) * direction <= 0:
        triggers.append(f"fresh {bos['kind']} through {bos['level']:.0f}")
    if any(("broke above" in x and direction > 0) or ("broke below" in x and direction < 0) for x in l_txt):
        triggers.append("fresh level breakout")
    fresh = [p for p in pats if p.direction == direction and df5.index.get_loc(pd.Timestamp(p.time)) >= len(df5) - 2
             and p.name != "Inside Bar" and (p.kind == "continuation" or (sup if direction > 0 else res) is not None
             and abs(price - (sup if direction > 0 else res)["price"]) <= 0.6 * a5)]
    triggers += [p.name for p in fresh]
    if not triggers:
        gates.append("No fresh entry trigger yet (breakout, structure break, or reversal candle at a level). "
                     "The direction is fine but there is nothing to act on - wait for the trigger candle.")
    ema9 = m_info.get("ema9")
    if ema9 and abs(price - ema9) > 1.5 * a5 and (price - ema9) * direction > 0:
        gates.append("Price is stretched far from its 9 EMA - chasing here usually means buying the top. Wait for a pullback.")
    if rr < MIN_REWARD_RISK:
        gates.append(f"Not enough room to the next {'resistance' if direction > 0 else 'support'}: reward is only {rr:.1f}x the risk (need {MIN_REWARD_RISK}x).")

    verdict = ("BUY" if direction > 0 else "SELL") if not gates else "NO TRADE"
    lean = "BUY" if direction > 0 else "SELL" if direction < 0 else "NEUTRAL"

    bull = [r["factor"] for r in reasons if r["signal"] == "bullish"]
    bear = [r["factor"] for r in reasons if r["signal"] == "bearish"]
    if verdict == "BUY":
        headline = "BUY - buy a Call (CE). Buyers are in control."
    elif verdict == "SELL":
        headline = "SELL - buy a Put (PE). Sellers are in control."
    else:
        headline = f"NO TRADE - leaning {lean}, but not clean enough to risk money."
    summary = (f"{len(bull)} factor(s) point up ({', '.join(bull) or 'none'}) and {len(bear)} point down "
               f"({', '.join(bear) or 'none'}). Overall score {score:+.2f} on a -1 to +1 scale.")

    return {
        "verdict": verdict, "lean": lean, "score": round(score, 3), "confidence": round(min(1.0, abs(score) / 0.7), 2),
        "headline": headline, "summary": summary, "gates": gates, "reasons": reasons,
        "factors": {k: round(v, 3) for k, v in factors.items()}, "weights": WEIGHTS, "triggers": triggers,
        "price": round(price, 2), "atr": round(a5, 2), "bar_time": df5.index[-1].isoformat(),
        "plan": {"direction": direction, "entry": round(price, 2), "stop": round(stop, 2), "target": round(target, 2),
                 "risk_points": round(risk_pts, 2), "target_points": round(target_pts, 2), "reward_risk": round(rr, 2)},
        "indicators": {**t_info, **m_info},
        "patterns": [p.dict() for p in C.detect(df5, lookback=12)],
        "anatomy": anat,
        "structure": {"swings": piv[-12:], "trend": s_dir, "text": s_txt, "bos": bos, "fvgs": S.fair_value_gaps(df5)},
        "levels": sorted(levels, key=lambda lv: lv["price"]),
        "support": sup, "resistance": res,
    }
