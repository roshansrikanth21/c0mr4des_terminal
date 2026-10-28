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
        {"id": 11, "date": "2026-10-26", "area": "process", "name": "Multi-capital paper study (4 isolated books)",
         "change": "Rs 10k / 30k / 50k plus a Rs 10k puts-only book, same signals, separate files, 1-2 trades/day, "
                   "no borrowing, bust-reset at the original stake",
         "evidence": "Owner request 26 Oct. Runs one week from the first live session; ranks by return on stake, "
                     "not raw rupees. Four or five trades per case is evidence about sizing, not proof of an edge.",
         "status": "testing", "owner": "owner request"},
        {"id": 12, "date": "2026-10-27", "area": "risk", "name": "Cost + theta gate, afternoon cut-off, 14:30 time stop",
         "change": "Refuse a long option when round-trip charges exceed 1% of premium or one day of theta exceeds 20% "
                   "of premium; no fresh entries after 13:00; force-close whatever is still open at 14:30 instead of "
                   "holding to the 15:15 square-off",
         "evidence": "Paper book 26 Oct: charges were 2.3% on a Rs 3.4k lot, 2 trades died on the premium stop before "
                     "the index stop, 2 entries after 13:00, 2 bled to square-off (avg Rs 1,468 vs Rs 1,056 stops). "
                     "Theta on a 1-DTE NIFTY ATM option is ~51% of premium per day vs ~9% at 6 DTE, and SEBI FY26 "
                     "puts 92% of individual derivatives losses in options. The 20% rule therefore sits out the last "
                     "1-2 days before expiry by design.",
         "status": "testing", "owner": "owner request"},
        {"id": 13, "date": "2026-10-27", "area": "strategy", "name": "Defined-risk credit spreads (bull put / bear call)",
         "change": "Sell a ~0.20-delta leg and buy a ~0.08-delta leg as protection, on the First-Hour signal: "
                   "one spread a day, Rs 50k stake, close at 50% of the credit or at 2x the credit, 14:30 time stop",
         "evidence": "VRP study 2016-2024: implied volatility exceeded realised on 79.5% of NIFTY days, so the "
                     "documented edge is on the sell side; naked selling needs Rs 1-1.5 lakh of margin per lot, "
                     "while a 250-point spread blocks about Rs 16k. The long-option book kept losing to theta "
                     "(premium stops before the index stop). Paper only - this book never sends an order.",
         "status": "testing", "owner": "owner request"},
        {"id": 14, "date": "2026-10-28", "area": "strategy", "name": "Fixed 10-point target on the 30-minute opening range",
         "change": "The rule as taught: range = the first two 15-minute candles (09:15-09:45), enter on a 15-minute "
                   "CLOSE outside it, stop at the opposite end, take a flat 10 points, one trade a day",
         "evidence": "Tested on 60 sessions of 5m NIFTY/SENSEX. NIFTY: 55 trades, 87.3% winners, -81 index points "
                     "(avg win +9.9 vs avg loss -79.6). SENSEX: 55 trades, 96.4% winners, +164 index points, but "
                     "-Rs 7,268 in the option account after charges, slippage and theta. A 10-point target is 0.12R "
                     "on NIFTY (median opening range 87 points) and 0.03R on SENSEX (median 297); the same 10 points "
                     "is roughly 0.5R on ES, where the rule was learned. The structure transfers, the number does not.",
         "status": "rejected", "owner": "owner request"},
        {"id": 15, "date": "2026-10-28", "area": "strategy", "name": "Shorten the opening range from 60 to 30 minutes",
         "change": "Range 09:15-09:45 instead of 09:15-10:15, 5-minute close confirmation, stop at the opposite end, "
                   "2R target. Same entry gate, same one-trade-a-day cap.",
         "evidence": "Re-tested apples-to-apples (2026-10-28): the earlier comparison used a separate "
                     "orb30_breakout() that did NOT apply the yesterday's-close side filter, so it was not the "
                     "same rule. orb30_breakout now delegates to first_hour_breakout(range_minutes=30). Same 69 "
                     "sessions, 2R, 1 lot: NIFTY 60min 48 tr +Rs 26,180 PF 1.57 win 47.9% (halves -747/+26,927) vs "
                     "30min 48 tr +Rs 59,488 PF 2.47 win 58.3% (halves +5,634/+53,854). SENSEX 60min 52 tr +Rs "
                     "19,135 PF 1.36 (halves -13,829/+32,964) vs 30min 52 tr +Rs 27,798 PF 1.54 (halves "
                     "-10,902/+38,700). Trade count is identical, so this is a better entry and stop on the same "
                     "days, not a different selection. BUT the rupee table flatters it: with 1 lot fixed a tighter "
                     "range means a closer stop and a smaller move to 2R. In R (what a risk-sized book earns) NIFTY "
                     "goes 0.023R -> 0.099R per trade, SENSEX is FLAT (0.004R -> 0.003R). NIFTY half1 stays "
                     "negative (-0.048R). Verdict: promising on NIFTY, no evidence on SENSEX, NOT promoted.",
         "status": "testing", "owner": "owner request"},
        {"id": 16, "date": "2026-10-28", "area": "strategy", "name": "Target is 2R, never a fixed number of points",
         "change": "Replace the flat 10-point target with 2x the entry-to-stop distance (orb.target_plan). "
                   "The desk prints today's 2R target in points and the win rate it needs, plus what a flat "
                   "10-point target would have needed on the same range.",
         "evidence": "A fixed target has a moving break-even: risk/(risk+target) is 86.5% on a quiet NIFTY "
                     "morning (64-pt stop), 90.5% at the median (95) and 94.7% on a wide one (178), while the "
                     "rule actually wins ~87% - so it is break-even on quiet days and a certain loser on wide "
                     "ones. SENSEX is worse still: 95.7%-98.2% needed against 96.4% achieved. An R-multiple pins "
                     "the requirement at 1/(1+k) every day: 33.3% at 2R. Ladder on 60 sessions: NIFTY 0.5R "
                     "+Rs 26,093, 1R +40,561, 1.5R +46,169, 2R +49,207 (PF 2.02), 3R +40,335; SENSEX peaks at 2R "
                     "too (+Rs 29,981, PF 1.53). 2R beats 1R in both halves of the sample on both indices.",
         "status": "promoted", "owner": "owner request"},
        {"id": 17, "date": "2026-10-28", "area": "process", "name": "Daily profit stop + a loss room one trade cannot breach",
         "change": "No new entries once the day banks +20% of capital (Rs 2,000 on Rs 10k). No new entries "
                   "once the day is down 25%. Every entry must also risk no more than the day's remaining "
                   "loss room, so a single fill can never breach the daily limit.",
         "evidence": "Replay of the real 10 trades: actual -Rs 3,293. The room rule alone turns 28 Oct from "
                     "-Rs 5,743 into -Rs 653, because the 10:20 trade risked Rs 4,846 with only Rs 2,500 of "
                     "room. The exact numbers cannot be chosen from 10 trades: a Rs 1,200 per-trade ceiling "
                     "replays +Rs 3,447 and Rs 1,000 replays -Rs 1,780 - a Rs 200 move flips the sign, because "
                     "the biggest winner risked Rs 1,158 and the biggest loser Rs 4,846. At Rs 1,200 the book "
                     "would refuse almost every ORB trade (one lot's honest stop is Rs 2,300-5,000), so the "
                     "limit stays at 25% and the room rule does the work. Judge after 20 trades.",
         "status": "testing", "owner": "owner request"},
        {"id": 18, "date": "2026-10-28", "area": "process", "name": "Local decision engine (the alternative to a hosted one)",
         "change": "New engine/decision.py + engine/dataset.py. Structured entry-time state in, typed "
                   "probabilistic output out, policy left in deterministic code. Two heads: P(green) and "
                   "expected R-multiple. It runs in SHADOW - it records a probability next to every paper "
                   "fill but cannot block or allow a trade until it is promoted on out-of-sample evidence.",
         "evidence": "Trained on 194 rows / 55 sessions of the two live rules (NIFTY + SENSEX, Yahoo 60-day "
                     "5m limit - Angel has no session on the VM, so this is the whole history). Walk-forward "
                     "OOS AUC 0.64 (folds 0.53-0.85, so unstable). The important result is negative: the win "
                     "head is a good ranker and still useless as a filter - keeping only p>=0.30 nets "
                     "+Rs 78,432 vs +Rs 151,687 taking every trade, because First-30 wins 32% and carries the "
                     "profit. The EV head does no better: best filter +Rs 153,477 on 187/194 trades is a "
                     "0.1% gain on a 96% keep rate, which is noise. Verdict: no filter earns its keep, so it "
                     "stays SHADOW. Promotion needs 200+ rows, OOS AUC >=0.55, an EV filter worth >=10% while "
                     "dropping >=15% of trades, and the R ranking right in 3 of 4 folds.",
         "status": "testing", "owner": "owner request"},
        {"id": 19, "date": "2026-10-28", "area": "strategy", "name": "First-Hour: skip when 5m and 15m trend already agree",
         "change": "Tested the decision engine's strongest coefficient as a real filter: skip the First-Hour "
                   "breakout when both the 5m and the 15m EMA20/50 already agree with the trade direction. "
                   "Four variants on the lab harness, same 2R target, same history.",
         "evidence": "NIFTY: baseline 48 trades +Rs 26,180 (PF 1.57, halves -747/+26,927); skip_aligned 19 "
                     "trades +Rs 15,974 (PF 2.06, halves +9,381/+6,593); only_aligned 45 +Rs 14,551 (PF 1.33). "
                     "SENSEX: baseline 52 +Rs 19,135 (PF 1.36); skip_aligned 23 -Rs 4,504 (PF 0.82, BOTH halves "
                     "negative); only_aligned 44 +Rs 17,452. The filter helps NIFTY and loses money on SENSEX on "
                     "19-23 trades - that is a coin landing the same way twice, not an edge. REJECTED as a rule. "
                     "The run also found a real bug: features() and mtf_align() used a 120-bar window, which "
                     "resamples to 40 15m bars, short of the 55 the 15m EMA50 needs - so the 15m half of "
                     "ema_align was ALWAYS 'unknown' and the model's -0.75 coefficient was 5m-only. With a "
                     "240-bar window the coefficient falls to -0.41 (VM refit, 222 rows; -0.32 on the 194-row "
                     "local run) - still negative, but the -0.75 was 5m-only. The refit on the VM gives OOS AUC "
                     "0.533, down from 0.566 with the bug, and the R head is positive in 4/4 folds but tiny "
                     "(r_corr 0.18/0.07/0.06/0.10), so it ranks barely better than chance. Slice AUCs 0.42 / "
                     "0.50 / 0.51 / 0.56 say the pooled 0.533 is mostly the model telling NIFTY and SENSEX apart, "
                     "not good trades from bad. Stays SHADOW; no filter earns its keep.",
         "status": "rejected", "owner": "owner request"},
        {"id": 20, "date": "2026-10-28", "area": "process", "name": "Per-day trade count and P&L, pushed to the phone",
         "change": "New engine/daily.py: closed trades grouped by the day they were OPENED (the book's own "
                   "convention), rendered as a short ASCII message. GET /api/daily (read-only), "
                   "POST /api/daily/send, desk.py daily [--send]. Evening cron 15:45 IST on weekdays.",
         "evidence": "Answers the owner's question directly: trades today, P&L today, the last ten trading "
                     "days, all-time, and whether a day stop fired. Uses the same opened_at[:10] grouping as "
                     "PaperTrader.today_closed, so the message and the journal cannot disagree. Tests pin the "
                     "grouping, the loss-stop wording, the empty day, and that the text stays ASCII.",
         "status": "promoted", "owner": "owner request"},
        {"id": 21, "date": "2026-10-28", "area": "infra", "name": "A refit may not train on a worse feed than the model on disk",
         "change": "decision.refit(force=False) now refuses when the training feed is a downgrade (Angel -> "
                   "Yahoo) or when the session count shrinks below 90% of the current model's. A refused refit "
                   "returns the existing card with refit_refused set and does NOT overwrite the model file. "
                   "POST /api/decision/refit?force=1 overrides.",
         "evidence": "Found while re-running the dataset build: on 28 Oct the VM's Angel feed started "
                     "returning EMPTY for 5m and 15m, so long_history silently fell back to Yahoo - 60 "
                     "sessions from 2026-08-03 instead of 64 from 2026-07-24. The model card still said "
                     "angel_one / 222 rows. Two bugs: (1) a refit during an outage would have replaced a "
                     "working 222-row model with a 194-row delayed-feed one and called it a refit; (2) a "
                     "dataset under MIN_TRAIN overwrote the good model with w=null, which blanks every shadow "
                     "decision until someone notices. The weekly cron runs unattended, so this would have "
                     "happened on a Monday morning with no warning.",
         "status": "promoted", "owner": "owner request"},
    ]


def all() -> list[dict]:
    """Every experiment, oldest first.

    Seeds the file on first read, adds newly committed rows, and lets a row's STATUS move
    (proposed -> testing -> promoted/rejected) when the code says so. Evidence is never rewritten:
    the record of what was believed at the time has to survive, or the registry is just a diary.
    """
    seeds = _seed()
    if not FILE.exists():
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text("\n".join(json.dumps(r) for r in seeds) + "\n", encoding="utf-8")
        return seeds
    try:
        rows = [json.loads(line) for line in FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:  # noqa: BLE001 - a corrupt line must not kill the page
        return []
    # A row committed after this file was created still belongs in the record. Merge it in by id,
    # but never rewrite a file we could not read.
    by_id = {r.get("id"): r for r in rows}
    changed = False
    for s in seeds:
        cur = by_id.get(s["id"])
        if cur is None:
            rows.append(s)
            changed = True
        elif cur.get("status") != s["status"]:
            cur["status"] = s["status"]
            changed = True
    if changed:
        rows = sorted(rows, key=lambda r: r.get("id", 0))
        FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return rows


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
