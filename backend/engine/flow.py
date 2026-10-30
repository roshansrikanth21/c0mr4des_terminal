"""Who is actually paying for the move: option-chain flow, order-book pressure, and the
volume that confirms or denies a breakout.

Three limits, stated here because the UI repeats them:

1. NIFTY and SENSEX SPOT candles carry zero volume on both feeds (see data.py). So "volume"
   here is the OPTION CHAIN's traded volume and open interest, never the index's.
2. The order book is RESTING liquidity - bid quantity vs ask quantity. It is not executed
   buying, and one large order can fake it. It is labelled pressure and gets the smallest weight.
3. There is no historical chain/OI/order-book feed in this project, so this read CANNOT be
   backtested. It is recorded on every paper entry and judged forward, like the decision model.

The read never blocks a trade. It explains one.

How the chain bias is built (kept deliberately small and transparent):

    volume skew   more calls traded than puts during a rise = buyers leaning long. Once two
                  snapshots exist, the volume traded BETWEEN them is used, not the cumulative day.
    OI change     OI only counts when it CONFIRMS the price move:
                    price up   + call OI up   -> longs adding        (bullish)
                    price down + put OI up    -> longs adding        (bearish)
                  the opposite combinations are ambiguous (writing vs hedging) and score 0

Weights: timeframes 0.50, chain flow 0.35, order book 0.15. A missing component is dropped
and the rest renormalised, never invented.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("engine.flow")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FLOW_FILE = DATA_DIR / "flow_snapshots.json"
SNAP_GAP = 240      # seconds between snapshots: dense enough for a 5m delta, cheap enough to write
KEEP = 120          # ~8 hours of session at that spacing
MAX_BIAS = 0.8      # the chain alone may never claim certainty

_LOCK = threading.RLock()
_STATE: dict | None = None


# ---------------------------------------------------------------- snapshots
def _load() -> dict:
    global _STATE
    if _STATE is not None:
        return _STATE
    try:
        _STATE = json.loads(FLOW_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _STATE = {}
    except Exception as exc:  # noqa: BLE001
        log.warning("flow snapshots unreadable (%s) - starting fresh", exc)
        _STATE = {}
    return _STATE


def _save() -> None:
    try:
        FLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FLOW_FILE.with_name(FLOW_FILE.name + ".tmp")
        tmp.write_text(json.dumps(_STATE, separators=(",", ":")), encoding="utf-8")
        tmp.replace(FLOW_FILE)
    except Exception as exc:  # noqa: BLE001 - a snapshot is a nicety, never a reason to stop trading
        log.warning("flow snapshot write failed: %s", exc)


def _leg_map(chain: list[dict] | None) -> dict[str, dict]:
    """{strike+kind: {oi, vol}} so deltas compare the SAME contracts as the window rolls."""
    out: dict[str, dict] = {}
    for row in chain or []:
        for kind in ("CE", "PE"):
            leg = row.get(kind)
            if not leg:
                continue
            out[f"{int(row['strike'])}{kind}"] = {"oi": int(leg.get("oi") or 0),
                                                 "vol": int(leg.get("volume") or 0)}
    return out


def _totals(legs: dict[str, dict]) -> dict:
    ce_oi = sum(v["oi"] for k, v in legs.items() if k.endswith("CE"))
    pe_oi = sum(v["oi"] for k, v in legs.items() if k.endswith("PE"))
    ce_vol = sum(v["vol"] for k, v in legs.items() if k.endswith("CE"))
    pe_vol = sum(v["vol"] for k, v in legs.items() if k.endswith("PE"))
    return {"ce_oi": ce_oi, "pe_oi": pe_oi, "ce_vol": ce_vol, "pe_vol": pe_vol}


def snapshot(key: str, expiry: date, chain: list[dict] | None, spot: float,
             now: datetime, persist: bool = True) -> dict | None:
    """Store this chain's totals (throttled) and return the previous snapshot, if any.

    The previous snapshot is the newest one at least SNAP_GAP seconds old, so the delta covers
    a real interval rather than two ticks 15 seconds apart.
    """
    legs = _leg_map(chain)
    if not legs:
        return None
    bucket = f"{key}|{expiry.isoformat()}"
    ts = now.timestamp()
    with _LOCK:
        state = _load()
        rows = state.setdefault(bucket, [])
        prev = next((r for r in reversed(rows) if ts - float(r.get("t") or 0) >= SNAP_GAP), None)
        newest = rows[-1] if rows else None
        if persist and (newest is None or ts - float(newest.get("t") or 0) >= SNAP_GAP):
            rows.append({"t": round(ts, 1), "spot": round(float(spot), 2), "legs": legs})
            del rows[:-KEEP]
            _save()
    return prev


def _deltas(legs: dict[str, dict], prev: dict | None) -> dict:
    """Change in OI and volume over the contracts present in BOTH snapshots."""
    if not prev:
        return {"ce_doi": 0, "pe_doi": 0, "ce_dvol": 0, "pe_dvol": 0, "n": 0}
    old = prev.get("legs") or {}
    common = [k for k in legs if k in old]
    ce_doi = sum(legs[k]["oi"] - old[k]["oi"] for k in common if k.endswith("CE"))
    pe_doi = sum(legs[k]["oi"] - old[k]["oi"] for k in common if k.endswith("PE"))
    ce_dvol = sum(max(legs[k]["vol"] - old[k]["vol"], 0) for k in common if k.endswith("CE"))
    pe_dvol = sum(max(legs[k]["vol"] - old[k]["vol"], 0) for k in common if k.endswith("PE"))
    return {"ce_doi": ce_doi, "pe_doi": pe_doi, "ce_dvol": ce_dvol, "pe_dvol": pe_dvol,
            "n": len(common)}


# ---------------------------------------------------------------- order book
def _book(leg: dict | None) -> dict | None:
    """Resting bid vs ask quantity on one option leg. None when the feed has no depth."""
    if not leg:
        return None
    bid_qty, ask_qty = leg.get("bid_qty"), leg.get("ask_qty")
    if bid_qty is None and ask_qty is None:
        return None
    bid_qty, ask_qty = float(bid_qty or 0), float(ask_qty or 0)
    if bid_qty + ask_qty <= 0:
        return None
    imb = (bid_qty - ask_qty) / (bid_qty + ask_qty)
    bid, ask = leg.get("bid"), leg.get("ask")
    spread_pct = None
    if bid and ask and bid > 0 and ask > 0:
        spread_pct = round((ask - bid) / ((ask + bid) / 2) * 100, 2)
    return {"bid_qty": int(bid_qty), "ask_qty": int(ask_qty), "imbalance": round(imb, 3),
            "bid": bid, "ask": ask, "spread_pct": spread_pct}


def book_bias(leg: dict | None, option_type: str) -> dict | None:
    """Signed bullish pressure. A bid-heavy CALL book is call buyers; a bid-heavy PUT book is
    put buyers, which is bearish. Half weight because this is queue, not trades."""
    b = _book(leg)
    if not b:
        return None
    signed = b["imbalance"] if option_type == "CE" else -b["imbalance"]
    return {**b, "bias": round(signed * 0.5, 3)}


# ---------------------------------------------------------------- the read
def _verdict(x: float) -> str:
    return "bullish" if x > 0.15 else "bearish" if x < -0.15 else "flat"


def _chain_bias(tot: dict, d: dict, spot: float, prev: dict | None) -> tuple[float, dict]:
    """Directional read of the chain, capped at MAX_BIAS. OI only counts with price."""
    ce_vol, pe_vol = tot["ce_vol"], tot["pe_vol"]
    # Cumulative day volume is dominated by the morning. When two snapshots exist, use the volume
    # traded BETWEEN them, which is the flow behind the current move; fall back to cumulative.
    window = bool(prev) and (d.get("ce_dvol", 0) + d.get("pe_dvol", 0)) > 0
    ce_flow, pe_flow = (d.get("ce_dvol", 0), d.get("pe_dvol", 0)) if window else (ce_vol, pe_vol)
    vol_skew = (pe_flow - ce_flow) / max(pe_flow + ce_flow, 1)
    vol_bias = -vol_skew                      # more calls traded = buyers leaning long
    doi_bias, dprice = 0.0, 0.0
    if prev:
        dprice = float(spot) - float(prev.get("spot") or spot)
        denom = max(abs(d["ce_doi"]) + abs(d["pe_doi"]), 1)
        if dprice > 0:
            doi_bias = max(d["ce_doi"], 0) / denom
        elif dprice < 0:
            doi_bias = -max(d["pe_doi"], 0) / denom
    bias = max(-MAX_BIAS, min(MAX_BIAS, 0.65 * vol_bias + 0.35 * doi_bias))
    return bias, {"vol_skew": round(vol_skew, 3), "vol_bias": round(vol_bias, 3),
                  "doi_bias": round(doi_bias, 3), "dprice": round(dprice, 2),
                  "vol_window": "delta" if window else "cumulative"}


def _text(tot: dict, cb: dict, mtf_bias: float, prev: bool) -> str:
    ce, pe = tot["ce_vol"], tot["pe_vol"]
    total = max(ce + pe, 1)
    call_share = ce / total * 100
    side = "calls" if call_share >= 50 else "puts"
    first = (f"{side.title()} are {max(call_share, 100 - call_share):.0f}% of chain volume "
             f"({ce:,} vs {pe:,})")
    if not prev:
        return first + ". No earlier snapshot yet, so open-interest change is not counted."
    oi = ""
    if cb["ce_doi"] or cb["pe_doi"]:
        oi = (f"; since the last snapshot call OI {cb['ce_doi']:+,} and put OI {cb['pe_doi']:+,} "
              f"while spot moved {cb['dprice']:+.0f}")
    trend = (" Timeframes point up." if mtf_bias > 0.12 else
             " Timeframes point down." if mtf_bias < -0.12 else " Timeframes are flat.")
    return first + oi + "." + trend


def market(key: str, chain: list[dict] | None, ladder: dict | None, spot: float,
           now: datetime, expiry: date, persist: bool = True) -> dict:
    """The direction-agnostic flow read. Safe with no chain: says so instead of guessing."""
    base = {"available": False, "bias": 0.0, "verdict": "no data", "confidence": 0.0,
            "components": {"mtf": round(float((ladder or {}).get("bias") or 0.0), 3), "chain": 0.0},
            "chain": None,
            "text": "No live option chain, so there is no flow to read.",
            "caveats": [
                "Index spot volume is zero on both feeds - flow is inferred from the option chain.",
                "Order-book pressure is resting orders, not executed trades; one large order can fake it.",
                "No historical chain data: this read is recorded forward, never backtested.",
            ]}
    legs = _leg_map(chain)
    if not legs:
        return base
    prev = snapshot(key, expiry, chain, spot, now, persist=persist)
    tot = _totals(legs)
    d = _deltas(legs, prev)
    cb, detail = _chain_bias(tot, d, spot, prev)
    mtf_bias = float((ladder or {}).get("bias") or 0.0)
    # Same 0.50 / 0.35 weights as trade(), renormalised because there is no book at market level.
    bias = max(-1.0, min(1.0, (0.50 * mtf_bias + 0.35 * cb) / 0.85))
    same = (mtf_bias > 0.12 and cb > 0.05) or (mtf_bias < -0.12 and cb < -0.05)
    confidence = 0.8 if same else 0.45
    if not prev:
        confidence *= 0.8
    pcr = round(tot["pe_oi"] / tot["ce_oi"], 2) if tot["ce_oi"] else None
    vol_pcr = round(tot["pe_vol"] / tot["ce_vol"], 2) if tot["ce_vol"] else None
    return {
        "available": True, "bias": round(bias, 3), "verdict": _verdict(bias),
        "confidence": round(confidence, 2),
        "components": {"mtf": round(mtf_bias, 3), "chain": round(cb, 3)},
        "chain": {**tot, "pcr_oi": pcr, "pcr_vol": vol_pcr, **detail, **d,
                  "spot": round(float(spot), 2)},
        "text": _text(tot, {**detail, **d}, mtf_bias, bool(prev)),
        "caveats": base["caveats"],
    }


def trade(read: dict, direction: int, option: dict | None, chain: list[dict] | None) -> dict | None:
    """How the flow reads FOR THIS TRADE. +1 fully supports it, -1 is fully against it."""
    if not read or not read.get("available") or not direction or not option:
        return None
    strike, kind = option.get("strike"), option.get("option_type")
    row = next((r for r in chain or [] if float(r.get("strike") or 0) == float(strike)), None)
    b = book_bias((row or {}).get(kind), kind) if row else None
    parts = [("mtf", read["components"]["mtf"], 0.50),
             ("chain", read["components"]["chain"], 0.35)]
    if b:
        parts.append(("book", b["bias"], 0.15))
    wsum = sum(w for _, _, w in parts)
    support = sum(v * w for _, v, w in parts) / wsum * direction
    verdict = "supports" if support >= 0.30 else "against" if support <= -0.30 else "mixed"
    label = "long call" if direction > 0 else "long put"
    if verdict == "supports":
        head = f"Flow supports the {label}"
    elif verdict == "against":
        head = f"Flow is AGAINST the {label}"
    else:
        head = f"Flow is mixed for the {label}"
    bits = [f"{n} {v:+.2f}" for n, v, _ in parts]
    text = f"{head}: " + ", ".join(bits) + f" -> net {support:+.2f}."
    if b and b.get("spread_pct") is not None and b["spread_pct"] > 1.5:
        text += f" The book is wide ({b['spread_pct']:.1f}%), so expect slippage."
    return {"support": round(support, 3), "verdict": verdict, "book": b, "text": text,
            "direction": direction, "strike": strike, "option_type": kind}
