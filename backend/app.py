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
from .engine.trader import live_enabled, paper, place_live_order  # noqa: E402
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


async def _analyze_and_trade(key: str) -> dict:
    a = await asyncio.to_thread(service.analyze, key)
    a["paper"] = await asyncio.to_thread(paper.on_analysis, a, service.load_settings())
    LATEST[key], LATEST_AT[key] = a, time.time()
    for ev in a["paper"]["events"]:
        log.info("PAPER %s %s", key, ev)
    return a


async def _market_loop():
    """One engine loop for everyone: refresh both indices, run the paper autopilot, cache for clients."""
    while True:
        for key in INSTRUMENTS:
            try:
                await _analyze_and_trade(key)
            except Exception as exc:  # noqa: BLE001
                log.warning("analysis failed for %s: %s", key, exc)
        open_now = timeline.session(key="NIFTY")["is_open"]
        await asyncio.sleep(15 if open_now else 300)


@asynccontextmanager
async def lifespan(_: FastAPI):
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


@app.get("/api/paper")
def paper_summary():
    return paper.summary()


@app.post("/api/paper/reset")
def paper_reset():
    paper.reset()
    return paper.summary()


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
