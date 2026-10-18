"""Walk-forward replay of the exact live logic on real 5-minute index bars.

- Each decision only sees bars up to that moment; entries fill at the NEXT bar's open.
- Exits: index stop/target touch (stop wins if both touch in one bar) or 15:15 square-off.
- Option P&L: the strike the live engine would pick, priced with Black-Scholes at entry and exit
  using that day's real India VIX (previous close, no look-ahead) and the real time left to
  that week's expiry, so time decay (theta) and gamma are included. Plus 0.5% slippage per side
  and full charges. These are modelled premiums from real index + VIX data, not traded option prints.
- News/global cues are not replayed (no history), so this tests the price engine alone.
"""
from __future__ import annotations

from datetime import datetime, time

import pandas as pd

from . import timeline
from .config import INSTRUMENTS, IST
from .data import closed_bars, get_candles, get_quote_series
from .options import bs, round_trip_cost, years_to_expiry
from .signal import evaluate

SLIPPAGE = 0.005


def _vix_lookup() -> dict:
    df = get_quote_series("^INDIAVIX", "1y", "1d")
    if df is None:
        return {}
    s = df["close"]
    return {d.date(): float(v) for d, v in s.shift(1).dropna().items()}  # yesterday's close = known at open


def _option_price(key: str, spot: float, strike: float, kind: str, expiry, at: datetime, vix: float) -> float:
    return max(0.05, bs(spot, strike, years_to_expiry(expiry, at), vix / 100, kind)["price"])


def run(key: str = "NIFTY", max_trades_per_day: int = 3, use_htf: bool = True) -> dict:
    inst = INSTRUMENTS[key]
    df5, source = get_candles(key, "5m")
    df5 = closed_bars(df5, "5m")
    daily, _ = get_candles(key, "1d")
    vix_by_day = _vix_lookup()
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
                exit_at = ts.to_pydatetime() + pd.Timedelta(minutes=5)
                prem_out = _option_price(key, exit_px, pos["strike"], pos["kind"], pos["expiry"], exit_at, pos["vix"])
                prem_out *= (1 - SLIPPAGE)
                qty = inst.lot_size
                cost = round_trip_cost((pos["prem_in"] + prem_out) / 2, qty)
                pnl = (prem_out - pos["prem_in"]) * qty - cost
                pts = (exit_px - pos["entry"]) * pos["dir"]
                trades.append({**{k: v for k, v in pos.items() if k not in ("expiry",)},
                               "expiry": pos["expiry"].isoformat(), "exit_time": ts.isoformat(), "exit": round(exit_px, 2),
                               "prem_out": round(prem_out, 2), "reason": "stop" if hit_stop else "target" if hit_tgt else "time",
                               "points": round(pts, 2), "r": round(pts / pos["risk"], 2), "pnl_per_lot": round(pnl, 2)})
                pos = None
            continue
        t = ts.time()
        if not (time(9, 30) <= t < time(15, 0)) or day_count.get(ts.date(), 0) >= max_trades_per_day:
            continue
        hist = df5.iloc[max(0, i - 400):i + 1]
        expiry = timeline.weekly_expiry(key, ts.date())
        sess = {"can_enter": True, "is_expiry_day": expiry == ts.date(),
                "phase": "midday_chop" if time(11, 30) <= t < time(13, 30) else "trend"}
        now = ts.to_pydatetime() + pd.Timedelta(minutes=5)
        r = evaluate(hist, daily, inst.strike_step, now=now, session=sess, use_htf=use_htf)
        if r["verdict"] not in ("BUY", "SELL") or idx[i + 1].date() != ts.date():
            continue
        d = r["plan"]["direction"]
        entry = float(df5.iloc[i + 1].open)
        shift = entry - r["price"]
        kind = "CE" if d > 0 else "PE"
        atm = round(entry / inst.strike_step) * inst.strike_step
        T = years_to_expiry(expiry, now)
        strike = atm - d * (1 if T * 365 < 2 else 0) * inst.strike_step
        vix = vix_by_day.get(ts.date(), 14.0)
        prem_in = _option_price(key, entry, strike, kind, expiry, now, vix) * (1 + SLIPPAGE)
        pos = {"time": idx[i + 1].isoformat(), "dir": d, "verdict": r["verdict"], "entry": round(entry, 2),
               "stop": r["plan"]["stop"] + shift, "target": r["plan"]["target"] + shift,
               "risk": max(abs(r["plan"]["stop"] - r["price"]), 1e-6), "score": r["score"],
               "strike": strike, "kind": kind, "expiry": expiry, "vix": vix, "prem_in": round(prem_in, 2),
               "triggers": ", ".join(r.get("triggers", []))}
        day_count[ts.date()] = day_count.get(ts.date(), 0) + 1
    return summarize(pd.DataFrame(trades), key, source, df5, warm)


