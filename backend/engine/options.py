"""Option pricing, strike selection, live chain (Angel One), costs and position sizing."""
from __future__ import annotations

import json
import logging
import math
import os
import time as _time
from datetime import date, datetime
from pathlib import Path

from .config import CHARGES, IST, INSTRUMENTS
from .data import angel

log = logging.getLogger("engine.options")
RISK_FREE = 0.065
SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
SCRIP_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "scrip_master.json"


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs(S: float, K: float, T: float, sigma: float, kind: str, r: float = RISK_FREE) -> dict:
    """Black-Scholes price and greeks. T in years, sigma annualised. theta per calendar day."""
    T = max(T, 1e-5)
    sigma = max(sigma, 1e-4)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == "CE":
        price = S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
        delta = _ncdf(d1)
        theta = -S * _npdf(d1) * sigma / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * _ncdf(d2)
    else:
        price = K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)
        delta = _ncdf(d1) - 1
        theta = -S * _npdf(d1) * sigma / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * _ncdf(-d2)
    return {
        "price": round(price, 2), "delta": round(delta, 3),
        "gamma": round(_npdf(d1) / (S * sigma * math.sqrt(T)), 6),
        "theta_per_day": round(theta / 365, 2), "vega": round(S * _npdf(d1) * math.sqrt(T) / 100, 2),
    }


def implied_vol(price: float, S: float, K: float, T: float, kind: str) -> float | None:
    intrinsic = max(0.0, S - K) if kind == "CE" else max(0.0, K - S)
    if price <= intrinsic + 0.05:
        return None
    lo, hi = 0.01, 3.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs(S, K, T, mid, kind)["price"] > price:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 4)


def years_to_expiry(expiry: date, now: datetime | None = None) -> float:
    now = now or datetime.now(IST)
    exp_dt = datetime(expiry.year, expiry.month, expiry.day, 15, 30, tzinfo=IST)
    return max((exp_dt - now).total_seconds(), 60) / (365 * 24 * 3600)


def expected_move(spot: float, vix: float | None, minutes: float) -> float | None:
    """1-sigma move over `minutes` of trading implied by India VIX (annualised %)."""
    if not vix:
        return None
    return spot * (vix / 100) * math.sqrt(minutes / (252 * 375))


def round_trip_cost(premium: float, qty: int) -> float:
    buy, sell = premium * qty, premium * qty
    ch = CHARGES
    brokerage = 2 * ch["brokerage_per_order"]
    exch = (buy + sell) * ch["exchange_txn"]
    sebi = (buy + sell) * ch["sebi_fee"]
    stt = sell * ch["stt_sell"]
    stamp = buy * ch["stamp_buy"]
    gst = (brokerage + exch + sebi) * ch["gst"]
    return round(brokerage + exch + sebi + stt + stamp + gst, 2)


# ---------------- live option chain (Angel One only) ----------------
_scrip: list | None = None


def _scrip_master() -> list:
    global _scrip
    if _scrip is not None:
        return _scrip
    try:
        if SCRIP_CACHE.exists() and _time.time() - SCRIP_CACHE.stat().st_mtime < 86400:
            _scrip = json.loads(SCRIP_CACHE.read_text())
            return _scrip
        import requests

        rows = requests.get(SCRIP_URL, timeout=60).json()
        keep = [r for r in rows if r.get("exch_seg") in ("NFO", "BFO") and r.get("instrumenttype") == "OPTIDX"
                and r.get("name") in ("NIFTY", "SENSEX")]
        SCRIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SCRIP_CACHE.write_text(json.dumps(keep))
        _scrip = keep
    except Exception as exc:  # noqa: BLE001
        log.warning("scrip master unavailable: %s", exc)
        _scrip = []
    return _scrip


