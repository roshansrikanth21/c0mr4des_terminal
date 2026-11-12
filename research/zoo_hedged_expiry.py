"""Can the expiry-day short straddle run on less capital? The only way to cut the margin is to buy protection.

Hedged version: sell the ATM call and put at 09:20 on expiry day, buy a call `w` strikes above and a put `w` strikes
below. 30% stop on each short leg; when a short leg stops, ITS wing is sold with it (no orphan hedge left to decay).
Flat at 15:15. Real prints, lot 65, charges and 0.5% slippage on all four legs.
Wing width is chosen on 2021-2024 only and judged on 2025-2026.
"""
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from research import zoo_intraday as Z  # noqa: E402

days = [d for d in Z.prepare()[1:] if d.is_expiry]
LOT = Z.LOT


def trade(day, w, stop=0.30, i=0):
    k0 = day.raw["atm"][i]
    if k0 != k0:
        return None
    sides = {}
    for kind, sign in (("ce", 1), ("pe", -1)):
        s_in, real = Z.price(day, kind, k0, i)
        if not real or s_in < 1:
            return None
        wk = k0 + sign * w * Z.STEP
        w_in, w_real = (Z.price(day, kind, wk, i) if w else (0.0, True))
        sides[kind] = {"s_in": s_in, "w_in": w_in, "wk": wk, "open": True, "s_out": None, "w_out": None, "real": w_real}
    for b in range(i + 1, day.end + 1):
        last = b == day.end
        for kind, x in sides.items():
            if not x["open"]:
                continue
            p, _ = Z.price(day, kind, k0, b)
            if p >= x["s_in"] * (1 + stop) or last:
                x["s_out"] = p
                if w:
                    x["w_out"], r = Z.price(day, kind, x["wk"], b)
                    x["real"] = x["real"] and r
                x["open"] = False
        if not any(x["open"] for x in sides.values()):
            break
    pnl = 0.0
    for x in sides.values():
        pnl += Z.leg_pnl(-1, x["s_in"], x["s_out"])
        if w:
            pnl += Z.leg_pnl(1, x["w_in"], x["w_out"])
    credit = sum(x["s_in"] - x["w_in"] for x in sides.values())
    max_loss = (w * Z.STEP - credit) * LOT if w else None
    return {"date": str(day.date), "pnl": pnl, "max_loss": max_loss, "real": all(x["real"] for x in sides.values()),
            "wing_cost": sum(x["w_in"] for x in sides.values()) * LOT}


def stats(tr):
    p = np.array([t["pnl"] for t in tr])
    w, l = p[p > 0].sum(), -p[p <= 0].sum()
    eq = np.cumsum(p)
    return {"n": len(p), "win": 100 * (p > 0).mean(), "pf": w / l if l else 0, "net": p.sum(), "worst": p.min(),
            "dd": (eq - np.maximum.accumulate(eq)).min()}


def line(label, tr):
    s = stats(tr)
    yrs = {}
    for t in tr:
        yrs[t["date"][:4]] = yrs.get(t["date"][:4], 0) + t["pnl"]
    ml = [t["max_loss"] for t in tr if t["max_loss"] is not None]
    cap = f"defined max loss median Rs {np.median(ml):,.0f}, worst Rs {max(ml):,.0f}" if ml else "loss not capped"
    print(f"{label:22s} n {s['n']} win {s['win']:.0f}% PF {s['pf']:.2f} net {s['net']:9,.0f} worst day {s['worst']:8,.0f} maxDD {s['dd']:8,.0f}"
          f" | {' '.join(f'{y[2:]}:{v / 1000:+.0f}k' for y, v in sorted(yrs.items()))}")
    print(f"{'':22s} {cap} | wing cost median Rs {np.median([t['wing_cost'] for t in tr]):,.0f} | all prints real {100 * np.mean([t['real'] for t in tr]):.0f}%")
    return s


print("=== full period, for reference")
allr = {}
for w in (0, 2, 3, 4, 5, 6, 7):
    tr = [t for t in (trade(d, w) for d in days) if t]
    allr[w] = tr
    line("naked (no wings)" if not w else f"wings {w * 50} pts", tr)

print("\n=== pick the wing width on 2021-2024, judge on 2025-2026")
best, best_pf = None, 0
for w in (2, 3, 4, 5, 6, 7):
    s = stats([t for t in allr[w] if t["date"] < "2025-01-01"])
    print(f"  build wings {w * 50}: PF {s['pf']:.2f} net {s['net']:,.0f} maxDD {s['dd']:,.0f}")
    if s["pf"] > best_pf:
        best, best_pf = w, s["pf"]
print(f"  chosen on build: wings {best * 50} pts")
judge = [t for t in allr[best] if t["date"] >= "2025-01-01"]
line(f"JUDGE wings {best * 50}", judge)
line("JUDGE naked", [t for t in allr[0] if t["date"] >= "2025-01-01"])
