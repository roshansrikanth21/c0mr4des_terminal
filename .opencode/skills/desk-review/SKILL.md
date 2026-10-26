---
name: desk-review
description: >-
  Evening review of the c0mr4des paper desk. Use after 15:30 IST, or when the owner
  says "review today", "how did we do", "pull the book", "daily review", "check the
  capital test", or asks for the honest read. Pulls today's trades, the named failure
  patterns, the go/no-go gate, the four-capital-case study and the experiment registry,
  then states what the numbers do and do not prove.
---

# Desk review

One read-only pull, then the same review every evening: what happened, why, and what
it does not prove yet.

## Run

From the repo root (Windows, repo venv):

```powershell
.\.venv\Scripts\python.exe scripts\desk.py review
```

No tunnel? Run it on the VM: add `--ssh <user@host>` (or set `desk.local.json`).
`--json` gives the raw payloads.

## Write the review in this order

1. **Today** — trades, wins, P&L.
2. **The trades themselves** — for each closed trade today: time, side, strike,
   entry -> exit, exit reason, P&L. Newest first. Use the API's `closed` list; never
   reconstruct a trade from memory.
3. **Honest read** — quote the `lessons.flags` text. These are computed from the book,
   not opinions. If the concentration flag fires, say it in the same words: the profit
   is one or two holdings, not an edge.
4. **Gate** — the strategy's go/no-go verdict and the failing checks. Never upgrade
   `NOT YET (too few trades)` to "working". Under 20 trades the gate does not speak.
5. **Capital test** — day n/7 and each case's equity, net, yield, trades, busts. If the
   week is young, say the sample is too small to rank the capital sizes.
6. **Experiments** — anything in `testing`, by id and name. Do not promote anything
   without the owner's explicit decision and a new evidence row.
7. **One next action** — the single thing worth doing, or "nothing; keep collecting".

## Rules

- Every number comes from the API output. No estimates, no "about", no memory.
- P&L is after charges; say so once.
- A loss is not a bug. Diagnose the pattern, do not explain it away.
- One week of four or five trades per case is evidence about sizing, not proof of an
  edge. State that whenever the capital table is shown.
- Read-only: no resets, no settings changes, no order placement. If a reset looks
  necessary, propose it and wait.

## If the API is unreachable

Say so, state the last known review time from the conversation, and stop. Do not
reconstruct a day from memory or from the signal log on disk unless the owner asks for
that specific fallback.
