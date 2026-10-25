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


MAX_LOTS = 4  # hard cap: a cheap premium must never turn one signal into a huge position


def plan_trade(key: str, direction: int, spot: float, expiry: date, vix: float | None, stop_points: float,
               target_points: float, risk: dict, chain: list[dict] | None = None, now: datetime | None = None,
               otm_steps: int | None = None) -> dict | None:
    """Pick strike (ATM, or 1 step ITM when expiry is close), estimate premium, size the position."""
    if direction == 0:
        return None
    inst = INSTRUMENTS[key]
    kind = "CE" if direction > 0 else "PE"
    atm = round(spot / inst.strike_step) * inst.strike_step
    T = years_to_expiry(expiry, now)
    if otm_steps is not None:
        # Strike test (2y NIFTY, first-hour breakout): 1 step OTM had the best profit factor (1.45 vs 1.41 ATM),
        # smaller average loss and lower risk of ruin for small accounts.
        strike = atm + direction * otm_steps * inst.strike_step
    else:
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
    lots = max(0, min(lots, affordable, MAX_LOTS))
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


def _liquid_strike(chain: list[dict] | None, atm: float, direction: int, inst, otm_steps: int) -> float:
    """The strike an owner would actually get filled on: near OTM, with the most open interest.

    Without a live chain we cannot see liquidity, so we fall back to the plain OTM step.
    """
    default = atm + direction * otm_steps * inst.strike_step
    if not chain:
        return default
    kind = "CE" if direction > 0 else "PE"
    lo, hi = atm - 2 * inst.strike_step, atm + 3 * inst.strike_step
    side = [r for r in chain if lo <= r["strike"] <= hi
            and ((r["strike"] >= atm) if direction > 0 else (r["strike"] <= atm))]
    if not side:
        return default
    def rank(r):
        leg = r.get(kind) or {}
        return (leg.get("oi") or 0, leg.get("volume") or 0)
    best = max(side, key=rank)
    return float(best["strike"]) if rank(best) != (0, 0) else default


def quote_both_sides(key: str, spot: float, expiry: date, vix: float | None, risk: dict,
                     chain: list[dict] | None = None, now: datetime | None = None,
                     otm_steps: int = 1) -> dict:
    """Price the CALL and the PUT an owner could buy today, side by side, and say which one fits.

    Two things this makes visible that a single ticket cannot:

    * Calls and puts are not symmetric. On the same day the put can cost 50% more than the
      call: it might be nearer the money, and Indian index options carry a put skew because
      big players buy downside protection. You cannot compare "a call" with "a put" unless
      you compare strikes at the same distance from spot.
    * A long option's worst case is the WHOLE premium, not the premium minus the stop. The
      stop only caps the loss if it fills.
    """
    inst = INSTRUMENTS[key]
    atm = round(spot / inst.strike_step) * inst.strike_step
    T = years_to_expiry(expiry, now)
    sigma = (vix or 14) / 100
    capital = float(risk.get("capital") or 0)
    lot = inst.lot_size
    sides: dict[str, dict] = {}

    for kind, direction in (("CE", 1), ("PE", -1)):
        strike = _liquid_strike(chain, atm, direction, inst, otm_steps)
        est = bs(spot, strike, T, sigma, kind)
        premium, source = est["price"], "estimated (Black-Scholes using India VIX)"
        row = next((r for r in (chain or []) if r["strike"] == strike), None)
        leg = (row or {}).get(kind) or {}
        if leg.get("ltp"):
            premium = float(leg["ltp"])
            source = "live (Angel One)"
            iv = implied_vol(premium, spot, strike, T, kind)
            if iv:
                est = bs(spot, strike, T, iv, kind) | {"iv": iv}
        premium = max(float(premium), 0.05)
        dist = strike - spot
        itm = (dist < 0) if kind == "CE" else (dist > 0)
        cost = premium * lot
        charges = round_trip_cost(premium, lot)
        sides["call" if kind == "CE" else "put"] = {
            "side": f"BUY {kind}", "option_type": kind, "strike": strike,
            "symbol_hint": f"{inst.key} {expiry.strftime('%d %b').upper()} {int(strike)} {kind}",
            "expiry": expiry.isoformat(),
            "moneyness": "ITM" if itm else ("ATM" if abs(dist) < inst.strike_step / 2 else "OTM"),
            "distance_points": round(dist, 1),
            "premium": round(premium, 2), "premium_source": source,
            "lot_size": lot, "lot_cost": round(cost, 2),
            "charges_round_trip": round(charges, 2),
            "worst_case": round(cost + charges, 2),
            "affordable": bool(capital and cost <= capital),
            "pct_of_capital": round(cost / capital * 100, 1) if capital else None,
            "delta": round(est.get("delta", 0), 3),
            "theta_per_lot_per_day": round(abs(est.get("theta_per_day", 0)) * lot, 2),
            "breakeven": round(strike + premium if kind == "CE" else strike - premium, 2),
            "iv": est.get("iv"),
            "oi": leg.get("oi"), "volume": leg.get("volume"),
        }

    explain: list[str] = []
    c, p = sides["call"], sides["put"]
    if c["premium"] > p["premium"] * 1.25:
        explain.append(f"The call is {c['premium'] / p['premium']:.2f}x the put. Calls are pricing "
                       f"more risk on the upside.")
    elif p["premium"] > c["premium"] * 1.25:
        explain.append(f"The put is {p['premium'] / c['premium']:.2f}x the call. That is put skew: "
                       f"big players pay up for downside protection, and the market expects sharper "
                       f"falls than rallies.")
    else:
        explain.append("The call and the put cost about the same, so the market is not leaning "
                       "either way on volatility.")
    explain.append(f"One lot is premium x {lot}. The premium changes every day with how far the "
                   f"strike sits from spot, how many days are left, and India VIX - that is why your "
                   f"one-lot cost moves between about 6k and 10k from day to day.")
    explain.append(f"These contracts lose roughly Rs {c['theta_per_lot_per_day']:,.0f} (call) and "
                   f"Rs {p['theta_per_lot_per_day']:,.0f} (put) of value per day to time decay, "
                   f"before the index moves at all.")

    fits = [k for k, v in sides.items() if v["affordable"]]
    if len(fits) == 2:
        text = (f"You can afford either side: call Rs {c['lot_cost']:,.0f}, "
                f"put Rs {p['lot_cost']:,.0f}.")
    elif len(fits) == 1:
        other = "put" if fits[0] == "call" else "call"
        text = (f"You can only afford the {fits[0]}: Rs {sides[fits[0]]['lot_cost']:,.0f}. "
                f"The {other} one lot costs Rs {sides[other]['lot_cost']:,.0f}, which is more than "
                f"your capital - so a {'bearish' if other == 'put' else 'bullish'} trade is not "
                f"available to you today, however good the setup looks.")
    else:
        text = (f"Neither side fits: the call needs Rs {c['lot_cost']:,.0f} and the put "
                f"Rs {p['lot_cost']:,.0f}, against Rs {capital:,.0f} of capital.")

    return {"call": c, "put": p, "affordable": fits, "explain": explain, "text": text,
            "capital": capital, "expiry": expiry.isoformat(), "spot": round(spot, 2), "atm": atm}
