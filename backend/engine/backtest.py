"""Walk-forward replay of the exact live logic on real 5-minute bars.

Each decision only sees bars up to that moment. Entries fill at the NEXT bar's open,
exits on stop/target touch (stop wins if both touch in one bar) or 15:15 square-off.
News/global cues are not replayed (no history), so this tests the price engine alone.
Option P&L is approximated with delta 0.5 minus 1 point slippage and full charges.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

from . import timeline
from .config import INSTRUMENTS
from .data import closed_bars, get_candles
from .options import round_trip_cost
from .signal import evaluate


def run(key: str = "NIFTY", max_trades_per_day: int = 3) -> dict:
    inst = INSTRUMENTS[key]
    df5, source = get_candles(key, "5m")
    df5 = closed_bars(df5, "5m")
    daily, _ = get_candles(key, "1d")
    trades, pos, day_count = [], None, {}
    warm = 200
    idx = df5.index
    for i in range(warm, len(df5) - 1):
        ts = idx[i]
        bar = df5.iloc[i]
        if pos:
            hit_stop = bar.low <= pos["stop"] if pos["dir"] > 0 else bar.high >= pos["stop"]
            hit_tgt = bar.high >= pos["target"] if pos["dir"] > 0 else bar.low <= pos["target"]
            eod = ts.time() >= time(15, 15) or idx[i + 1].date() != ts.date()
            if hit_stop or hit_tgt or eod:
                exit_px = pos["stop"] if hit_stop else pos["target"] if hit_tgt else float(bar.close)
                pts = (exit_px - pos["entry"]) * pos["dir"]
                prem = 0.5 * pts - 1.0
                cost = round_trip_cost(max(pos["est_premium"], 1), inst.lot_size)
                trades.append({**pos, "exit_time": ts.isoformat(), "exit": round(exit_px, 2),
                               "reason": "stop" if hit_stop else "target" if hit_tgt else "time",
                               "points": round(pts, 2), "r": round(pts / pos["risk"], 2),
                               "pnl_per_lot": round(prem * inst.lot_size - cost, 2)})
                pos = None
            continue
        t = ts.time()
        if not (time(9, 30) <= t < time(15, 0)):
            continue
        if day_count.get(ts.date(), 0) >= max_trades_per_day:
            continue
        hist = df5.iloc[max(0, i - 400):i + 1]
        sess = {"can_enter": True, "is_expiry_day": timeline.weekly_expiry(key, ts.date()) == ts.date(),
                "phase": "midday_chop" if time(11, 30) <= t < time(13, 30) else "trend"}
        r = evaluate(hist, daily, inst.strike_step, now=ts.to_pydatetime() + pd.Timedelta(minutes=5), session=sess)
        if r["verdict"] in ("BUY", "SELL"):
            nxt = df5.iloc[i + 1]
            if idx[i + 1].date() != ts.date():
                continue
            d = r["plan"]["direction"]
            entry = float(nxt.open)
            shift = entry - r["price"]
            pos = {"time": idx[i + 1].isoformat(), "dir": d, "verdict": r["verdict"], "entry": round(entry, 2),
                   "stop": r["plan"]["stop"] + shift, "target": r["plan"]["target"] + shift,
                   "risk": max(abs(entry - (r["plan"]["stop"] + shift)), 1e-6), "score": r["score"],
                   "est_premium": entry * 0.004}
            day_count[ts.date()] = day_count.get(ts.date(), 0) + 1
    df = pd.DataFrame(trades)
    if df.empty:
        return {"instrument": key, "source": source, "bars": len(df5), "trades": 0, "summary": "No trades triggered."}
    wins = df[df.points > 0]
    gross_win = wins.pnl_per_lot.clip(lower=0).sum()
    gross_loss = -df.pnl_per_lot.clip(upper=0).sum()
    eq = df.pnl_per_lot.cumsum()
    res = {
        "instrument": key, "source": source, "bars": len(df5),
        "from": df5.index[warm].isoformat(), "to": df5.index[-1].isoformat(),
        "trades": len(df), "win_rate": round(len(wins) / len(df) * 100, 1),
        "avg_r": round(df.r.mean(), 2), "expectancy_per_lot": round(df.pnl_per_lot.mean(), 2),
        "net_pnl_per_lot": round(df.pnl_per_lot.sum(), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "max_drawdown_per_lot": round(float((eq - eq.cummax()).min()), 2),
        "by_exit": df.reason.value_counts().to_dict(),
        "equity": [{"time": t, "equity": round(e, 2)} for t, e in zip(df.exit_time, eq)],
        "trade_list": df.drop(columns=["risk"]).tail(200).to_dict("records"),
    }
    res["summary"] = (f"{res['trades']} trades, {res['win_rate']}% winners, average {res['avg_r']}R per trade, "
                      f"net Rs {res['net_pnl_per_lot']:,.0f} per lot after costs over "
                      f"{df5.index[warm].date()} to {df5.index[-1].date()}. Small sample: treat as a sanity check, not proof.")
    return res
