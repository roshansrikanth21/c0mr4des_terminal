"""C0MR4DE Terminal API - lean core for intraday NIFTY / SENSEX options.

Run:  python -m uvicorn backend.app:app --port 8100
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

load_dotenv(Path(__file__).with_name(".env"))

from .engine import backtest, macro, service, timeline  # noqa: E402
from .engine import capital_test  # noqa: E402
from .engine.trader import go_no_go, live_enabled, paper, place_live_order, replay_paper, scorecard  # noqa: E402
from .engine import replay  # noqa: E402
from datetime import date as _date  # noqa: E402
from .engine import notify  # noqa: E402
from .engine.config import IST  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from .engine.config import INSTRUMENTS  # noqa: E402
from .engine.data import angel, get_candles  # noqa: E402
from .engine.news import radar  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


async def _news_loop():
    while True:
        try:
            await asyncio.to_thread(radar.refresh, True)
        except Exception as exc:  # noqa: BLE001
            log.warning("news refresh failed: %s", exc)
        await asyncio.sleep(90)


LATEST: dict[str, dict] = {}
LATEST_AT: dict[str, float] = {}
_WAKE: asyncio.Event | None = None  # set to cut the market loop's sleep short (replay start/stop)


async def _sleep(seconds: float) -> None:
    global _WAKE
    _WAKE = _WAKE or asyncio.Event()
    try:
        await asyncio.wait_for(_WAKE.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
    _WAKE.clear()


def _wake() -> None:
    if _WAKE is not None:
        _WAKE.set()


def book():
    """Replay trades go to their own paper book so the real paper record stays clean."""
    return replay_paper if replay.active() else paper


_HEALTH: dict = {"bad_since": None, "alerted": False, "fails": 0}


def _check_health(a: dict | None, error: str | None = None) -> None:
    """Telegram the user when the bot is trading blind: delayed data, stale candles or failing analysis."""
    if replay.active():
        return
    now = datetime.now(IST)
    if not timeline.session(now, "NIFTY")["is_open"]:
        _HEALTH.update(bad_since=None, fails=0)
        return
    problem = None
    if error:
        _HEALTH["fails"] += 1
        problem = f"analysis failing ({error[:120]})" if _HEALTH["fails"] >= 3 else None
    else:
        _HEALTH["fails"] = 0
        last = a["candles"][-1]["time"] if a.get("candles") else 0
        if a.get("data_delayed"):
            problem = f"on delayed Yahoo data (Angel {'connected' if a.get('broker_connected') else 'NOT connected'})"
        elif time.time() - last > 15 * 60:
            problem = "candles are more than 15 minutes old"
    if problem:
        _HEALTH["bad_since"] = _HEALTH["bad_since"] or now
        if not _HEALTH["alerted"] and (now - _HEALTH["bad_since"]).total_seconds() >= 180:
            _HEALTH["alerted"] = True
            notify.send(f"DATA WARNING NIFTY: {problem} for 3+ minutes. Alerts may be late - don't act on them "
                        "until you get the all-clear.")
    else:
        if _HEALTH["alerted"]:
            notify.send("DATA OK: back on live Angel One data.")
        _HEALTH.update(bad_since=None, alerted=False)


async def _analyze_and_trade(key: str) -> dict:
    a = await asyncio.to_thread(service.analyze, key)
    if key == "NIFTY":
        _check_health(a)
    a["paper"] = await asyncio.to_thread(book().on_analysis, a, service.load_settings())
    if not replay.active():
        # Four isolated paper books on the same signal. Guarded: a study must never stop the desk.
        try:
            await asyncio.to_thread(capital_test.on_analysis, a, service.load_settings())
        except Exception:  # noqa: BLE001
            log.exception("capital test failed - main loop unaffected")
    LATEST[key], LATEST_AT[key] = a, time.time()
    for ev in a["paper"]["events"]:
        log.info("PAPER %s %s", key, ev)
        msg = notify.fmt_event(ev)
        if msg:
            notify.send(("[REPLAY " + replay.status()["day"] + "] " if replay.active() else "") + msg)
    _maybe_alert_shock(key, a)
    return a


_SENT_FILE = Path(__file__).resolve().parents[1] / "data" / "alerts_sent.json"


def _once(tag: str) -> bool:
    """True the first time a tag is seen today. Persisted, so restarts don't repeat alerts."""
    import json
    today = str(datetime.now(IST).date())
    try:
        sent = json.loads(_SENT_FILE.read_text())
    except Exception:  # noqa: BLE001
        sent = {}
    sent = {k: v for k, v in sent.items() if k == today}  # keep only today's tags
    tags = set(sent.get(today, []))
    if tag in tags:
        return False
    tags.add(tag)
    _SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SENT_FILE.write_text(json.dumps({today: sorted(tags)}))
    return True


