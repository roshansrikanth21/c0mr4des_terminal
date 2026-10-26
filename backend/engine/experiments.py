"""Append-only experiment registry: every deliberate change to strategy or process, one JSON line each.

Rule the whole project runs on: an idea is not an experiment until it has a row here, and a row is
not promoted until the evidence column says why. This is the discipline the "self-improving bot"
posts preach - kept deliberately manual, because an automated loop that promotes its own versions
over eight paper trades is an overfitting machine, not a system.

Seeding is truthful: only changes that actually happened (with the commit or the owner decision
that made them), no invented dates, no invented numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "data" / "experiments.jsonl"

STATUSES = ("proposed", "testing", "promoted", "parked", "rejected")
AREAS = ("strategy", "process", "infra")


def _seed() -> list[dict]:
    """The registry's opening history - real changes only."""
    return [
        {"id": 1, "date": "original", "area": "strategy", "name": "First-Hour (ORB)",
         "change": "Breakout of the first-hour range, 1 lot, stop below the range, hold to 15:15",
         "evidence": "Entry: First-Hour excl. expiry days sits near break-even (PF ~1.15); the README's "
                     "1.41 headline comes from expiry days, the least reliable prices. Paper evidence "
                     "accumulating on the Azure box.",
         "status": "promoted", "owner": "original build"},
        {"id": 2, "date": "original", "area": "strategy", "name": "First-30 (ORB, faster)",
         "change": "Same breakout family on the first 30 minutes",
         "evidence": "Paper: 3 trades, the largest winner of the whole book (+Rs 5,227). Too few trades to judge.",
         "status": "testing", "owner": "original build"},
        {"id": 3, "date": "original", "area": "strategy", "name": "Engine (7-factor scorer)",
         "change": "Full scorer as its own strategy slot",
         "evidence": "Weakest backtest (PF 1.27) and 0/2 in its first live week. Default OFF, slot kept for comparison.",
         "status": "parked", "owner": "original build"},
        {"id": 4, "date": "2026-10-25", "area": "strategy", "name": "Expiry slot",
         "change": "First-Hour signal on Tuesday's expiring option, 1 lot, Rs 1,000 max loss, scored separately",
         "evidence": "Owner decision 26 Oct: OFF by default - backtest profit concentrates on expiry days, the "
                      "least trustworthy prices in the record. Opt-in until it banks ~20 honest paper trades.",
         "status": "testing", "owner": "owner decision"},
        {"id": 5, "date": "2026-10-25", "area": "process", "name": "Paper book hardening",
         "change": "Stale square-off closes next session, corrupt-file recovery, positions marked against their own expiry's chain",
         "evidence": "Commit 3248e2a; test suite green.",
         "status": "promoted", "owner": "audit"},
        {"id": 6, "date": "2026-10-25", "area": "process", "name": "Oversize gate rule",
         "change": "go/no-go refuses GO while any trade was bigger than the risk budget",
         "evidence": "The only thing stopping a Rs 10k account from 'passing' a strategy it cannot fund. Commit 4f7b520.",
         "status": "promoted", "owner": "owner OK"},
        {"id": 7, "date": "2026-10-25", "area": "infra", "name": "Go/no-go gate on Trade Journal + /api/paper",
         "change": "Journal page shows the same gate verdict the Saturday report sends",
         "evidence": "Commit f5213b0.",
         "status": "promoted", "owner": "owner OK"},
        {"id": 8, "date": "2026-10-26", "area": "infra", "name": "Decision strip + MTF ladder + both-side pricing",
         "change": "Daily/4h/1h/15m/5m/1m confluence, yesterday's range, CE and PE priced, affordability honest",
         "evidence": "Commits 8765885, b8a5896. Direction from the ladder, actionability still from the engine verdict.",
         "status": "promoted", "owner": "owner request"},
        {"id": 9, "date": "2026-10-26", "area": "strategy", "name": "One position at a time",
         "change": "max_open_positions = 1 - a second strategy waits instead of stacking risk",
         "evidence": "Owner decision 26 Oct. Reason logged in tests and MAILBOX.",
         "status": "promoted", "owner": "owner decision"},
        {"id": 10, "date": "2026-10-26", "area": "process", "name": "Failure-pattern reader + this registry",
         "change": "lessons() counts named loss patterns in the paper book; every deliberate change gets a row here",
         "evidence": "The manual half of a self-improvement loop: observe and count only - promotions stay human decisions.",
         "status": "promoted", "owner": "owner OK"},
    ]


def all() -> list[dict]:
    """Every experiment, oldest first. Seeds the file on first read."""
    if not FILE.exists():
        rows = _seed()
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return rows
    try:
        return [json.loads(line) for line in FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:  # noqa: BLE001 - a corrupt line must not kill the page
        return []


def record(area: str, name: str, change: str, evidence: str, status: str = "testing",
           owner: str = "", date: str = "") -> dict:
    """Add one experiment row and return it. bad input raises - this file must never lie."""
    if area not in AREAS or status not in STATUSES:
        raise ValueError(f"area must be one of {AREAS}, status one of {STATUSES}")
    rows = all()
    if not date:
        from datetime import date as _d
        date = _d.today().isoformat()
    row = {"id": (rows[-1]["id"] + 1) if rows else 1, "date": date, "area": area, "name": name,
           "change": change, "evidence": evidence, "status": status, "owner": owner}
    rows.append(row)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return row
