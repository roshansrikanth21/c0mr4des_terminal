---
name: desk-preopen
description: >-
  Pre-open check for the c0mr4des NIFTY/SENSEX terminal. Use before 09:15 IST, or
  whenever the owner asks "can we trade today", "is everything up", "is the bot
  ready", "check the desk", or after the machine or service was restarted. Reports
  whether the API, Angel session, data feed, paper book, settings, expiry day and
  capital-test books are fit to trade, and names the one thing to fix if not.
---

# Desk pre-open

One read-only pass over the live API, then a short verdict. The bot trades on its
own; this check exists so the owner knows whether to trust today's trades.

## Run

From the repo root (Windows, repo venv):

```powershell
.\.venv\Scripts\python.exe scripts\desk.py preopen
```

If that cannot reach the API, run it on the VM instead:

```powershell
.\.venv\Scripts\python.exe scripts\desk.py preopen --ssh <user@host>
```

The host and key can live in `desk.local.json` (git-ignored), so `--ssh` with no
value uses them. `--json` is available for machine use.

If neither works, stop and report the connection error. Do not guess the desk is
healthy, and do not start a second copy of the server to "check".

## How to read it

- **FAIL** — do not trust the session until it is fixed. Say so first, in one line.
- **WARN** — can trade, but say why it matters (expiry day, delayed data, carried position).
- **Trading day = holiday/weekend** — say "market closed, next open <date>" and stop.
- **Expiry day** is the important one: `First-Hour` and `First-30` both sit out on
  expiry days by design. If the Expiry slot is off (it is by default), the bot will
  take **no trade today**. Say that plainly instead of implying it is broken.
- **Capital test "not started"** is normal before the first live session; the week
  clock starts itself.

## Report to the owner

1. The date/time and the verdict: `clear`, `clear with warnings`, or `blocked`.
2. Only the lines that matter: broker, data, book, expiry, strategies, one-lot cost.
3. If blocked: the exact fix from the `fix:` line, and what you need from the owner.
4. End with one sentence: "Nothing to do at 09:15" or "Fix X first".

Do not paste the whole checklist unless the owner asks for it.

## What this never does

No orders, no settings writes, no restarts, no book resets, no logins. It reads the
API and systemd only. A restart or a settings change is an action — propose it and
wait for the owner's yes.
