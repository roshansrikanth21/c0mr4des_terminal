"""Turn closed paper trades into named failure patterns, standing warnings, and one honest sentence.

This is the human half of a self-improvement loop, and deliberately only the human half: it observes
and counts, it never changes a rule on its own. Strategy changes stay a deliberate act recorded in
`experiments.py`, because an automated loop over eight trades would happily promote noise forever.

Every pattern here is computable from the trade record itself - no candle lookups, no judgement
calls - so live, replay and tests all read the same book the same way.
"""
from __future__ import annotations

from datetime import datetime

from .config import IST

MIN_TRADES = 20  # the same number the go/no-go gate needs before it will speak


def _ist_hour(iso: str) -> int:
    try:
        return datetime.fromisoformat(iso).astimezone(IST).hour
    except Exception:  # noqa: BLE001 - a malformed timestamp must not kill the report
        return -1


def lessons(closed: list[dict]) -> dict:
    """Count the honest patterns in a list of closed trades and say what they mean."""
    counts: dict[str, int] = {}
    losses = [t for t in closed if t.get("pnl", 0) <= 0]
    net = sum(t.get("pnl", 0) for t in closed)

    for t in closed:
        hour = _ist_hour(t.get("opened_at", ""))
        reason = t.get("reason", "")
        win = t.get("pnl", 0) > 0
        if hour >= 13:
            counts["late_entry"] = counts.get("late_entry", 0) + 1
        if hour >= 0 and hour <= 10 and not win:
            counts["early_loss"] = counts.get("early_loss", 0) + 1
        if "square-off" in reason and not win and not t.get("stale"):
            counts["bled_to_close"] = counts.get("bled_to_close", 0) + 1
        if "square-off" in reason and win:
            counts["winners_held_to_close"] = counts.get("winners_held_to_close", 0) + 1
        if reason == "premium stop":
            counts["decay_death"] = counts.get("decay_death", 0) + 1
        if t.get("oversize") and not win:
            counts["oversize_loss"] = counts.get("oversize_loss", 0) + 1

    bleed_avg = (sum(t["pnl"] for t in closed if "square-off" in t.get("reason", "") and t["pnl"] <= 0)
                 / max(counts.get("bled_to_close", 0), 1)) if counts.get("bled_to_close") else 0.0
    stop_avg = (sum(t["pnl"] for t in losses if "stop" in t.get("reason", ""))
                / max(sum(1 for t in losses if "stop" in t.get("reason", "")), 1)) if losses else 0.0

    flags: list[dict] = []
    add = flags.append
    if len(closed) < MIN_TRADES:
        add({"name": "sample", "text": (f"Only {len(closed)} closed trades. Even a perfect-looking "
                                        f"record at this size is noise - the gate will not speak before {MIN_TRADES}.")})
    positives = sorted((t["pnl"] for t in closed if t["pnl"] > 0), reverse=True)
    if net > 0 and positives:
        gross = sum(positives)
        top = positives[:2]
        if sum(top) >= 0.8 * gross:
            share_txt = f"{len(top)} trade(s) hold Rs {sum(top):,.0f} of Rs {gross:,.0f} gross wins"
            if len(top) < len(positives) or sum(top) < gross:
                share_txt += f" ({sum(top) / gross * 100:.0f}%)"
            add({"name": "luck", "text": (f"{share_txt}. Cut those out and the book is deeply negative - "
                                          f"this is not yet an edge, it is one or two holdings.")})
    if counts.get("oversize_loss"):
        add({"name": "oversize", "text": (f"{counts['oversize_loss']} loss(es) were trades bigger than the risk "
                                          f"budget allowed. At this capital that is expected, but none of them "
                                          f"may ever count towards a live GO.")})
    if counts.get("bled_to_close", 0) >= 2 and bleed_avg < stop_avg:
        add({"name": "bleed", "text": (f"{counts['bled_to_close']} trades bled all the way to the 15:15 "
                                       f"square-off, averaging Rs {abs(bleed_avg):,.0f}, while stops averaged "
                                       f"Rs {abs(stop_avg):,.0f}. Either entries are too early or the stop is "
                                       f"too far - the clock is cutting deeper than the stop is.")})
    if counts.get("late_entry", 0) >= 2:
        add({"name": "late", "text": (f"{counts['late_entry']} entries came after 13:00 - buying a move that "
                                      f"already spent itself. Afternoon entries pay the worst theta and the "
                                      f"least follow-through.")})
    if counts.get("decay_death", 0) >= 2:
        add({"name": "decay", "text": (f"{counts['decay_death']} trades died at the premium stop before the "
                                       f"index ever hit the index stop - time decay, not direction, killed "
                                       f"them. That argues for nearer strikes or shorter holds.")})
    if counts.get("winners_held_to_close"):
        add({"name": "hold_winners", "text": (f"{counts['winners_held_to_close']} of the winners came from "
                                              f"holding to the square-off. That is the design working: winners "
                                              f"are rare and big, so the 40% win-rate gate expects discipline, "
                                              f"not frequent wins.")})

    if not closed:
        return {"counts": {}, "flags": [{"name": "empty", "text": "No paper trades yet - nothing to read."}],
                "text": "No paper trades yet.", "losses": 0, "net": 0.0}

    lines = [f["text"] for f in flags]
    return {"counts": counts, "flags": flags, "text": " ".join(lines),
            "losses": len(losses), "net": round(net, 2)}
