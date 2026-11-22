---
name: desk-incident
description: >-
  Runbook for a broken c0mr4des desk. Use when the dashboard stops loading, Angel One
  disconnects, prices go stale, the service is down or crash-looping, a trade looks
  wrong, or the owner says "it's not working", "broker disconnected", "no signals",
  "the bot is stuck". Gathers read-only facts from the API and the VM, names the fault,
  and gives the safe fix in order.
---

# Desk incident

First facts, then one fix. Never "try things" on a live session.

## Run

```powershell
.\.venv\Scripts\python.exe scripts\desk.py incident --ssh <user@host>
```

Use `--ssh` for real incidents: it adds systemd state, memory, disk and the last 40
log lines. Without it you only get the API view.

## How to work it

1. Read the FACTS block. Separate **the desk is down** (API/broker/service) from
   **you cannot see it** (tunnel/browser). They have different fixes.
2. Match the symptom in TRIAGE. Follow the numbered steps in order.
3. Restarting the service is an **action**: say what you are about to run and why, then
   do it once the owner agrees. If the owner already said "fix it", proceed.
4. After any restart: wait ~10 seconds, then re-run `desk.py incident --ssh ...` (or
   `preopen`) and show that broker and freshness are healthy again.
5. If it is not fixed after one restart, **stop**. Go to the log line. A restart loop
   locks the Angel account and hides the real error.

## Known causes

| Symptom | Usual cause | Safe fix |
|---|---|---|
| `broker_connected: false` | Angel session token expired | restart the service; it logs in on startup |
| API down, service `active` | port/process problem, crash after start | read `journalctl -n 60`; restart once |
| API down, service `inactive` | crash or boot without start | `systemctl restart c0mr4des`; check `NRestarts` |
| Freshness stale during market | loop stuck on a slow data call | wait one cycle (15-30s), then restart once |
| Universe of prices delayed | Angel feed down, yfinance fallback | treat signals as untrusted; do not trade live |
| Memory > 85% | leak or too many browser sessions | restart; if it returns, resize the VM |
| Trades look wrong | inspect the book, not the UI | check `open`/`closed` timestamps; stale exits are labelled |

## Never

- Set `LIVE_TRADING=true` to "test" a fix.
- Log in to Angel from the laptop while the server owns the session.
- Place a manual order to correct the paper book.
- Delete, reset or hand-edit `data/*.json` during a session.
- Restart more than once in two minutes (Angel rate-limits logins).
- Redeploy code mid-session to fix an operational fault.

## Report

Three lines: what broke, what you did, what the desk says now. If the fix needs the
owner (credentials, Azure portal, billing), say exactly what and stop.