def _maybe_alert_shock(key: str, a: dict) -> None:
    sh = a.get("shock")
    if sh and sh.get("active") and a["session"]["is_open"] and not replay.active() and _once(f"shock|{key}"):
        notify.send(f"SHOCK MODE {key}: " + "; ".join(sh["reasons"]) + "\n" + "\n".join("- " + p for p in sh["playbook"][:3]))


def _maybe_replay_summary() -> None:
    st = replay.status()
    if not st.get("finished") or not _once(f"replay|{st['day']}|{st['speed']}"):
        return
    d = _date.fromisoformat(st["day"])
    s = replay_paper.summary(day=d)
    lines = [f"[REPLAY {st['day']}] finished: {s['today']['trades']} trade(s), P&L Rs {s['today']['pnl']:,.0f}"]
    for t in reversed([t for t in s["closed"] if t["opened_at"][:10] == st["day"]]):
        lines.append(f"- {t['strategy']}: {t['side']} {t['strike']} {t['reason']} Rs {t['pnl']:,.0f}")
    notify.send("\n".join(lines))


def _maybe_weekly_report() -> None:
    """Saturday 10:00 IST: the week's paper results per strategy and where each stands on go/no-go."""
    now = datetime.now(IST)
    if replay.active() or now.weekday() != 5 or now.hour < 10 or not _once("weekly"):
        return
    closed = paper.summary()["closed"]
    closed = sorted(closed, key=lambda t: t["closed_at"])
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    week = [t for t in closed if t["opened_at"][:10] >= week_start]
    on = service.load_settings().get("autopilot_strategies", [])
    lines = [f"WEEKLY REPORT w/c {week_start}: {len(week)} trade(s), Rs {sum(t['pnl'] for t in week):,.0f} this week",
             f"All-time paper: Rs {sum(t['pnl'] for t in closed):,.0f} over {len(closed)} trades", ""]
    for name in ("First-Hour", "First-30", "Expiry", "Engine"):
        mine = [t for t in closed if t["strategy"] == name]
        if not mine:
            continue
        sc = scorecard(mine)
        verdict, checks = go_no_go(sc)
        lines.append(f"[{name}]{'' if name in on else ' (switched off)'} Rs {sc['net']:,.0f}, "
                     f"{sc['win_rate']}% won, avg win Rs {sc['avg_win']:,.0f} / avg loss Rs {sc['avg_loss']:,.0f}")
        lines.append(f"  Go/no-go: {verdict}")
        lines += ["  " + c for c in checks]
    notify.send("\n".join(lines))


def _maybe_daily_summary() -> None:
    if replay.active():
        return _maybe_replay_summary()
    now = datetime.now(IST)
    sess = timeline.session(now, "NIFTY")
    if not sess["is_trading_day"] or now.hour * 60 + now.minute < 15 * 60 + 35 or not _once("summary"):
        return
    s = paper.summary()
    today = [t for t in s["closed"] if t["opened_at"][:10] == now.date().isoformat()]
    lines = [f"DAILY SUMMARY {now:%d %b}: {len(today)} paper trade(s), P&L Rs {s['today']['pnl']:,.0f}",
             f"All-time paper: Rs {s['all_time']['pnl']:,.0f} over {s['all_time']['trades']} trades"
             + (f" ({s['all_time']['win_rate']}% won)" if s['all_time']['win_rate'] is not None else "")]
    for t in reversed(today):
        lines.append(f"- {t['strategy']}: {t['side']} {t['strike']} {t['reason']} Rs {t['pnl']:,.0f}")
    for k, v in s.get("by_strategy", {}).items():
        lines.append(f"[{k}] total Rs {v['pnl']:,.0f}, {v['wins']}/{v['trades']} won")
    notify.send("\n".join(lines))