def summarize(df: pd.DataFrame, key: str, source: str, df5: pd.DataFrame, warm: int) -> dict:
    base = {"instrument": key, "source": source, "bars": len(df5),
            "from": df5.index[warm].isoformat(), "to": df5.index[-1].isoformat()}
    if df.empty:
        return {**base, "trades": 0, "summary": "No trades triggered."}
    win, loss = df[df.pnl_per_lot > 0], df[df.pnl_per_lot <= 0]
    eq = df.pnl_per_lot.cumsum()
    df["month"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m")
    df["weekday"] = pd.to_datetime(df["time"]).dt.day_name()
    df["expiry_day"] = pd.to_datetime(df["time"]).dt.date.astype(str) == df["expiry"]
    grp = lambda col: {str(k): {"trades": int(len(g)), "wins": int((g.pnl_per_lot > 0).sum()),
                                "net": round(float(g.pnl_per_lot.sum()), 0)} for k, g in df.groupby(col)}
    res = {
        **base,
        "trades": len(df), "win_rate": round(len(win) / len(df) * 100, 1),
        "winners": int(len(win)), "total_profit": round(float(win.pnl_per_lot.sum()), 0),
        "avg_win": round(float(win.pnl_per_lot.mean()), 0) if len(win) else 0,
        "biggest_win": round(float(win.pnl_per_lot.max()), 0) if len(win) else 0,
        "losers": int(len(loss)), "total_loss": round(float(loss.pnl_per_lot.sum()), 0),
        "avg_loss": round(float(loss.pnl_per_lot.mean()), 0) if len(loss) else 0,
        "biggest_loss": round(float(loss.pnl_per_lot.min()), 0) if len(loss) else 0,
        "net_pnl_per_lot": round(float(df.pnl_per_lot.sum()), 0),
        "expectancy_per_lot": round(float(df.pnl_per_lot.mean()), 0),
        "avg_r": round(float(df.r.mean()), 2),
        "profit_factor": round(float(win.pnl_per_lot.sum() / -loss.pnl_per_lot.sum()), 2) if loss.pnl_per_lot.sum() < 0 else None,
        "max_drawdown_per_lot": round(float((eq - eq.cummax()).min()), 0),
        "by_exit": grp("reason"), "by_side": grp("verdict"), "by_month": grp("month"),
        "by_weekday": grp("weekday"), "by_expiry_day": grp("expiry_day"),
        "equity": [{"time": t, "equity": round(e, 2)} for t, e in zip(df.exit_time, eq)],
        "trade_list": df.drop(columns=["risk", "month", "weekday", "expiry_day"]).tail(300).to_dict("records"),
    }
    res["summary"] = (f"{res['trades']} trades: {res['winners']} winners made Rs {res['total_profit']:,.0f}, "
                      f"{res['losers']} losers lost Rs {abs(res['total_loss']):,.0f}. Net Rs {res['net_pnl_per_lot']:,.0f} "
                      f"per lot after costs ({base['from'][:10]} to {base['to'][:10]}).")
    return res
