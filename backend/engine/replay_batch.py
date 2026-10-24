"""Batch replay: push every recent trading day through the LIVE code path (analyze + paper autopilot),
one 5-minute step at a time, and score each strategy. This checks the running system, not the lab.

    python -m backend.engine.replay_batch [days]

Caveat: option premiums use today's India VIX (no intraday history), so rupee P&L is approximate;
entries, exits and direction are exact.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

from . import replay, service
from .config import DATA_DIR, IST
from .data import get_candles
from .trader import PaperTrader, go_no_go, scorecard

STRATS = ["First-Hour", "First-30", "Engine"]


def run(n_days: int = 40) -> dict:
    df, source = get_candles("NIFTY", "5m")
    today = datetime.now(IST).date()
    days = sorted({d for d in df.index.date if d < today})[-n_days:]
    settings = {**service.load_settings(), "autopilot_strategies": STRATS}
    book = PaperTrader(Path(tempfile.mkdtemp()) / "batch.json")
    for d in days:
        t = datetime.combine(d, time(9, 20), IST)
        while t.time() <= time(15, 25):
            replay.start(d, speed=1, start_at=t.time())  # frozen clock at exactly t
            try:
                book.on_analysis(service.analyze("NIFTY"), settings)
            except Exception as exc:  # noqa: BLE001
                print(f"{d} {t:%H:%M} skipped: {exc}")
            t += timedelta(minutes=5)
        replay.stop()
        day = [x for x in book.state["closed"] if x["opened_at"][:10] == d.isoformat()]
        print(f"{d} {len(day)} trade(s) " + ", ".join(f"{x['strategy']} {x['side']} {x['pnl']:+,.0f}" for x in day), flush=True)
    closed = sorted(book.state["closed"], key=lambda x: x["closed_at"])
    out = {"source": source, "days": [d.isoformat() for d in days], "strategies": {}}
    for s in STRATS:
        sc = scorecard([x for x in closed if x["strategy"] == s])
        out["strategies"][s] = {**sc, "verdict": go_no_go(sc)[0]}
    out["trades"] = closed
    (DATA_DIR / "replay_batch.json").write_text(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    res = run(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
    print(f"\n{len(res['days'])} days ({res['days'][0]} to {res['days'][-1]}), data: {res['source']}")
    for s, v in res["strategies"].items():
        print(f"{s:11s} {v['trades']:3d} trades  win {v['win_rate']}%  avg win {v['avg_win']:,.0f} / loss {v['avg_loss']:,.0f}"
              f"  payoff {v['payoff']}x  net Rs {v['net']:,.0f}  worst streak {v['worst_streak']}  -> {v['verdict']}")
