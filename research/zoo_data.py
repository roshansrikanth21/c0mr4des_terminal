"""Build one compact cache of the real NIFTY data for the strategy zoo.

Per trading day: the 5-minute index bars and, for every bar, the real option close for each strike that was
downloaded (rolling ATM-7..ATM+7, calls and puts), plus the ATM strike and ATM implied volatility.

    python research/zoo_data.py        ->  data/zoo_cache.pkl
"""
from __future__ import annotations

import json
import pickle
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "data"
IST = timezone(timedelta(hours=5, minutes=30))
CACHE = ROOT / "zoo_cache.pkl"
TUESDAY_FROM = date(2025, 9, 1)     # NIFTY weekly expiry moved from Thursday to Tuesday


def minutes(ts: float) -> int:
    dt = datetime.fromtimestamp(ts, IST)
    return dt.hour * 60 + dt.minute


def expiry_map(days: list[date]) -> dict[date, date]:
    """Next weekly expiry on/after each trading day; a holiday expiry moves to the previous trading day."""
    have = set(days)
    out = {}
    for d in days:
        c = d
        for _ in range(4):
            wd = 1 if c >= TUESDAY_FROM else 3
            cand = c + timedelta(days=(wd - c.weekday()) % 7)
            exp = cand
            while exp not in have and exp > d - timedelta(days=1):
                exp -= timedelta(days=1)
            if exp >= d and exp in have:
                out[d] = exp
                break
            c = cand + timedelta(days=1)
        else:
            out[d] = d
    return out


def build() -> dict:
    names = sorted(p.stem for p in (ROOT / "dhan_strikes").glob("20*.json"))
    days = {}
    for n in names:
        try:
            s = json.loads((ROOT / "dhan_spot5m" / f"{n}.json").read_text())
            e = json.loads((ROOT / "dhan_expired" / f"{n}.json").read_text())
            k = json.loads((ROOT / "dhan_strikes" / f"{n}.json").read_text())
        except FileNotFoundError:
            continue
        t = [minutes(x) for x in s["timestamp"]]
        keep = [i for i, m in enumerate(t) if 555 <= m <= 925]
        if len(keep) < 60:
            continue
        pos = {t[i]: j for j, i in enumerate(keep)}
        nb = len(keep)
        ce = [dict() for _ in range(nb)]
        pe = [dict() for _ in range(nb)]
        atm = np.full(nb, np.nan)
        iv = np.full(nb, np.nan)
        for side, book in (("ce", ce), ("pe", pe)):
            series = [e.get(side)] + list((k.get(side) or {}).values())
            for n_ser, ser in enumerate(series):
                if not ser:
                    continue
                ivs = ser.get("iv") or []
                for i, ts in enumerate(ser["timestamp"]):
                    j = pos.get(minutes(ts))
                    st, cl = ser["strike"][i], ser["close"][i]
                    if j is None or not st or not cl:
                        continue
                    book[j][float(st)] = float(cl)
                    if n_ser == 0:
                        atm[j] = float(st)
                        if i < len(ivs) and ivs[i]:
                            iv[j] = ivs[i] if np.isnan(iv[j]) else (iv[j] + ivs[i]) / 2
        for arr in (atm, iv):                      # carry the last known value over gaps
            last = np.nan
            for j in range(nb):
                if np.isnan(arr[j]):
                    arr[j] = last
                else:
                    last = arr[j]
        days[date.fromisoformat(n)] = {
            "t": np.array([t[i] for i in keep]), "o": np.array([s["open"][i] for i in keep], float),
            "h": np.array([s["high"][i] for i in keep], float), "l": np.array([s["low"][i] for i in keep], float),
            "c": np.array([s["close"][i] for i in keep], float), "ce": ce, "pe": pe, "atm": atm, "iv": iv}
    exp = expiry_map(sorted(days))
    for d, v in days.items():
        v["expiry"] = exp[d]
    return days


def load() -> dict:
    if not CACHE.exists():
        CACHE.write_bytes(pickle.dumps(build(), protocol=4))
    return pickle.loads(CACHE.read_bytes())


if __name__ == "__main__":
    if CACHE.exists():
        CACHE.unlink()
    D = load()
    ds = sorted(D)
    print(f"days {len(ds)} ({ds[0]} .. {ds[-1]}), cache {CACHE.stat().st_size / 1e6:.0f} MB")
    exp_days = [d for d in ds if D[d]["expiry"] == d]
    tv = []
    for d in ds:
        v = D[d]
        j = len(v["c"]) - 2
        k0 = v["atm"][j]
        c, p = v["ce"][j].get(k0), v["pe"][j].get(k0)
        if c and p:
            tv.append((d in exp_days, (c + p - abs(v["c"][j] - k0)) / v["c"][j] * 100))
    on = [x for e, x in tv if e]
    off = [x for e, x in tv if not e]
    print(f"expiry days flagged {len(exp_days)} | ATM time value at 15:20 as % of spot: expiry days median {np.median(on):.3f}, other days median {np.median(off):.3f}")
    print("weekday of flagged expiries by year:", {y: sorted({d.strftime('%a') for d in exp_days if d.year == y}) for y in range(2021, 2027)})
    full = np.mean([len(D[d]["ce"][30]) for d in ds])
    print(f"average strikes available per bar (calls): {full:.1f}")
