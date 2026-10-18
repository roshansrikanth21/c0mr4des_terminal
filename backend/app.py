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


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_news_loop())
    yield
    task.cancel()


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
    try:
        return await asyncio.to_thread(service.analyze, _sym(symbol))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


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
    return {"configured": angel.configured(), "connected": angel.api is not None,
            "note": "Read-only market data. This app never places orders." if angel.configured()
            else "Add ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD (MPIN) and ANGEL_TOTP_KEY to backend/.env "
                 "for real-time candles and live option prices. Without it, data comes from Yahoo (delayed)."}


@app.websocket("/ws")
async def ws(socket: WebSocket, symbol: str = "NIFTY"):
    await socket.accept()
    key = _sym(symbol)
    try:
        while True:
            try:
                data = await asyncio.to_thread(service.analyze, key)
                await socket.send_json({"type": "signal", "data": data})
            except RuntimeError as exc:
                await socket.send_json({"type": "error", "message": str(exc)})
            sess = timeline.session(key=key)
            await asyncio.sleep(15 if sess["is_open"] else 120)
    except (WebSocketDisconnect, RuntimeError):
        return
