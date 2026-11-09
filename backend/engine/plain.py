"""Plain-language CALL or PUT read (owner, 9 Nov, on the Angel One screenshot:
"no i dont want a copy i want it to be bale to tell me in more simper terms on
wether to call or put and it should have indicators and anaylze maaarket trednds").

It invents nothing: every word is a translation of numbers the engine already
scored, in simple words.
- choice: CALL / PUT when the headline score points that way, TOO MIXED when it
  is genuinely balanced; confidence is the engine's own 0..1 strength in %.
- go/wait: the owner's own entry bar, evaluated with the SAME `trader.entry_evidence`
  the live paper trader runs (score clears the floor in the trade's direction +
  multi-timeframe read aligned, the daily row included - the owner asked for
  "identifying trends based on the DAILY MARKET highs and lows"). Where it does
  not pass, wait_reason says why in one plain sentence.
- bullets: daily highs/lows structure first (the owner's daily read), then the
  15-minute trend with ADX, RSI momentum, the level position in plain POINTS
  (not ATR - jargon was the complaint), and the newest candle pattern.
- chips: the indicator row at a glance (trend, ADX state, RSI, Supertrend, MTF).
Nothing here decides a trade and nothing here gates one: it reads what exists.
"""
from __future__ import annotations

from datetime import datetime

from .predict import daily_read
from .trader import entry_evidence


def plain_read(result: dict, mtf: dict, daily, price: float, now: datetime,
               can_enter: bool, entry_min: float) -> dict:
    score = float(result.get("score") or 0.0)
    conf = int(round(float(result.get("confidence") or 0.0) * 100))
    ind = result.get("indicators") or {}
    factors = result.get("factors") or {}
    lean = "CALL" if score > 0 else "PUT" if score < 0 else "NEUTRAL"
    direction = 1 if score > 0 else (-1 if score < 0 else 0)

    # ---- GO or WAIT: the owner's own bar, the exact helper the trader runs ----
    wait_reason = None
    if not can_enter:
        wait_reason = "Market is closed or outside the entry window (09:30-15:00)."
    elif abs(score) < entry_min:
        wait_reason = (f"Signal is only {abs(score):.2f}; your rules want {entry_min:.2f} "
                       f"pointing one way before buying a {lean}. Mixed show = no edge.")
    elif not entry_evidence({"score": score, "mtf": mtf}, {"direction": direction}, entry_min):
        phase = (mtf or {}).get("phase") or "unclear"
        wait_reason = (f"Timeframes do not agree yet (read: {phase}). Before buying a {lean}, "
                       f"the daily read and the shorter ones have to pull the same way.")
    go = wait_reason is None

    # ---- plain bullets, daily highs/lows first (the owner's own read) ----
    bullets: list[str] = []
    daily_d = daily_read(daily, price, now.date()) if daily is not None else None
    if daily_d and daily_d.get("text"):
        bullets.append(daily_d["text"])

    adx = float(ind.get("adx") or 0.0)
    t = float(factors.get("trend") or 0.0)
    if adx:
        trend_word = "up" if t > 0.15 else "down" if t < -0.15 else "sideways"
        strength = "clean" if adx >= 25 else "soft" if adx >= 18 else "choppy"
        bullets.append(f"15-minute trend {trend_word} and {strength} (ADX {adx:.0f}): "
                       f"price {'above' if t > 0.15 else 'below' if t < -0.15 else 'at'} the short averages.")

    rsi = float(ind.get("rsi") or 0.0)
    if rsi:
        bullets.append(f"RSI {rsi:.0f} - "
                       f"{'buyers stronger' if rsi > 55 else 'sellers stronger' if rsi < 45 else 'neither side is pressing'}.")

    sup, res = result.get("support"), result.get("resistance")
    if sup or res:
        bits = []
        if sup:
            bits.append(f"support {sup['name']} {sup['price']:,.0f} ({max(0.0, price - float(sup['price'])):,.0f} points below)")
        if res:
            bits.append(f"resistance {res['name']} {res['price']:,.0f} ({max(0.0, float(res['price']) - price):,.0f} points above)")
        bullets.append("Nearest " + "; ".join(bits) + ".")

    pat = next((p for p in (result.get("patterns") or []) if p.get("direction")), None)
    if pat:
        bullets.append(f"{pat['name']} on the last candles: {pat['meaning']}")

    # ---- one plain line ----
    drivers = []
    if t > 0.15:
        drivers.append("15-minute trend up")
    elif t < -0.15:
        drivers.append("15-minute trend down")
    if rsi > 55:
        drivers.append("buyers stronger")
    elif rsi < 45:
        drivers.append("sellers stronger")
    if (daily_d or {}).get("score", 0) and int(daily_d["score"]) > 0:
        drivers.append("daily making higher highs")
    elif (daily_d or {}).get("score", 0) and int(daily_d["score"]) < 0:
        drivers.append("daily making lower lows")
    line = (f"Leaning {lean} ({conf}% strength): " + " · ".join(drivers[:3]) + "."
            if drivers else
            f"Leaning {lean} ({conf}% strength) but nothing is pushing hard - the card stays cautious.")

    # ---- chips: indicator row at a glance ----
    chips = [{"k": "15m trend", "v": "UP" if t > 0.15 else "DOWN" if t < -0.15 else "FLAT",
              "tone": "up" if t > 0.15 else "down" if t < -0.15 else "flat"}]
    if adx:
        chips.append({"k": "ADX", "v": f"{adx:.0f} {'trending' if adx >= 25 else 'soft' if adx >= 18 else 'chop'}",
                      "tone": "up" if adx >= 25 and t != 0 else "flat"})
    if rsi:
        chips.append({"k": "RSI", "v": f"{rsi:.0f}", "tone": "up" if rsi > 55 else "down" if rsi < 45 else "flat"})
    st = int(ind.get("supertrend") or 0)
    if st:
        chips.append({"k": "Supertrend", "v": "green" if st > 0 else "red", "tone": "up" if st > 0 else "down"})
    phase = (mtf or {}).get("phase") or "unclear"
    chips.append({"k": "Timeframes", "v": phase,
                  "tone": "up" if phase == "aligned" else "down" if phase == "conflict" else "flat"})

    return {
        "choice": lean if abs(score) >= 0.15 else "TOO MIXED",
        "go": go, "wait_reason": wait_reason,
        "confidence": conf, "line": line, "bullets": bullets, "chips": chips,
    }