async def _market_loop():
    """One engine loop for everyone: refresh both indices, run the paper autopilot, cache for clients."""
    while True:
        replay.hold(True)
        for key in INSTRUMENTS:
            try:
                await _analyze_and_trade(key)
            except Exception as exc:  # noqa: BLE001
                log.warning("analysis failed for %s: %s", key, exc)
                if key == "NIFTY":
                    _check_health(None, str(exc))
        replay.hold(False)
        _maybe_weekly_report()
        _maybe_daily_summary()
        if replay.active():
            if replay.finished():  # summary already sent above; hand control back to the live market
                replay.stop()
                LATEST.clear(); LATEST_AT.clear()
            await _sleep(replay.step_seconds())
            continue
        now = datetime.now(IST)
        open_now = timeline.session(now, "NIFTY")["is_open"]
        near_open = now.hour == 9 and now.minute < 15 or now.hour == 8 and now.minute >= 50
        await _sleep(15 if open_now else 30 if near_open else 300)


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = service.load_settings()
    on = " + ".join(s.get("autopilot_strategies", []))
    where = " + ".join(s.get("autopilot_instruments", ["NIFTY"]))
    notify.send(f"C0MR4DE Terminal (re)started. Paper autopilot armed on {where}: {on}.")
    tasks = [asyncio.create_task(_news_loop()), asyncio.create_task(_market_loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="C0MR4DE Terminal", version="2.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def _sym(symbol: str) -> str:
    s = symbol.upper().replace("^NSEI", "NIFTY").replace("^BSESN", "SENSEX")
    if s not in INSTRUMENTS:
        raise HTTPException(400, f"symbol must be one of {list(INSTRUMENTS)}")
    return s


@app.get("/api/health")
def health():
    return {"status": "ok", "broker_configured": angel.configured(), "broker_connected": angel.api is not None,
            "news_sources": radar.status, "instruments": list(INSTRUMENTS)}


@app.get("/api/signal")
async def signal(symbol: str = "NIFTY"):
    key = _sym(symbol)
    if key in LATEST and time.time() - LATEST_AT[key] < 20:
        return LATEST[key]
    try:
        return await _analyze_and_trade(key)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/notify/test")
def notify_test():
    if not notify.configured():
        raise HTTPException(400, "No TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or NTFY_TOPIC in backend/.env")
    notify.send("Test alert from C0MR4DE Terminal - notifications work.")
    return {"ok": True}


@app.get("/api/paper")
def paper_summary():
    if replay.active():
        return {**replay_paper.summary(day=replay.now().date()), "replay": True}
    return paper.summary()


@app.get("/api/experiments")
def experiments_list():
    """Every deliberate change to strategy or process, with its evidence and status."""
    from .engine import experiments

    return {"experiments": experiments.all()}


@app.get("/api/capital-test")
def capital_test_report():
    """Four isolated paper books (Rs 10k / 30k / 50k / 10k puts only) on one signal feed."""
    return capital_test.report()


@app.post("/api/capital-test/restart")
def capital_test_restart():
    """Archive all four books and start a fresh week. Files are moved, never deleted."""
    return capital_test.restart()


@app.post("/api/paper/reset")
def paper_reset():
    book().reset()
    return book().summary()


class ReplayReq(BaseModel):
    day: str
    speed: float = 60


@app.get("/api/replay")
def replay_status():
    return replay.status()


@app.get("/api/replay/days")
async def replay_days():
    df, _ = await asyncio.to_thread(get_candles, "NIFTY", "5m")
    today = datetime.now(IST).date()
    days = sorted({d for d in df.index.date if d < today or not timeline.session(key="NIFTY")["is_open"]}, reverse=True)
    return {"days": [d.isoformat() for d in days[:40]]}


@app.post("/api/replay/start")
async def replay_start(req: ReplayReq):
    d = _date.fromisoformat(req.day)
    if not timeline.is_trading_day(d):
        raise HTTPException(400, f"{req.day} was not a trading day")
    LATEST.clear(); LATEST_AT.clear()
    st = replay.start(d, req.speed)
    _wake()
    return st


@app.post("/api/replay/stop")
async def replay_stop():
    LATEST.clear(); LATEST_AT.clear()
    st = replay.stop()
    _wake()
    return st


@app.post("/api/replay/pause")
def replay_pause(on: bool = True):
    return replay.pause(on)


class OrderReq(BaseModel):
    symbol: str
    expiry: str
    strike: float
    option_type: str
    lots: int
    side: str = "BUY"
    limit_price: float
    confirm: bool = False


@app.post("/api/orders/place")
def place_order(req: OrderReq):
    if not req.confirm:
        raise HTTPException(400, "Order not confirmed.")
    if req.option_type not in ("CE", "PE") or req.side not in ("BUY", "SELL"):
        raise HTTPException(400, "Bad order parameters.")
    return place_live_order(_sym(req.symbol), req.expiry, req.strike, req.option_type, req.lots, req.side,
                            req.limit_price, service.load_settings())


@app.get("/api/candles")
async def candles(symbol: str = "NIFTY", interval: str = Query("5m", pattern="^(1m|5m|15m|1d)$")):
    try:
        df, source = await asyncio.to_thread(get_candles, _sym(symbol), interval)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"symbol": _sym(symbol), "interval": interval, "source": source,
            "candles": service.chart_payload(df, 400 if interval != "1d" else 250)}


@app.get("/api/news")
async def news(q: str | None = None, kind: str | None = None, relevant: bool = False, limit: int = 80):
    items = await asyncio.to_thread(radar.feed, q, kind, relevant, limit)
    return {"items": items, "sources": radar.status, "sentiment": radar.sentiment(),
            "x_enabled": radar.status.get("X / Twitter") == "ok"}


@app.get("/api/global")
async def global_cues():
    cues, vix = await asyncio.gather(asyncio.to_thread(macro.global_cues), asyncio.to_thread(macro.india_vix))
    return {**cues, "vix": vix}


@app.get("/api/session")
def session(symbol: str = "NIFTY"):
    return timeline.session(key=_sym(symbol))


_bt_cache: dict[str, tuple[float, dict]] = {}


@app.get("/api/backtest")
async def run_backtest(symbol: str = "NIFTY", refresh: bool = False):
    key = _sym(symbol)
    hit = _bt_cache.get(key)
    if hit and not refresh and time.time() - hit[0] < 3600:
        return hit[1]
    settings = service.load_settings()
    res = await asyncio.to_thread(backtest.run, key, int(settings["max_trades_per_day"]))
    _bt_cache[key] = (time.time(), res)
    return res


class Settings(BaseModel):
    capital: float | None = None
    risk_per_trade_pct: float | None = None
    max_trades_per_day: int | None = None
    max_daily_loss_pct: float | None = None
    autopilot_instruments: list[str] | None = None
    autopilot_strategies: list[str] | None = None


@app.get("/api/settings")
def get_settings():
    return service.load_settings()


@app.post("/api/settings")
def set_settings(body: Settings):
    return service.save_settings(body.model_dump())


@app.get("/api/signals/log")
def signals_log(limit: int = 100):
    return {"items": service.signal_log(limit)}


@app.get("/api/broker/status")
def broker_status():
    return {"configured": angel.configured(), "connected": angel.api is not None, "live_trading": live_enabled(),
            "note": "Read-only market data. This app never places orders." if angel.configured()
            else "Add ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD (MPIN) and ANGEL_TOTP_KEY to backend/.env "
                 "for real-time candles and live option prices. Without it, data comes from Yahoo (delayed)."}


@app.websocket("/ws")
async def ws(socket: WebSocket, symbol: str = "NIFTY"):
    await socket.accept()
    key = _sym(symbol)
    sent = 0.0
    try:
        while True:
            if LATEST_AT.get(key, 0) > sent:
                sent = LATEST_AT[key]
                await socket.send_json({"type": "signal", "data": LATEST[key]})
            await asyncio.sleep(2)
    except (WebSocketDisconnect, RuntimeError):
        return


# Serve the built dashboard (npm run build -> dist/) from the same port, so one SSH tunnel shows everything.
_DIST = Path(__file__).resolve().parents[1] / "dist"
if _DIST.exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(_DIST / "index.html")
