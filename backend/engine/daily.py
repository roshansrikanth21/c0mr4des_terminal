"""Per-day paper results, in the shape a phone can read.

The question this answers is one line long: how many trades today, and how much. Everything else
in this project is a caveat on that number, so the caveats stay in `lessons` and `desk.py review`
and this file stays boring on purpose.

Grouping follows the book's own convention: a trade belongs to the day it was OPENED
(`opened_at[:10]`), which is what `PaperTrader.today_closed` already uses, so the daily number and
the journal never disagree.
"""
from __future__ import annotations

from datetime import date

MAX_DAYS = 14


def by_day(closed: list[dict], days: int = MAX_DAYS) -> list[dict]:
    """Closed trades grouped by the day they were opened, newest day first."""
    rows: dict[str, dict] = {}
    for t in closed or []:
        d = str(t.get("opened_at") or "")[:10]
        if len(d) != 10:
            continue
        p = float(t.get("pnl") or 0)
        b = rows.setdefault(d, {"date": d, "trades": 0, "wins": 0, "pnl": 0.0,
                                "best": 0.0, "worst": 0.0})
        b["trades"] += 1
        b["wins"] += 1 if p > 0 else 0
        b["pnl"] = round(b["pnl"] + p, 2)
        b["best"] = max(b["best"], p)
        b["worst"] = min(b["worst"], p)
    out = sorted(rows.values(), key=lambda r: r["date"], reverse=True)[:days]
    for r in out:
        r["win_rate"] = round(r["wins"] / r["trades"] * 100, 1) if r["trades"] else None
        r["green"] = r["pnl"] > 0
    return out


def report(paper: dict, day: str | None = None, cases: dict | None = None,
           spreads: dict | None = None) -> dict:
    """Today's line, the last two weeks, the other books, and the all-time total. No interpretation."""
    closed = (paper or {}).get("closed") or []
    days = by_day(closed)
    today = day or date.today().isoformat()
    match = next((r for r in days if r["date"] == today), None)
    live = (paper or {}).get("today") or {}
    allt = (paper or {}).get("all_time") or {}
    dr = (paper or {}).get("day_rules") or {}
    day_state = (paper or {}).get("day") or {}
    case_rows = []
    for c in (cases or {}).get("cases") or []:
        t = c.get("today") or {}
        case_rows.append({"id": c.get("id"), "label": c.get("label"),
                          "trades": int(t.get("trades") or 0), "pnl": round(float(t.get("pnl") or 0), 2),
                          "net": round(float(c.get("net") or 0), 2),
                          "return_pct": c.get("return_pct"), "open": len(c.get("open") or [])})
    sp = spreads or {}
    sp_today = [t for t in sp.get("closed") or [] if str(t.get("closed_at") or "")[:10] == today]
    spread_row = None
    if sp:
        spread_row = {"trades": len(sp_today), "pnl": round(sum(float(t.get("pnl") or 0) for t in sp_today), 2),
                      "net": round(float(sp.get("net") or 0), 2), "closed": int(sp.get("trades") or 0),
                      "open": 1 if sp.get("open") else 0, "rules_version": sp.get("rules_version")}
    return {
        "date": today,
        "trades": int(live.get("trades") or 0),
        "pnl": round(float(live.get("pnl") or 0), 2),
        "wins": int(live.get("wins") or 0),
        "best": match["best"] if match else 0.0,
        "worst": match["worst"] if match else 0.0,
        "days": days,
        "cases": case_rows,
        "spreads": spread_row,
        "all_time": {"trades": int(allt.get("trades") or 0),
                     "pnl": round(float(allt.get("pnl") or 0), 2),
                     "win_rate": allt.get("win_rate")},
        "open": len((paper or {}).get("open") or []),
        "stopped": day_state.get("stopped"),
        "profit_stop": dr.get("profit_stop"), "loss_stop": dr.get("loss_stop"),
    }


def _rs(x: float) -> str:
    """Rs with an explicit sign, ASCII only - this goes through Telegram and a terminal."""
    return f"Rs {x:+,.0f}"


def text(rep: dict) -> str:
    """The message itself. Short enough to read on a lock screen."""
    try:
        nice = date.fromisoformat(rep["date"]).strftime("%a %d %b %Y")
    except Exception:  # noqa: BLE001
        nice = str(rep.get("date"))
    lines = [f"C0MR4DES {nice}",
             f"Main book: {rep['trades']} trade(s) | {_rs(rep['pnl'])} | {rep['wins']} won"]
    if rep.get("stopped") == "profit":
        lines.append(f"Day stop: PROFIT target hit ({_rs(float(rep.get('profit_stop') or 0))})")
    elif rep.get("stopped") == "loss":
        lines.append(f"Day stop: LOSS limit hit ({_rs(-float(rep.get('loss_stop') or 0))})")
    if rep.get("open"):
        lines.append(f"Still open: {rep['open']}")

    cases = rep.get("cases") or []
    sp = rep.get("spreads")
    if cases or sp:
        lines.append("")
        lines.append("Other books")
        for c in cases:
            ret = c.get("return_pct")
            ret_txt = f"{ret:+.1f}%" if ret is not None else "n/a"
            lines.append(f"  {c['id']} {str(c['label']):18s} {c['trades']:>2} tr {_rs(c['pnl']):>11} "
                         f"| week {ret_txt}")
        if sp:
            lines.append(f"  Spreads (v{sp.get('rules_version', '?')})  {sp['trades']:>2} tr {_rs(sp['pnl']):>11} "
                         f"| all-time {_rs(sp['net'])} on {sp['closed']} closed"
                         + (f" | {sp['open']} open" if sp.get("open") else ""))

    days = [d for d in rep.get("days") or [] if d["trades"]]
    if days:
        lines.append("")
        lines.append("By day")
        for d in days[:10]:
            lines.append(f"  {d['date'][5:]}  {d['trades']:>2} tr  {_rs(d['pnl']):>12}  "
                         f"{d['wins']}/{d['trades']} won")

    a = rep.get("all_time") or {}
    wr = a.get("win_rate")
    lines.append("")
    lines.append(f"All time: {a.get('trades', 0)} trades | {_rs(float(a.get('pnl') or 0))}"
                 + (f" | {wr}% win" if wr is not None else ""))
    if rep["trades"] == 0:
        lines.append("No trades today - the gate refused them, or nothing set up.")
    return "\n".join(lines)
