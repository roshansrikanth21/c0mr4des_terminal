"""Strategy zoo, part 3: score all 50 strategies with one rulebook fixed before the results were seen.

Survive = net positive over 2021-2026 after costs, profitable in at least 4 of the 6 calendar years, and a maximum
drawdown under half the capital the strategy needs. Selection is then checked honestly: build on 2021-2024, judge
on 2025-2026, which no choice was allowed to see.

    python research/zoo_report.py     ->  prints the tables, writes data/zoo_report.json and research/ZOO_RESULTS.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.zoo_data import ROOT  # noqa: E402

YEARS = [str(y) for y in range(2021, 2027)]
SPAN_YEARS = 5.86
LAST12 = "2025-11-10"


def pf(v):
    w = sum(x for x in v if x > 0)
    l = -sum(x for x in v if x <= 0)
    return round(w / l, 2) if l else float("inf")


def score(name, s):
    tr = sorted(s["trades"], key=lambda t: t["date"])
    cap = s["capital"]
    by_year, by_month = defaultdict(float), defaultdict(float)
    eq = peak = dd = 0.0
    for t in tr:
        by_year[t["date"][:4]] += t["pnl"]
        by_month[t["date"][:7]] += t["pnl"]
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    pnl = [t["pnl"] for t in tr]
    months = list(by_month.values())
    tstat = (np.mean(months) / (np.std(months, ddof=1) / np.sqrt(len(months)))) if len(months) > 2 and np.std(months) > 0 else 0.0
    build = [t["pnl"] for t in tr if t["date"] < "2025-01-01"]
    test = [t["pnl"] for t in tr if t["date"] >= "2025-01-01"]
    units = s.get("periods") if s.get("daily") else pnl          # profit factor per trade, or per month for daily books
    net = sum(pnl)
    yrs_up = sum(1 for y in YEARS if by_year.get(y, 0) > 0)
    return {
        "name": name, "family": s["family"], "capital": cap, "n": len(tr) if not s.get("daily") else None,
        "win": round(100 * np.mean([x > 0 for x in pnl]), 0) if not s.get("daily") else None,
        "pf": pf(units), "net": round(net), "years": {y: round(by_year.get(y, 0)) for y in YEARS}, "years_up": yrs_up,
        "maxdd": round(dd), "ret_pa": round(net / cap / SPAN_YEARS * 100, 1),
        "last12": round(sum(t["pnl"] for t in tr if t["date"] >= LAST12)), "last12_pct": round(sum(t["pnl"] for t in tr if t["date"] >= LAST12) / cap * 100, 1),
        "build": round(sum(build)), "build_pf": pf(build) if not s.get("daily") else None, "test": round(sum(test)),
        "test_pct_pa": round(sum(test) / cap / 1.86 * 100, 1), "t": round(float(tstat), 2),
        "survive": net > 0 and yrs_up >= 4 and -dd < 0.5 * cap,
        "build_pass": sum(build) > 0 and sum(1 for y in YEARS[:4] if by_year.get(y, 0) > 0) >= 3,
    }


def main():
    data = {**json.loads((ROOT / "zoo_intraday.json").read_text()), **json.loads((ROOT / "zoo_daily.json").read_text())}
    bench = score("ZZ", data.pop("ZZ Benchmark: buy and hold NIFTY ETF"))
    rows = [score(n, s) for n, s in data.items()]
    assert len(rows) == 50, len(rows)
    lines = []

    def out(x=""):
        print(x)
        lines.append(x)

    out("# 50 strategies on real Indian market data, 2021-2026")
    out()
    out("| Strategy | Capital | Net | Return/yr | PF | Years up | Max drawdown | Last 12 months | Survives |")
    out("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: r["name"]):
        out(f"| {r['name']} | {r['capital']:,.0f} | {r['net']:,} | {r['ret_pa']}% | {r['pf']} | {r['years_up']}/6 | {r['maxdd']:,} |"
            f" {r['last12']:,} ({r['last12_pct']}%) | {'YES' if r['survive'] else 'no'} |")
    out()
    out(f"Benchmark, buy and hold the NIFTY ETF on Rs 1,00,000: net {bench['net']:,}, {bench['ret_pa']}%/yr, max drawdown {bench['maxdd']:,},"
        f" last 12 months {bench['last12']:,}, 2025-26 {bench['test_pct_pa']}%/yr.")
    out()
    surv = sorted([r for r in rows if r["survive"]], key=lambda r: -r["ret_pa"])
    out(f"## Survivors: {len(surv)} of 50")
    out()
    out("| Strategy | Family | Capital | Return/yr | Last 12 months | By year (Rs '000) | Max drawdown | Monthly t-stat |")
    out("|---|---|---|---|---|---|---|---|")
    for r in surv:
        out(f"| {r['name']} | {r['family']} | {r['capital']:,.0f} | {r['ret_pa']}% | {r['last12_pct']}% |"
            f" {' '.join(f'{v / 1000:+.0f}' for v in r['years'].values())} | {r['maxdd']:,} | {r['t']} |")
    out()
    fam = defaultdict(list)
    for r in rows:
        fam[r["family"]].append(r)
    out("## By family")
    out()
    out("| Family | Strategies | Net positive | Survive | Median return/yr |")
    out("|---|---|---|---|---|")
    for f, rs in fam.items():
        out(f"| {f} | {len(rs)} | {sum(r['net'] > 0 for r in rs)} | {sum(r['survive'] for r in rs)} | {np.median([r['ret_pa'] for r in rs]):.1f}% |")
    out()
    bp = [r for r in rows if r["build_pass"]]
    held = [r for r in bp if r["test"] > 0]
    out("## Honest check: pick on 2021-2024, judge on 2025-2026")
    out()
    out(f"{len(bp)} strategies looked good on 2021-2024 (net positive, at least 3 of 4 years up). {len(held)} of them made money in 2025-2026.")
    out()
    out("| Picked on 2021-2024 | Build net | 2025-26 net | 2025-26 return/yr | Benchmark 2025-26 |")
    out("|---|---|---|---|---|")
    for r in sorted(bp, key=lambda r: -r["test_pct_pa"]):
        out(f"| {r['name']} | {r['build']:,} | {r['test']:,} | {r['test_pct_pa']}% | {bench['test_pct_pa']}% |")
    out()
    strong = [r for r in rows if r["t"] > 2]
    out(f"Luck check: {len(strong)} of 50 have a monthly t-statistic above 2. With 50 tries, about 1 would clear that bar by luck alone.")
    (ROOT / "zoo_report.json").write_text(json.dumps({"rows": rows, "benchmark": bench}, indent=1))
    (Path(__file__).with_name("ZOO_RESULTS.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