def live_chain(key: str, expiry: date, spot: float, width: int = 6) -> list[dict] | None:
    """Real LTP/OI for strikes around ATM, or None when Angel One is not configured."""
    if not angel.configured():
        return None
    inst = INSTRUMENTS[key]
    exp_str = expiry.strftime("%d%b%Y").upper()
    atm = round(spot / inst.strike_step) * inst.strike_step
    wanted = {atm + i * inst.strike_step for i in range(-width, width + 1)}
    rows = [r for r in _scrip_master() if r.get("name") == inst.angel_name and r.get("expiry") == exp_str
            and r.get("exch_seg") == inst.option_exchange and float(r.get("strike", 0)) / 100 in wanted]
    if not rows:
        return None
    quotes = angel.ltp(inst.option_exchange, [r["token"] for r in rows])
    chain: dict[float, dict] = {}
    for r in rows:
        k = float(r["strike"]) / 100
        kind = "CE" if r["symbol"].endswith("CE") else "PE"
        q = quotes.get(str(r["token"]), {})
        chain.setdefault(k, {"strike": k})[kind] = {
            "symbol": r["symbol"], "token": r["token"], "ltp": q.get("ltp"), "oi": q.get("opnInterest"),
            "volume": q.get("tradeVolume"),
        }
    return [chain[k] for k in sorted(chain)]


def pcr(chain: list[dict] | None) -> float | None:
    if not chain:
        return None
    ce = sum((row.get("CE") or {}).get("oi") or 0 for row in chain)
    pe = sum((row.get("PE") or {}).get("oi") or 0 for row in chain)
    return round(pe / ce, 2) if ce else None


def plan_trade(key: str, direction: int, spot: float, expiry: date, vix: float | None, stop_points: float,
               target_points: float, risk: dict, chain: list[dict] | None = None, now: datetime | None = None) -> dict | None:
    """Pick strike (ATM, or 1 step ITM when expiry is close), estimate premium, size the position."""
    if direction == 0:
        return None
    inst = INSTRUMENTS[key]
    kind = "CE" if direction > 0 else "PE"
    atm = round(spot / inst.strike_step) * inst.strike_step
    T = years_to_expiry(expiry, now)
    itm_shift = 1 if T * 365 < 2 else 0  # near expiry, slightly ITM holds value better
    strike = atm - direction * itm_shift * inst.strike_step
    sigma = (vix or 14) / 100
    est = bs(spot, strike, T, sigma, kind)
    premium, source = est["price"], "estimated (Black-Scholes using India VIX)"
    if chain:
        row = next((r for r in chain if r["strike"] == strike), None)
        live = (row or {}).get(kind, {}).get("ltp") if row else None
        if live:
            premium, source = float(live), "live (Angel One)"
            iv = implied_vol(premium, spot, strike, T, kind)
            if iv:
                est = bs(spot, strike, T, iv, kind) | {"iv": iv}
    delta = abs(est["delta"]) or 0.5
    # Premium-side stop/target derived from underlying stop/target via delta (+gamma ignored, conservative).
    prem_stop = max(premium - delta * stop_points, premium * 0.5)
    prem_target = premium + delta * target_points
    risk_per_lot = (premium - prem_stop) * inst.lot_size
    budget = risk["capital"] * risk["risk_per_trade_pct"] / 100
    lots = int(budget // risk_per_lot) if risk_per_lot > 0 else 0
    affordable = int(risk["capital"] // (premium * inst.lot_size)) if premium > 0 else 0
    lots = max(0, min(lots, affordable))
    qty = lots * inst.lot_size
    cost = round_trip_cost(premium, max(qty, inst.lot_size))
    return {
        "side": f"BUY {kind}",
        "symbol_hint": f"{inst.key} {expiry.strftime('%d %b').upper()} {int(strike)} {kind}",
        "strike": strike, "option_type": kind, "expiry": expiry.isoformat(),
        "premium": round(premium, 2), "premium_source": source,
        "premium_stop": round(prem_stop, 2), "premium_target": round(prem_target, 2),
        "greeks": est, "lot_size": inst.lot_size, "lots": lots, "quantity": qty,
        "capital_needed": round(premium * qty, 2), "max_loss": round((premium - prem_stop) * qty + cost, 2),
        "charges_round_trip": cost,
        "note": ("Position size is 0 lots: your risk-per-trade budget is smaller than one lot's risk. "
                 "Raise capital/risk % in Settings or skip.") if lots == 0 else "",
    }
