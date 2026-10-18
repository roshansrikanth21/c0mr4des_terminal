"""Global cues that move Indian indices indirectly (free Yahoo symbols)."""
from __future__ import annotations

from .data import get_quote_series

# symbol, label, sign (+1 = rising is good for NIFTY), why
CUES = [
    ("ES=F", "S&P 500 futures", 1, "US risk mood carries into Asian/Indian open"),
    ("NQ=F", "Nasdaq futures", 1, "Tech mood; matters for Infosys/TCS"),
    ("^N225", "Nikkei 225", 1, "Asian session mood"),
    ("^HSI", "Hang Seng", 1, "Asian session mood"),
    ("BZ=F", "Brent crude", -1, "India imports ~85% of its oil"),
    ("INR=X", "USD/INR", -1, "Rising = weaker rupee = FII outflows"),
    ("DX-Y.NYB", "Dollar index", -1, "Strong dollar pressures emerging markets"),
    ("^TNX", "US 10Y yield", -1, "Higher yields pull money out of India"),
    ("GC=F", "Gold", -1, "Gold up often = risk-off"),
]


def india_vix() -> dict | None:
    df = get_quote_series("^INDIAVIX", "1mo", "1d")
    if df is None or df.empty:
        return None
    v = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else v
    if v < 12:
        regime, text = "low", "India VIX is low: calm market, small moves, option premiums cheap."
    elif v < 17:
        regime, text = "normal", "India VIX is normal: regular intraday swings."
    elif v < 22:
        regime, text = "elevated", "India VIX is elevated: bigger swings, options are pricier, use tighter size."
    else:
        regime, text = "high", "India VIX is high: fear in the market, violent moves both ways. Trade small or sit out."
    return {"value": round(v, 2), "change_pct": round((v / prev - 1) * 100, 2), "regime": regime, "text": text,
            "percentile_1m": round(float((df["close"] <= v).mean() * 100), 0)}


def global_cues() -> dict:
    rows, score, n = [], 0.0, 0
    for sym, label, sign, why in CUES:
        df = get_quote_series(sym, "5d", "1d")
        if df is None or len(df) < 2:
            rows.append({"symbol": sym, "label": label, "available": False})
            continue
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        chg = (last / prev - 1) * 100
        effect = sign * (1 if chg > 0.25 else -1 if chg < -0.25 else 0)
        score += effect
        n += 1
        rows.append({"symbol": sym, "label": label, "available": True, "last": round(last, 2),
                     "change_pct": round(chg, 2), "effect": effect, "why": why})
    bias = score / n if n else 0.0
    mood = "supportive" if bias > 0.2 else "negative" if bias < -0.2 else "mixed"
    return {"bias": round(bias, 2), "text": f"Global cues are {mood} for Indian markets.", "cues": rows}
