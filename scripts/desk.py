#!/usr/bin/env python3
"""Read-only desk checks for the c0mr4des terminal.

Three jobs, one tool:

    desk.py preopen    before 09:15 - is the desk able to trade today?
    desk.py review     after 15:30 - what happened, what does it mean?
    desk.py incident   something is wrong - gather facts, name the safe fix.

It only reads: /api/health, /api/signal, /api/paper, /api/settings, /api/capital-test,
/api/experiments, and (with --ssh) systemd, memory, disk and the service log. It never
places an order, never writes settings, never restarts anything, and never edits a book.

How to reach the API
--------------------
The VM binds the API to 127.0.0.1, so from the owner's PC there are two ways:

  * open the tunnel (watch.bat) and use the default  http://127.0.0.1:8100
  * pass --ssh user@host and the tool runs curl on the VM itself

Host and key can be set in desk.local.json next to this repo (git-ignored), or with
C0MR4DES_SSH / C0MR4DES_KEY / C0MR4DES_URL.

Output is ASCII only: PowerShell mangles the rupee sign and arrows.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "desk.local.json"
DEFAULT_URL = os.getenv("C0MR4DES_URL", "http://127.0.0.1:8100")
REMOTE_URL = "http://127.0.0.1:8100"


class DeskError(RuntimeError):
    pass


def local_config() -> dict:
    try:
        return json.loads(LOCAL.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no config is a valid state
        return {}


def now_ist() -> datetime:
    return datetime.now(IST)


def ago(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:  # noqa: BLE001
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    secs = int((now_ist() - dt).total_seconds())
    if secs < 0:
        return "in the future"
    if secs < 90:
        return f"{secs}s ago"
    if secs < 5400:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h {secs % 3600 // 60}m ago"


def money(value) -> str:
    try:
        return f"Rs {float(value):,.0f}"
    except Exception:  # noqa: BLE001
        return "Rs --"


def pct(value, digits=2) -> str:
    try:
        return f"{float(value):+.{digits}f}%"
    except Exception:  # noqa: BLE001
        return "--"


class Desk:
    def __init__(self, url: str, host: str | None = None, key: str | None = None):
        self.url = url.rstrip("/")
        self.host = host
        self.key = key or str(Path.home() / ".ssh" / "c0mr4des_key.pem")

    # ---------- transport ----------
    def ssh(self, command: str, timeout: int = 60) -> str:
        if not self.host:
            raise DeskError("no SSH host configured")
        args = ["ssh", "-i", self.key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                self.host, command]
        try:
            res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise DeskError(f"ssh timed out after {timeout}s") from exc
        except FileNotFoundError as exc:
            raise DeskError("ssh is not installed on this machine") from exc
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip().splitlines()
            raise DeskError("ssh failed: " + (detail[-1] if detail else f"exit {res.returncode}"))
        return res.stdout

    def get(self, path: str) -> dict:
        if self.host:
            body = self.ssh(f"curl -sS --max-time 25 '{REMOTE_URL}{path}'")
        else:
            try:
                with urllib.request.urlopen(self.url + path, timeout=25) as res:
                    body = res.read().decode("utf-8")
            except urllib.error.URLError as exc:
                raise DeskError(
                    f"cannot reach {self.url}{path} ({exc.reason}). Start the tunnel "
                    "(double-click c0mr4des-watch.bat) or pass --ssh user@host."
                ) from exc
        try:
            return json.loads(body)
        except Exception as exc:  # noqa: BLE001
            if body.lstrip().startswith("<"):
                raise DeskError(
                    f"{path} returned HTML, not JSON. The server on {self.url} is an older "
                    "build or a static server - use --ssh, or restart that server."
                ) from exc
            raise DeskError(f"{path} did not return JSON: {body[:200]!r}")

    def post(self, path: str, timeout: int = 240) -> dict:
        """Only used for explicit, owner-initiated actions (e.g. a model refit). Never a trade."""
        if self.host:
            body = self.ssh(f"curl -sS --max-time {timeout} -X POST '{REMOTE_URL}{path}'", timeout=timeout + 20)
        else:
            req = urllib.request.Request(self.url + path, method="POST", data=b"")
            with urllib.request.urlopen(req, timeout=timeout) as res:
                body = res.read().decode("utf-8")
        try:
            return json.loads(body)
        except Exception as exc:  # noqa: BLE001
            raise DeskError(f"{path} did not return JSON: {body[:200]!r}") from exc


def line(status: str, name: str, detail: str) -> str:
    return f"[{status:<4}] {name:<13} {detail}"

def emit(checks: list[dict], facts: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"checks": checks, "facts": facts}, indent=1, default=str))
        return
    for c in checks:
        print(line(c["status"], c["name"], c["detail"]))
        if c.get("fix") and c["status"] != "OK":
            print(f"       fix: {c['fix']}")


# ---------------------------------------------------------------- pre-open
def preopen(d: Desk) -> tuple[list[dict], dict]:
    checks: list[dict] = []
    facts: dict = {}

    health = d.get("/api/health")
    facts["health"] = health
    checks.append({"name": "API", "status": "OK", "detail": "responding"})
    checks.append({
        "name": "Broker",
        "status": "OK" if health.get("broker_connected") else "FAIL",
        "detail": "Angel One connected" if health.get("broker_connected")
                  else "Angel One NOT connected",
        "fix": "sudo systemctl restart c0mr4des, wait 10s, check /api/health. "
               "Do not log in from this laptop.",
    })

    sig = d.get("/api/signal?symbol=NIFTY")
    facts["signal"] = sig
    sess = sig.get("session") or {}
    health_of_data = sig.get("data_source") or "unknown"
    delayed = bool(sig.get("data_delayed"))
    checks.append({
        "name": "Data",
        "status": "WARN" if delayed else "OK",
        "detail": f"{health_of_data}{' (delayed)' if delayed else ' (live)'}",
        "fix": "Delayed prices mean Angel is not feeding the engine. Same restart as Broker.",
    })
    age = ago(sig.get("generated_at", ""))
    stale = "m ago" in age and int(age.split("m")[0]) >= 15
    checks.append({
        "name": "Freshness",
        "status": "WARN" if stale else "OK",
        "detail": f"last analysis {age} ({str(sig.get('generated_at', ''))[11:16]})",
        "fix": "If this is during market hours the loop is stuck; see incident.",
    })

    trading = bool(sess.get("is_trading_day"))
    checks.append({
        "name": "Trading day",
        "status": "OK" if trading else "WARN",
        "detail": (f"{sess.get('phase', 'closed')} - market opens 09:15"
                   if trading else "holiday / weekend - market closed"),
    })
    if trading:
        checks.append({
            "name": "Session",
            "status": "OK",
            "detail": (f"phase {sess.get('phase')} | entry window 09:30-15:00 | "
                       f"square-off by {sess.get('square_off_by')}"),
        })
        checks.append({
            "name": "Expiry",
            "status": "WARN" if sess.get("is_expiry_day") else "OK",
            "detail": (f"{sess.get('expiry')} ({sess.get('expiry_weekday')}), "
                       f"{sess.get('days_to_expiry')} trading day(s) away"
                       + (" - TODAY" if sess.get("is_expiry_day") else "")),
            "fix": "Expiry day: First-Hour and First-30 both sit out by design. "
                   "Expect no trades unless the Expiry slot is enabled.",
        })

    paper = d.get("/api/paper")
    facts["paper"] = paper
    opens = paper.get("open") or []
    checks.append({
        "name": "Book",
        "status": "FAIL" if opens else "OK",
        "detail": (f"{len(opens)} position(s) still open from a previous session"
                   if opens else "flat - no carried positions"),
        "fix": "A carried paper position closes on the next analysis as 'stale'. If it "
               "does not, the loop is down; see incident.",
    })

    rules = paper.get("entry_rules") or {}
    gate = paper.get("last_gate") or {}
    blocked = gate.get("blocked") or []
    gate_age = ago(gate.get("at", "")) if blocked else ""
    detail = (f"last entry {rules.get('no_entry_after', '--')} | "
              f"time stop {rules.get('time_stop', '--')} | "
              f"charges <= {rules.get('max_charge_pct', '--')}% | "
              f"theta <= {rules.get('max_theta_pct', '--')}%/day")
    if blocked:
        detail += f" | blocked {gate_age}: " + "; ".join(gate.get("reasons") or blocked)
    checks.append({
        "name": "Entry gate",
        "status": "OK",
        "detail": detail,
        "fix": "A blocked gate is the rule working: the contract is too close to expiry or too "
               "cheap to pay for its own costs. No trade is the correct outcome.",
    })

    settings = d.get("/api/settings")
    facts["settings"] = settings
    strat = settings.get("autopilot_strategies") or []
    checks.append({
        "name": "Strategies",
        "status": "OK" if strat else "FAIL",
        "detail": " + ".join(strat) if strat else "none enabled - the bot will not trade",
        "fix": "Settings page -> enable First-Hour and/or First-30.",
    })
    checks.append({
        "name": "Risk",
        "status": "OK",
        "detail": (f"capital {money(settings.get('capital'))} | risk "
                   f"{settings.get('risk_per_trade_pct')}%/trade | "
                   f"{settings.get('max_trades_per_day')} trades/day | daily loss "
                   f"{settings.get('max_daily_loss_pct')}% | "
                   f"{settings.get('max_open_positions')} open at once"),
    })

    cap = d.get("/api/capital-test")
    facts["capital_test"] = cap
    cases = cap.get("cases") or []
    open_cases = [c["id"] for c in cases if c.get("open")]
    if cap.get("started_at"):
        detail = (f"day {cap.get('day_index')}/{cap.get('week_days')} | "
                  + " | ".join(f"{c['id']} {money(c['equity'])} ({pct(c['return_pct'])})"
                               for c in cases))
        if open_cases:
            detail += f" | open: {', '.join(open_cases)}"
    else:
        detail = "not started yet - the clock starts on the first live session"
    checks.append({"name": "Capital test", "status": "OK", "detail": detail})

    sp = d.get("/api/spreads")
    facts["spreads"] = sp
    pos = sp.get("open")
    detail = (f"stake {money(sp.get('stake'))} | equity {money(sp.get('equity'))} | "
              f"{sp.get('trades', 0)} closed | net {money(sp.get('net'))} | "
              f"rules v{sp.get('rules_version', '?')}")
    if pos:
        detail += (f" | open {pos.get('symbol_hint')} "
                   f"credit {money(pos.get('credit_value'))} mark {pos.get('mark')}")
    checks.append({"name": "Spreads", "status": "OK", "detail": detail})

    sides = sig.get("sides") or {}
    call, put = sides.get("call") or {}, sides.get("put") or {}
    if call or put:
        checks.append({
            "name": "One lot",
            "status": "OK",
            "detail": (f"NIFTY call {money(call.get('lot_cost'))} | "
                       f"put {money(put.get('lot_cost'))} | "
                       f"affordable on {money(settings.get('capital'))}: "
                       f"{', '.join(sides.get('affordable') or []) or 'neither side'}"),
        })

    verdict = sig.get("verdict") or "NO TRADE"
    mtf = sig.get("mtf") or {}
    checks.append({
        "name": "Preview",
        "status": "OK",
        "detail": (f"engine {verdict} (score {sig.get('score')}) | "
                   f"MTF {mtf.get('phase', '--')} | ORB "
                   f"{(sig.get('orb') or {}).get('status', '--')}"),
    })

    # The target has to be an R-multiple: a flat number of points demands a different win rate
    # every morning, because the stop is the other side of a range that changes size daily.
    ob = sig.get("orb") or {}
    rng = ob.get("range_points")
    if rng:
        checks.append({
            "name": "ORB target",
            "status": "OK",
            "detail": (f"range {rng:.0f} pts | 2R target {2 * rng:.0f} pts (needs 33.3% wins) | "
                       f"a flat 10-pt target today would need {round(rng / (rng + 10) * 100, 1)}% wins"),
        })

    facts["generated_at"] = sig.get("generated_at")
    return checks, facts


# ---------------------------------------------------------------- review
def review(d: Desk) -> tuple[list[dict], dict]:
    checks: list[dict] = []
    facts: dict = {}
    paper = d.get("/api/paper")
    cap = d.get("/api/capital-test")
    exps = d.get("/api/experiments").get("experiments") or []
    facts.update({"paper": paper, "capital_test": cap, "experiments": exps})

    today = (paper.get("today") or {})
    allt = (paper.get("all_time") or {})
    checks.append({
        "name": "Today",
        "status": "OK",
        "detail": (f"{today.get('trades', 0)} trade(s), {today.get('wins', 0)} won, "
                   f"{money(today.get('pnl', 0))}"),
    })
    checks.append({
        "name": "All-time",
        "status": "OK",
        "detail": (f"{allt.get('trades', 0)} trades | {money(allt.get('pnl', 0))} | "
                   f"win rate {allt.get('win_rate') if allt.get('win_rate') is not None else '--'}%"),
    })

    today_str = now_ist().date().isoformat()
    for t in [x for x in (paper.get("closed") or []) if str(x.get("opened_at", ""))[:10] == today_str]:
        entry = t.get("entry_premium")
        exit_ = t.get("exit_premium")
        checks.append({
            "name": "  trade",
            "status": "OK",
            "detail": (f"{str(t.get('opened_at', ''))[11:16]} {t.get('side', '?')} "
                       f"{t.get('symbol', '?')} {t.get('lots', '?')} lot | "
                       f"{entry} -> {exit_} ({t.get('reason', '?')}) | "
                       f"{money(t.get('pnl', 0))}"),
        })

    rules = paper.get("entry_rules") or {}
    last = paper.get("last_gate") or {}
    blocked = last.get("blocked") or []
    rule_line = (f"last entry {rules.get('no_entry_after', '--')} | "
                 f"time stop {rules.get('time_stop', '--')} | "
                 f"charges <= {rules.get('max_charge_pct', '--')}% | "
                 f"theta <= {rules.get('max_theta_pct', '--')}%/day")
    if blocked:
        rule_line += f" | last block {ago(last.get('at', ''))}: " + "; ".join(last.get("reasons") or blocked)
    checks.append({"name": "Entry rules", "status": "OK", "detail": rule_line})

    dr = paper.get("day_rules") or {}
    day = paper.get("day") or {}
    if dr:
        day_line = (f"profit stop {money(dr.get('profit_stop'))} (+{dr.get('profit_pct')}%) | "
                    f"loss stop {money(dr.get('loss_stop'))} (-{dr.get('loss_pct')}%) | "
                    f"a trade may only risk the room left")
        if day.get("stopped"):
            day_line += f" | STOPPED ({day['stopped']}) at {money(day.get('pnl', 0))}"
        elif day.get("room") is not None:
            day_line += f" | room left today {money(day.get('room'))}"
        checks.append({"name": "Day rules", "status": "OK", "detail": day_line})

    lessons = paper.get("lessons") or {}
    flags = lessons.get("flags") or []
    checks.append({
        "name": "Honest read",
        "status": "OK",
        "detail": f"{len(flags)} flag(s)" if flags else "nothing to read yet",
    })
    for i, f in enumerate(flags):
        checks.append({"name": f"  read {i + 1}", "status": "OK", "detail": f.get("text", "")})

    gate = paper.get("go_no_go") or {}
    for name, g in gate.items():
        failing = [c for c in (g.get("checks") or []) if not c.startswith("OK ")]
        checks.append({
            "name": f"Gate {name}",
            "status": "OK" if g.get("verdict") == "GO" else "WARN",
            "detail": g.get("verdict", "?") + (" | " + "; ".join(failing) if failing else ""),
        })

    cases = cap.get("cases") or []
    if cap.get("started_at"):
        checks.append({
            "name": "Capital",
            "status": "OK",
            "detail": f"day {cap.get('day_index')}/{cap.get('week_days')} | "
                      f"leader {cap.get('leader') or 'none yet'}",
        })
        for c in cases:
            checks.append({
                "name": f"  case {c['id']}",
                "status": "WARN" if c.get("busts") else "OK",
                "detail": (f"{c['label']:<20} equity {money(c['equity'])} | net "
                           f"{money(c['net'])} | yield {pct(c['return_pct'])} | "
                           f"{c['trades']} trades | busts {c['busts']}"),
            })
        checks.append({"name": "  note", "status": "OK", "detail": cap.get("note", "")})
    else:
        checks.append({"name": "Capital", "status": "OK",
                       "detail": "not started - the week begins on the first live session"})

    sp = d.get("/api/spreads")
    facts["spreads"] = sp
    pos = sp.get("open")
    versions = sp.get("by_version") or {}
    vtxt = " | ".join(f"v{v} {b.get('trades', 0)}tr {money(b.get('net', 0))}"
                      for v, b in sorted(versions.items()))
    checks.append({
        "name": "Spreads",
        "status": "OK",
        "detail": (f"stake {money(sp.get('stake'))} | equity {money(sp.get('equity'))} | "
                   f"net {money(sp.get('net'))} | {sp.get('trades', 0)} closed | "
                   f"rules v{sp.get('rules_version', '?')}"
                   + (f" ({vtxt})" if len(versions) > 1 else "")
                   + (f" | win rate {sp.get('win_rate')}%" if sp.get("win_rate") is not None else "")),
    })
    for t in [x for x in (sp.get("closed") or []) if str(x.get("closed_at", ""))[:10] == today_str]:
        checks.append({
            "name": "  spread",
            "status": "OK",
            "detail": (f"{str(t.get('opened_at', ''))[11:16]} {t.get('label')} "
                       f"{int(t.get('short_strike', 0))}/{int(t.get('long_strike', 0))} | "
                       f"credit {t.get('credit')} -> debit {t.get('exit_debit')} "
                       f"({t.get('reason')}) | {money(t.get('pnl', 0))}"),
        })
    if pos:
        checks.append({
            "name": "  open",
            "status": "OK",
            "detail": (f"{pos.get('symbol_hint')} | credit {money(pos.get('credit_value'))} | "
                       f"mark {pos.get('mark')} | unrealized {money(pos.get('unrealized', 0))}"),
        })

    try:
        dec = d.get("/api/decision")
    except DeskError as exc:
        dec = {}
        checks.append({"name": "Decision", "status": "WARN",
                       "detail": f"not available on this server ({exc})"})
    facts["decision"] = dec
    dc = dec.get("card") or {}
    if dc.get("status") == "none":
        checks.append({"name": "Decision", "status": "WARN",
                       "detail": "not fitted - run: desk.py decision-refit"})
    else:
        wf_ev = dc.get("best_ev_filter") or {}
        age = dc.get("age_days")
        checks.append({
            "name": "Decision",
            "status": "WARN" if (dc.get("status") != "active" or (age or 0) > 8) else "OK",
            "detail": (f"{dc.get('status', '?').upper()} | {dc.get('version')} on "
                       f"{dc.get('samples')} rows / {dc.get('sessions')} sessions | "
                       f"OOS AUC {dc.get('oos_auc')} | best EV filter "
                       f"{money(wf_ev.get('net', 0))} on {wf_ev.get('trades', 0)} vs "
                       f"{money(dc.get('all_net', 0))} taking all | fitted "
                       f"{age if age is not None else '?'}d ago"
                       + (" | STALE - the weekly refit did not run" if (age or 0) > 8 else "")),
        })
    sc = dec.get("shadow") or {}
    if sc.get("trades"):
        checks.append({
            "name": "  shadow",
            "status": "OK",
            "detail": (f"{sc['trades']} scored | said {sc.get('predicted_p')}% green, got "
                       f"{sc.get('actual_win_rate')}% | said {sc.get('predicted_ev_r')}R, got "
                       f"{sc.get('actual_r')}R | rank corr {sc.get('rank_corr')} | "
                       f"brier {sc.get('brier')}"),
        })
    elif sc:
        checks.append({"name": "  shadow", "status": "OK", "detail": sc.get("reason", "")})
    for key, live in dec.items():
        if key in ("card", "shadow"):
            continue
        for name, v in (live or {}).items():
            if not v or v.get("p_win") is None:
                continue
            checks.append({
                "name": f"  {name}",
                "status": "OK",
                "detail": (f"P(green) {float(v['p_win']) * 100:.0f}% vs break-even "
                           f"{float(v.get('breakeven') or 0) * 100:.0f}% | expected "
                           f"{float(v.get('ev_r') or 0):+.2f}R | {v.get('action')} "
                           f"({v.get('confidence')})"),
            })

    testing = [e for e in exps if e.get("status") == "testing"]
    if testing:
        checks.append({
            "name": "Experiments",
            "status": "OK",
            "detail": "; ".join(f"#{e['id']} {e.get('name')}" for e in testing[-4:]),
        })

    opens = paper.get("open") or []
    checks.append({
        "name": "Open",
        "status": "WARN" if opens else "OK",
        "detail": ("; ".join(f"{p.get('strategy')} {p.get('symbol')} "
                             f"{money(p.get('unrealized', 0))}" for p in opens)
                   if opens else "none"),
    })
    return checks, facts


# ---------------------------------------------------------------- incident
def remote_facts(d: Desk) -> dict:
    if not d.host:
        return {}
    script = (
        "echo @@SERVICE; systemctl is-active c0mr4des 2>&1; "
        "echo @@SINCE; systemctl show c0mr4des -p ActiveEnterTimestamp --value 2>&1; "
        "echo @@RESTARTS; systemctl show c0mr4des -p NRestarts --value 2>&1; "
        "echo @@MEM; free -m | awk 'NR==2{print $3\" \"$2}'; "
        "echo @@DISK; df -h / | awk 'NR==2{print $5}'; "
        "echo @@LOG; journalctl -u c0mr4des -n 40 --no-pager 2>&1 | tail -40"
    )
    raw = d.ssh(script, timeout=60)
    out: dict[str, str] = {}
    key = None
    for row in raw.splitlines():
        if row.startswith("@@"):
            key = row[2:].strip()
            out[key] = ""
        elif key:
            out[key] += row + "\n"
    return {k: v.strip() for k, v in out.items()}


def incident(d: Desk) -> tuple[list[dict], dict]:
    checks: list[dict] = []
    facts: dict = {}
    api_up = True
    health = {}
    try:
        health = d.get("/api/health")
        facts["health"] = health
    except DeskError as exc:
        api_up = False
        checks.append({"name": "API", "status": "FAIL", "detail": str(exc),
                       "fix": "Is the VM up? ssh in and run: systemctl status c0mr4des"})
    if api_up:
        checks.append({"name": "API", "status": "OK", "detail": "responding"})
        checks.append({
            "name": "Broker",
            "status": "OK" if health.get("broker_connected") else "FAIL",
            "detail": "Angel One connected" if health.get("broker_connected") else "Angel One NOT connected",
            "fix": "sudo systemctl restart c0mr4des, wait 10s, re-check. If still down, "
                   "inspect backend/.env ANGEL_* (never print the values).",
        })
        try:
            sig = d.get("/api/signal?symbol=NIFTY")
            facts["signal"] = sig
            age = ago(sig.get("generated_at", ""))
            checks.append({"name": "Freshness", "status": "OK" if ("s ago" in age or "m ago" in age and
                                                                   int(age.split("m")[0]) < 10)
                           else "WARN", "detail": f"last analysis {age}"})
        except DeskError as exc:
            checks.append({"name": "Signal", "status": "FAIL", "detail": str(exc)})

    remote = {}
    if d.host:
        try:
            remote = remote_facts(d)
            facts["remote"] = remote
        except DeskError as exc:
            checks.append({"name": "Remote", "status": "FAIL", "detail": str(exc),
                           "fix": "The VM may be unreachable. Check the Azure portal / network."})
    if remote:
        service = (remote.get("SERVICE") or "").strip()
        checks.append({"name": "Service", "status": "OK" if service == "active" else "FAIL",
                       "detail": f"{service or 'unknown'} | since {remote.get('SINCE', '?')} | "
                                 f"restarts {remote.get('RESTARTS', '?')}"})
        mem = (remote.get("MEM") or "").split()
        if len(mem) == 2:
            used, total = int(mem[0]), int(mem[1])
            checks.append({"name": "Memory", "status": "WARN" if used / total > 0.85 else "OK",
                           "detail": f"{used} / {total} MB used"})
        checks.append({"name": "Disk", "status": "OK", "detail": f"/ at {remote.get('DISK', '?')}"})
        log = remote.get("LOG") or ""
        bad = [ln for ln in log.splitlines()
               if any(w in ln for w in ("Traceback", "ERROR", "CRITICAL", "Invalid Token"))]
        checks.append({"name": "Log", "status": "WARN" if bad else "OK",
                       "detail": (bad[-1][:160] if bad else "no errors in the last 40 lines")})
        facts["log_tail"] = log.splitlines()[-12:]
    return checks, facts


def triage(checks: list[dict], facts: dict) -> list[str]:
    failed = {c["name"] for c in checks if c["status"] in ("FAIL", "WARN")}
    out: list[str] = []
    if "API" in failed:
        out += [
            "API unreachable.",
            "  1. ssh to the box and run: systemctl status c0mr4des --no-pager",
            "  2. if inactive: sudo systemctl restart c0mr4des && sleep 5 && curl -s localhost:8100/api/health",
            "  3. if active but unreachable: journalctl -u c0mr4des -n 60 --no-pager",
            "  4. if the VM itself is down: start it in the Azure portal, wait, re-check.",
        ]
    if "Broker" in failed:
        out += [
            "Angel One is disconnected. The usual cause is an expired session token.",
            "  1. sudo systemctl restart c0mr4des (the app logs in again on startup).",
            "  2. wait 10s, check /api/health for broker_connected=true.",
            "  3. still false: the credentials in backend/.env are wrong or the account is locked.",
            "  Do not log in from your laptop; the server owns the session.",
        ]
    if "Service" in failed:
        out += ["The systemd unit is not active. Restart it, then read the last 40 log lines."]
    if "Freshness" in failed:
        out += [
            "The market loop has not produced an analysis recently.",
            "  1. Confirm the market is actually open (IST 09:15-15:30, not a holiday).",
            "  2. curl -s localhost:8100/api/session and look at generated timestamps.",
            "  3. If it is stale during market hours: restart the service once.",
            "  4. Do not restart twice in two minutes; Angel rate-limits logins.",
        ]
    if "Memory" in failed:
        out += ["Memory is above 85%. Restart the service; if it recurs, the box needs more RAM."]
    if "Log" in failed:
        out += ["The log names an error above. Fix that cause before restarting in a loop."]
    if not out:
        out = ["No fault found by these checks. If the UI is wrong, the problem is the tunnel "
               "or the browser, not the desk."]
    return out


# ---------------------------------------------------------------- main
def decision_refit(d: Desk) -> tuple[list[dict], dict]:
    """Refit the decision model. Explicit, owner-initiated, never part of the trading loop."""
    out = d.post("/api/decision/refit")
    card = out.get("card") or {}
    wf = out.get("walk_forward") or {}
    best_ev = (wf.get("best_ev_filter") or {})
    refused = card.get("refit_refused")
    checks = [{
        "name": "Decision",
        "status": "OK" if card.get("ok") else "WARN",
        "detail": (f"{card.get('status', '?').upper()} | {card.get('version')} | "
                   f"{card.get('samples')} rows / {card.get('sessions')} sessions | "
                   f"source {card.get('source')} | "
                   f"OOS AUC {wf.get('oos_auc')} | best EV filter {money(best_ev.get('net', 0))} "
                   f"on {best_ev.get('trades', 0)} vs {money(wf.get('all_net', 0))} taking all"),
    }, {"name": "  verdict",
        "status": "WARN" if refused else "OK",
        "detail": str(refused or card.get("promotion") or card.get("reason") or "")}]
    for f in (wf.get("ev_filters") or []):
        checks.append({"name": f"  ev>={f['threshold']}", "status": "OK",
                       "detail": f"{f['trades']:>3} trades | {money(f['net'])} | win {f['win_rate']}%"})
    for f in (wf.get("folds") or []):
        checks.append({"name": f"  fold {f['fold']}", "status": "OK",
                       "detail": (f"train {f['train']:>3} ({f['train_days']}d) test {f['test']:>2} "
                                  f"({f['test_days']}d) | AUC {f['auc']} | R corr {f.get('r_corr')}")})
    for k, v in (wf.get("per_instrument") or {}).items():
        checks.append({"name": f"  {k} only", "status": "OK",
                       "detail": (f"OOS AUC {v.get('oos_auc')} on {v.get('trades')} trades vs pooled "
                                  f"{wf.get('oos_auc')} | slices {v.get('slices')}")})
    return checks, {"decision": out}


def daily(d: Desk, send: bool = False) -> tuple[list[dict], dict]:
    """The phone summary, printed. `--send` also pushes it (the one POST this command makes)."""
    out = d.post("/api/daily/send") if send else d.get("/api/daily")
    return [], {"daily": out.get("report") or {}, "text": out.get("text") or "",
                "sent": out.get("sent")}


def main(argv=None) -> int:
    cfg = local_config()
    ap = argparse.ArgumentParser(description="Read-only c0mr4des desk checks.")
    ap.add_argument("command", choices=("preopen", "review", "incident", "decision-refit", "daily"))
    ap.add_argument("--send", action="store_true", help="daily: push the summary to the phone")
    ap.add_argument("--url", default=os.getenv("C0MR4DES_URL") or cfg.get("url") or DEFAULT_URL)
    default_host = os.getenv("C0MR4DES_SSH") or cfg.get("ssh")
    ap.add_argument("--ssh", nargs="?", const=default_host, default=None,
                    help="user@host - run the API calls on the VM instead of through a tunnel "
                         "(no value: use desk.local.json / C0MR4DES_SSH)")
    ap.add_argument("--key", default=os.getenv("C0MR4DES_KEY") or cfg.get("key"),
                    help="SSH key path (default ~/.ssh/c0mr4des_key.pem)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    d = Desk(args.url, args.ssh, args.key)
    run = {"preopen": preopen, "review": review, "incident": incident,
           "decision-refit": decision_refit, "daily": lambda dd: daily(dd, args.send)}[args.command]
    via = f"ssh {args.ssh}" if args.ssh else args.url
    try:
        checks, facts = run(d)
    except DeskError as exc:
        # The owner's normal path: no tunnel open, or a stale local server on 8100. Fall back
        # to the VM when a host is configured, and say so instead of failing silently.
        if args.ssh is None and default_host:
            print(f"[note] local API: {exc}")
            print(f"[note] reading the desk over ssh {default_host} instead")
            try:
                checks, facts = run(Desk(args.url, default_host, args.key))
                via = f"ssh {default_host}"
            except DeskError as exc2:
                print(f"[FAIL] API           {exc2}")
                return 1
        else:
            print(f"[FAIL] API           {exc}")
            print("       The desk cannot be inspected. Start the tunnel or pass --ssh user@host.")
            return 1

    when = now_ist().strftime("%a %d %b %Y %H:%M IST")
    if not args.json:
        print(f"C0MR4DES {args.command.upper()} - {when}")
        print(f"via {via}")
        print("-" * 78)
    emit(checks, facts, args.json)

    if args.command == "daily":
        if not args.json:
            print(facts.get("text") or "")
            if args.send:
                print("-" * 78)
                print("Sent." if facts.get("sent")
                      else "NOT sent - no TELEGRAM_BOT_TOKEN/CHAT_ID or NTFY_TOPIC, or the send failed.")
        return 0

    if args.command == "incident" and not args.json:
        print("-" * 78)
        print("TRIAGE")
        for row in triage(checks, facts):
            print("  " + row)
        print("\nDO NOT")
        for row in ("set LIVE_TRADING=true to 'test' anything",
                    "place a manual order to 'fix' the paper book",
                    "delete or reset data files mid-session",
                    "restart more than once in two minutes (Angel rate-limits logins)"):
            print("  - " + row)
        log = facts.get("log_tail") or []
        if log and not args.json:
            print("\nLAST LOG LINES")
            for row in log:
                print("  " + row[:160])
    elif args.command == "preopen" and not args.json:
        print("-" * 78)
        failed = [c for c in checks if c["status"] == "FAIL"]
        warned = [c for c in checks if c["status"] == "WARN"]
        if failed:
            print("BLOCKED: fix the FAIL line(s) before trusting today's trades.")
        elif warned:
            print("OK to run, with the warnings above.")
        else:
            print("All clear. The loop trades on its own; nothing for you to do at 09:15.")
    elif args.command == "review" and not args.json:
        print("-" * 78)
        print("Review is read-only. Nothing above changed a book, a setting or an order.")
    return 0 if not any(c["status"] == "FAIL" for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
