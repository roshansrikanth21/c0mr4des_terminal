from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware  # [NEW] Compression
from dotenv import load_dotenv
import os
import json
import re
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from PIL import Image
import io
import asyncio # [NEW]
import logging
import importlib
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

try:
    from google import genai as google_genai  # Preferred SDK
except Exception:
    google_genai = None

try:
    import structlog
except Exception:
    structlog = None

from backend.services.request_coordinator import request_coordinator

# [NEW] Top-level imports for performance
import time

_core_dependency_error: Optional[Exception] = None
_core_dependency_error_message: Optional[str] = None


def _dependency_error_payload(component: str = "analytics stack") -> Dict[str, Any]:
    message = _core_dependency_error_message or "Core dependencies are unavailable."
    return {
        "status": "error",
        "message": f"{component} unavailable: {message}",
        "degraded_mode": True,
    }


class _NullMonitor:
    def log_request(self, *args, **kwargs):
        return None

    def get_stats(self):
        return {
            "total_requests": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_latency": 0,
            "uptime": "degraded",
        }

    def get_history(self):
        return []


class _UnavailableExecutionEngine:
    broker = None

    def switch_mode(self, *args, **kwargs):
        return _dependency_error_payload("execution engine")

    def get_status(self):
        return _dependency_error_payload("execution engine")

    def get_portfolio(self):
        return _dependency_error_payload("execution engine")

    def execute_order(self, *args, **kwargs):
        return _dependency_error_payload("execution engine")


class _UnavailableServiceManager:
    advanced_trading_system = None
    execution_engine = _UnavailableExecutionEngine()
    learning_manager = None
    market_timing = None
    bayesian_model = None

    def initialize_all_background(self):
        return None


try:
    from backend.market_data import get_market_regime, get_market_history, get_market_history_async, get_market_regime_async
    from backend.services.service_manager import service_manager
    from backend.services.market_data_service import get_sync_market_data, async_market_data_service
    from backend.utils.monitor import monitor
except Exception as exc:
    _core_dependency_error = exc
    _core_dependency_error_message = str(exc)
    service_manager = _UnavailableServiceManager()
    async_market_data_service = None
    monitor = _NullMonitor()

    def get_market_regime(*args, **kwargs):
        return _dependency_error_payload("market regime engine")

    def get_market_history(*args, **kwargs):
        return _dependency_error_payload("market history engine")

    async def get_market_regime_async(*args, **kwargs):
        return _dependency_error_payload("market regime engine")

    async def get_market_history_async(*args, **kwargs):
        return _dependency_error_payload("market history engine")

    def get_sync_market_data(*args, **kwargs):
        raise RuntimeError(_core_dependency_error_message or "Market data stack unavailable")

logger = logging.getLogger(__name__)

if structlog is not None:
    # --- Structured Logging Setup ---
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    # --------------------------------
else:
    logger.warning("structlog is not installed; falling back to standard logging.")


class _GenAIResponseAdapter:
    def __init__(self, text: str):
        self.text = text or ""


class _LegacyGenAIClientAdapter:
    """
    Compatibility adapter for deprecated google.generativeai package.
    Exposes minimal Client-like interface used by this app.
    """

    def __init__(self, legacy_module):
        self._legacy = legacy_module
        self.models = self._Models(legacy_module)

    class _Models:
        def __init__(self, legacy_module):
            self._legacy = legacy_module

        def generate_content(self, model: str, contents, config: Optional[Dict[str, Any]] = None):
            generation_config = config or {}
            model_obj = self._legacy.GenerativeModel(model)
            response = model_obj.generate_content(
                contents,
                generation_config=generation_config
            )
            text = getattr(response, "text", "") or ""
            return _GenAIResponseAdapter(text=text)


def _create_gemini_client(api_key: Optional[str]):
    if not api_key:
        return None

    if google_genai is not None:
        try:
            return google_genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning("google.genai client init failed, attempting legacy fallback: %s", e)

    try:
        legacy_genai = importlib.import_module("google.generativeai")
        legacy_genai.configure(api_key=api_key)
        return _LegacyGenAIClientAdapter(legacy_genai)
    except Exception as e:
        logger.error("Could not initialize Gemini SDK: %s", e)
        return None


# Shared cache/in-flight state for expensive dashboard analysis calls.
_dashboard_analysis_cache: Dict[str, Dict[str, Any]] = {}
_dashboard_analysis_inflight: Dict[str, asyncio.Task] = {}
_dashboard_analysis_ttl_sec = int(os.getenv("DASHBOARD_ANALYSIS_CACHE_SEC", "25"))
_chart_analyzer_status: Dict[str, Any] = {
    "total_requests": 0,
    "success_count": 0,
    "failure_count": 0,
    "last_request_at": None,
    "last_duration_ms": 0.0,
    "last_model": None,
    "last_files_count": 0,
    "last_error": None,
    "last_attempted_models": [],
}
_intel_bundle_cache: Dict[str, Dict[str, Any]] = {}
_intel_bundle_inflight: Dict[str, asyncio.Task] = {}
_intel_bundle_ttl_sec = int(os.getenv("INTEL_BUNDLE_CACHE_SEC", "20"))
_system_prewarm_status: Dict[str, Any] = {
    "last_started_at": None,
    "last_completed_at": None,
    "tickers": [],
    "status": "idle",
    "last_error": None,
}


async def _get_dashboard_analysis_cached(ticker: str) -> Dict[str, Any]:
    """
    Deduplicate and cache heavy dashboard analysis per ticker.
    Prevents parallel /summary and /market_analysis calls from recomputing the same payload.
    """
    now = time.time()
    cache_entry = _dashboard_analysis_cache.get(ticker)
    if cache_entry and (now - cache_entry.get("ts", 0)) < _dashboard_analysis_ttl_sec:
        return cache_entry["data"]

    async def _compute():
        system = service_manager.advanced_trading_system
        if system is None:
            return _dependency_error_payload("advanced trading system")
        if ticker != system.ticker:
            system.ticker = ticker
        return await system.get_complete_analysis()
    data = await request_coordinator.run(
        key=f"dashboard:{ticker}",
        workload="dashboard",
        work_fn=_compute,
        ttl_sec=float(_dashboard_analysis_ttl_sec),
        cache_success_predicate=lambda result: isinstance(result, dict) and result.get("status") != "error",
    )
    _dashboard_analysis_cache[ticker] = {"ts": time.time(), "data": data}
    return data


async def _get_intel_bundle_cached(cache_key: str, compute_fn) -> Dict[str, Any]:
    """Cache and de-duplicate /api/intel/bundle calls."""
    now = time.time()
    cache_entry = _intel_bundle_cache.get(cache_key)
    if cache_entry and (now - cache_entry.get("ts", 0)) < _intel_bundle_ttl_sec:
        return cache_entry["data"]
    data = await request_coordinator.run(
        key=f"intel:{cache_key}",
        workload="intel",
        work_fn=compute_fn,
        ttl_sec=float(_intel_bundle_ttl_sec),
        cache_success_predicate=lambda result: isinstance(result, dict) and result.get("status") == "success",
    )
    if isinstance(data, dict) and data.get("status") == "success":
        _intel_bundle_cache[cache_key] = {"ts": time.time(), "data": data}
    return data


async def _compute_intel_bundle_payload(ticker: str, period: str = "30d", interval: str = "15m") -> Dict[str, Any]:
    if _core_dependency_error is not None:
        return _dependency_error_payload("intel bundle")
    from backend.volume_profile import VolumeProfile
    from backend.ict_smart_money import ICTSmartMoney
    from backend.market_timing import get_market_timing
    from backend.institutional_order_flow import InstitutionalOrderFlowAnalyzer
    from backend.services.market_data_service import async_market_data_service

    if async_market_data_service:
        df = await async_market_data_service.get_market_data(ticker, period, interval)
    else:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, period, interval))

    if df.empty:
        return {"status": "error", "message": "No market data available for bundle"}

    if len(df) > 600:
        df = df.iloc[-600:].copy()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    loop = asyncio.get_event_loop()
    if async_market_data_service:
        ob_task = async_market_data_service.get_order_book(ticker)
    else:
        ob_task = asyncio.sleep(
            0,
            result={"bid": [], "ask": [], "ltp": 0, "volume": 0, "timestamp": datetime.now().isoformat()},
        )

    def _run_sync_analyses():
        try:
            vp = VolumeProfile(df)
            vp_data = vp.analyze()
        except Exception as e:
            print(f"Bundle VOL Component Failed: {e}")
            vp_data = None

        ict_flattened = []
        try:
            ict = ICTSmartMoney(df)
            ict_raw = ict.analyze()
            for fvg in ict_raw.get("fvg", []):
                ict_flattened.append(
                    {
                        "type": "FVG_BULL" if fvg["type"] == "bullish" else "FVG_BEAR",
                        "top": fvg["top"],
                        "bottom": fvg["bottom"],
                        "start_time": fvg["start_time"],
                        "end_time": fvg["end_time"],
                    }
                )
            for ifvg in ict_raw.get("ifvg", []):
                ict_flattened.append(
                    {
                        "type": str(ifvg.get("type", "IFVG")).upper(),
                        "top": ifvg.get("top"),
                        "bottom": ifvg.get("bottom"),
                        "end_time": ifvg.get("end_time"),
                        "flipped_at": ifvg.get("flipped_at"),
                        "source_type": ifvg.get("source_type"),
                    }
                )
            for ob in ict_raw.get("ob", []):
                ict_flattened.append(
                    {
                        "type": ob["type"].upper(),
                        "top": ob["top"],
                        "bottom": ob["bottom"],
                        "time": ob["time"],
                    }
                )
            for snd in ict_raw.get("snd", []):
                ict_flattened.append(
                    {
                        "type": snd["type"].upper() + "_ZONE",
                        "top": snd["top"],
                        "bottom": snd["bottom"],
                        "time": snd["time"],
                        "description": snd["description"],
                    }
                )
            for sweep in ict_raw.get("sweeps", []):
                ict_flattened.append(
                    {
                        "type": "LIQUIDITY_SWEEP",
                        "direction": "BULLISH" if "Bullish" in sweep["description"] else "BEARISH",
                        "level": sweep["level"],
                        "time": sweep["time"],
                    }
                )
        except Exception as e:
            print(f"Bundle ICT Component Failed: {e}")

        timing_data = None
        try:
            timing = get_market_timing(ticker)
            timing_data = {
                "session": timing.get_current_session(),
                "signals": timing.get_timing_signals(),
            }
        except Exception as e:
            print(f"Bundle TIMING Component Failed: {e}")

        return vp_data, ict_flattened, timing_data

    order_book_results, sync_results = await asyncio.gather(
        ob_task,
        loop.run_in_executor(None, _run_sync_analyses),
    )
    vp_data, ict_data, timing_data = sync_results

    flow_data = None
    try:
        analyzer = InstitutionalOrderFlowAnalyzer(ticker)
        flow_data = analyzer.analyze_comprehensive_flow(order_book_results, df)
    except Exception as flow_err:
        print(f"Bundle Order Flow Component Failed: {flow_err}")

    return {
        "status": "success",
        "data": {
            "volume": vp_data,
            "ict": ict_data,
            "timing": timing_data,
            "order_flow": flow_data,
        },
    }


async def _prewarm_ticker_context(ticker: str, period: str = "30d", interval: str = "15m") -> None:
    if _core_dependency_error is not None:
        _system_prewarm_status["last_error"] = _core_dependency_error_message
        return
    try:
        if async_market_data_service:
            await asyncio.gather(
                async_market_data_service.get_market_data(ticker, period, interval),
                async_market_data_service.get_market_data(ticker, "60d", "15m"),
                async_market_data_service.get_market_data(ticker, "1y", "1d"),
                return_exceptions=True,
            )
        await _get_intel_bundle_cached(
            cache_key=f"{ticker}|{period}|{interval}",
            compute_fn=lambda: _compute_intel_bundle_payload(ticker, period, interval),
        )
        try:
            from backend.services.news_ml_service import news_ml_service

            await news_ml_service.get_global_news_impact(benchmark_ticker=ticker, interval=interval)
        except Exception:
            pass
    except Exception as exc:
        _system_prewarm_status["last_error"] = str(exc)


async def _prewarm_system_context(tickers: List[str]) -> None:
    _system_prewarm_status["last_started_at"] = datetime.now().isoformat()
    _system_prewarm_status["tickers"] = list(tickers)
    _system_prewarm_status["status"] = "running"
    _system_prewarm_status["last_error"] = None
    try:
        await asyncio.gather(*[_prewarm_ticker_context(ticker) for ticker in tickers], return_exceptions=True)
    finally:
        _system_prewarm_status["last_completed_at"] = datetime.now().isoformat()
        _system_prewarm_status["status"] = "idle"

# Load environment variables from backend/.env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini API
client = _create_gemini_client(os.getenv("GEMINI_API_KEY"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - Pre-warm services in background"""
    print("[START] AI Market Analyser: Starting System...")
    if _core_dependency_error is None:
        service_manager.initialize_all_background()
    else:
        logger.warning("Starting in degraded mode: %s", _core_dependency_error_message)
    
    # Warm up key services safely without blocking startup.
    _ = service_manager.advanced_trading_system
    exec_engine = service_manager.execution_engine

    # Start WebSocket broadcaster using execution engine broker quote function.
    try:
        quote_func = getattr(getattr(exec_engine, "broker", None), "get_quote", None)
        if not callable(quote_func):
            quote_func = lambda _symbol: 0.0
        await ws_manager.start_price_broadcaster(quote_func)
    except Exception as e:
        logger.warning("WebSocket broadcaster startup skipped: %s", e)

    if _core_dependency_error is None:
        prewarm_tickers = [
            t.strip()
            for t in os.getenv("SYSTEM_PREWARM_TICKERS", "^NSEI,^NSEBANK,SPY,BTC-USD").split(",")
            if t.strip()
        ]
        if prewarm_tickers:
            asyncio.create_task(_prewarm_system_context(prewarm_tickers))
    
    yield
    print("Starting C0MR4DE TERMINAL Assistant...")

from backend.database import engine, Base
from backend import models, auth

app = FastAPI(lifespan=lifespan)

# Initialize database schemas
Base.metadata.create_all(bind=engine)

# [NEW] Add GZip Middleware (Minimum size 1000 bytes)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include Auth Router
app.include_router(auth.router)

from backend.services.websocket_manager import manager as ws_manager

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # We just listen to keep connection open
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# [NEW] Request Monitoring Middleware
@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    
    # Only log /api routes
    if request.url.path.startswith("/api"):
        monitor.log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=process_time
        )
    return response

@app.get("/api/system/status")
async def get_system_status():
    """
    Returns the health status of all core backend components.
    """
    status = {
        "api": "ONLINE",
        "monitor": "ACTIVE" if monitor else "ERROR",
        "gemini": "CONNECTED" if os.getenv("GEMINI_API_KEY") else "MISSING_KEY",
        "market_data": "DEGRADED" if _core_dependency_error is not None else "SYNC_ACTIVE",
        "dependency_error": _core_dependency_error_message,
        "timestamp": datetime.now().isoformat()
    }
    return {"status": "success", "data": status}


@app.get("/api/system/deep_status")
async def get_deep_system_status():
    """
    Extended diagnostic status for temporary observability during stabilization.
    """
    news_status = {"status": "error", "message": "news service unavailable"}
    try:
        from backend.services.news_ml_service import news_ml_service

        news_status = news_ml_service.get_runtime_status()
    except Exception as exc:
        news_status = {"status": "error", "message": str(exc)}

    providers = []
    provider_cache_entries = 0
    provider_inflight = 0
    if async_market_data_service:
        providers = async_market_data_service.get_provider_status()
        provider_cache_entries = len(getattr(async_market_data_service, "cache", {}))
        provider_inflight = len(getattr(async_market_data_service, "_inflight_requests", {}))

    fusion_status = {}
    try:
        from backend.services.decision_fusion_service import fusion_service

        fusion_status = fusion_service.get_runtime_status()
    except Exception as exc:
        fusion_status = {"status": "error", "message": str(exc)}

    routing_status = {}
    try:
        from backend.services.routing_service import routing_service

        routing_status = routing_service.get_routing_snapshot(ticker="^NSEI")
    except Exception as exc:
        routing_status = {"status": "error", "message": str(exc)}

    ops_status = {}
    try:
        from backend.services.ops_control_service import ops_control_service

        ops_status = ops_control_service.get_config()
    except Exception as exc:
        ops_status = {"status": "error", "message": str(exc)}

    execution_models_status = {}
    try:
        from backend.services.execution_quality_service import execution_quality_service

        execution_models_status = execution_quality_service.get_models()
    except Exception as exc:
        execution_models_status = {"status": "error", "message": str(exc)}

    memory_status = {}
    try:
        from backend.services.memory_service import memory_service

        memory_status = memory_service.get_runtime_status()
    except Exception as exc:
        memory_status = {"status": "error", "message": str(exc)}

    coordinator_status = request_coordinator.get_status()

    return {
        "status": "success",
        "data": {
            "system": {
                "api": "ONLINE",
                "monitor": "ACTIVE" if monitor else "ERROR",
                "gemini": "CONNECTED" if os.getenv("GEMINI_API_KEY") else "MISSING_KEY",
                "market_data": "DEGRADED" if _core_dependency_error is not None else "SYNC_ACTIVE",
                "dependency_error": _core_dependency_error_message,
                "timestamp": datetime.now().isoformat(),
            },
            "monitor": {
                "stats": monitor.get_stats(),
                "recent_requests": monitor.get_history()[:20],
            },
            "market_providers": {
                "providers": providers,
                "cache_entries": provider_cache_entries,
                "inflight_requests": provider_inflight,
            },
            "news_engine": news_status,
            "chart_analyzer": dict(_chart_analyzer_status),
            "fusion_engine": fusion_status,
            "routing": routing_status,
            "ops": ops_status,
            "execution_models": execution_models_status,
            "memory_engine": memory_status,
            "request_coordinator": coordinator_status,
            "prewarm": dict(_system_prewarm_status),
        },
    }


@app.post("/api/system/prewarm")
async def trigger_system_prewarm(
    ticker: str = "^NSEI",
    period: str = "30d",
    interval: str = "15m",
):
    asyncio.create_task(_prewarm_ticker_context(ticker=ticker, period=period, interval=interval))
    return {
        "status": "success",
        "message": "Prewarm started",
        "ticker": ticker,
        "period": period,
        "interval": interval,
    }

@app.get("/")
def read_root():
    # API Key configured in .env file
    return {"status": "Edge-Ops Backend Running"}

@app.get("/api/regime")
async def read_regime(ticker: str = "^NSEI"):
    """
    Fetch market regime for a given ticker.
    Default: ^NSEI (Nifty 50)
    """
    return await get_market_regime_async(ticker)

@app.get("/api/history")
async def read_history(ticker: str = "^NSEI", period: str = "1y", interval: str = "1d"):
    """
    Fetch historical price data with indicators and signals.
    """
    return await get_market_history_async(ticker, period, interval)

@app.get("/api/quant_analysis")
async def get_quant_data(ticker: str = "^NSEI", period: str = "1y"):
    """
    Fetch Advanced Quant Analysis: Regime Detection, A-Vol, State.
    """
    # Note: quant_engine might still be sync, so we run it in executor if needed
    # For now, let's keep it sync wrapped or just allow it to block slightly if it's fast
    # Ideally: await run_in_executor
    from backend.quant_engine import get_quant_analysis
    try:
        # data = get_quant_analysis(ticker, period=period) 
        # Using executor to prevent blocking event loop
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: get_quant_analysis(ticker, period=period))
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

class ChatRequest(BaseModel):
    context: str
    question: str

class HistoricalBackfillRequest(BaseModel):
    ticker: str = "^NSEI"
    period: str = "2y"
    interval: str = "1d"
    force_refresh: bool = False

class HistoricalBacktestRequest(BaseModel):
    ticker: str = "^NSEI"
    interval: str = "15m"
    start_date: str
    end_date: str
    initial_capital: float = 100000.0

class PriceModelTrainRequest(BaseModel):
    ticker: str = "^NSEI"
    interval: str = "1d"
    period: str = "2y"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    auto_backfill: bool = True

class PriceModelPredictRequest(BaseModel):
    ticker: str = "^NSEI"
    interval: str = "1d"
    horizon: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class PatternTrainingRequest(BaseModel):
    ticker: str = "^NSEI"
    interval: str = "15m"
    period: str = "1y"
    min_samples: int = 12
    min_win_rate: float = 0.80
    horizon_bars: int = 12
    stop_atr: float = 1.0
    target_atr: float = 1.5

@app.post("/api/backtest")
def run_backtest(
    ticker: str = "^NSEI",
    interval: str = "15m",
    period: str = "60d",
    slippage_bps: float = 3.0,
    transaction_cost_bps: float = 2.0,
    allow_synthetic: bool = False,
):
    """
    Run backtest simulation.
    """
    from backend.backtest import Backtester
    try:
        tester = Backtester(
            ticker=ticker,
            interval=interval,
            period=period,
            slippage_bps=slippage_bps,
            transaction_cost_bps=transaction_cost_bps,
            allow_synthetic=allow_synthetic,
        )
        tester.fetch_data()
        tester.run()
        return {"status": "success", "backtest": tester.get_results()}
    except Exception as e:
        print(f"Backtest Error: {e}")
        return {"status": "error", "message": str(e), "trades": []}

@app.post("/api/data/backfill")
def backfill_historical_data(payload: HistoricalBackfillRequest):
    """
    Backfill and persist historical OHLCV data for deterministic backtesting/ML.
    """
    from backend.services.historical_data_service import historical_data_service
    try:
        return historical_data_service.backfill(
            ticker=payload.ticker,
            period=payload.period,
            interval=payload.interval,
            force_refresh=payload.force_refresh
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/data/quality")
def get_historical_data_quality(
    ticker: str = "^NSEI",
    interval: str = "1d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Inspect persisted historical data quality for a ticker/interval.
    """
    from backend.services.historical_data_service import historical_data_service
    try:
        df = historical_data_service.load_range(
            ticker=ticker,
            interval=interval,
            start_date=start_date,
            end_date=end_date
        )
        return {
            "status": "success",
            "ticker": ticker,
            "interval": interval,
            "quality": historical_data_service.quality_report(df, interval)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/backtest/historical")
def run_historical_backtest(payload: HistoricalBacktestRequest):
    """
    Run backtest on persisted historical market data for a fixed date range.
    """
    from backend.backtest import Backtester
    from backend.services.historical_data_service import historical_data_service

    try:
        df = historical_data_service.load_range(
            ticker=payload.ticker,
            interval=payload.interval,
            start_date=payload.start_date,
            end_date=payload.end_date
        )
        if df.empty:
            return {
                "status": "error",
                "message": (
                    f"No stored data for {payload.ticker} [{payload.interval}] in range "
                    f"{payload.start_date} to {payload.end_date}. "
                    "Run /api/data/backfill first."
                ),
            }

        tester = Backtester(
            ticker=payload.ticker,
            interval=payload.interval,
            period=f"{payload.start_date}:{payload.end_date}",
            initial_capital=float(payload.initial_capital),
        )
        tester.set_data(df, source_label="historical_store")
        tester.run()
        backtest = tester.get_results()

        return {
            "status": "success",
            "dataset": {
                "rows": int(len(df)),
                "start": df.index.min().isoformat(),
                "end": df.index.max().isoformat(),
            },
            "quality": historical_data_service.quality_report(df, payload.interval),
            "backtest": backtest,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/ml/price/train")
def train_price_forecast_model(payload: PriceModelTrainRequest):
    """
    Train and save a price forecasting model from persisted historical data.
    """
    from backend.services.historical_data_service import historical_data_service
    from backend.services.price_forecast_service import price_forecast_service

    try:
        df = historical_data_service.load_range(
            ticker=payload.ticker,
            interval=payload.interval,
            start_date=payload.start_date,
            end_date=payload.end_date
        )
        if df.empty and payload.auto_backfill:
            backfill_result = historical_data_service.backfill(
                ticker=payload.ticker,
                period=payload.period,
                interval=payload.interval,
                force_refresh=False
            )
            if backfill_result.get("status") != "success":
                return backfill_result
            df = historical_data_service.load_range(
                ticker=payload.ticker,
                interval=payload.interval,
                start_date=payload.start_date,
                end_date=payload.end_date
            )

        if df.empty:
            return {
                "status": "error",
                "message": f"No historical dataset available for {payload.ticker} [{payload.interval}]",
            }

        result = price_forecast_service.train_and_save(
            ticker=payload.ticker,
            interval=payload.interval,
            df=df
        )
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/ml/price/predict")
def predict_price(payload: PriceModelPredictRequest):
    """
    Predict next N close prices using the saved ML forecast model.
    """
    from backend.services.historical_data_service import historical_data_service
    from backend.services.price_forecast_service import price_forecast_service

    try:
        if payload.horizon < 1 or payload.horizon > 50:
            return {"status": "error", "message": "horizon must be between 1 and 50"}

        df = historical_data_service.load_range(
            ticker=payload.ticker,
            interval=payload.interval,
            start_date=payload.start_date,
            end_date=payload.end_date
        )
        if df.empty:
            return {
                "status": "error",
                "message": f"No historical dataset available for {payload.ticker} [{payload.interval}]",
            }

        result = price_forecast_service.predict_next(
            ticker=payload.ticker,
            interval=payload.interval,
            df=df,
            horizon=payload.horizon
        )
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/train")
def train_model(ticker: str = "^NSEI"):
    """
    Run the Strategy Optimizer to learn the best parameters from historical data.
    """
    from backend.optimizer import StrategyOptimizer
    try:
        opt = StrategyOptimizer(ticker=ticker)
        result = opt.optimize() # Now returns dict with best_params and logs
        return {"status": "success", "data": result}
    except Exception as e:
        # Return error but don't crash 
        return {"status": "error", "message": str(e)}


@app.post("/api/patterns/train")
def train_pattern_quality_model(payload: PatternTrainingRequest):
    """
    Train historical pattern quality model and persist only high-performing patterns.
    """
    try:
        from backend.services.pattern_learning_service import (
            PatternTrainingConfig,
            pattern_learning_service,
        )

        cfg = PatternTrainingConfig(
            ticker=payload.ticker,
            interval=payload.interval,
            period=payload.period,
            min_samples=max(int(payload.min_samples), 3),
            min_win_rate=min(max(float(payload.min_win_rate), 0.0), 1.0),
            horizon_bars=max(int(payload.horizon_bars), 2),
            stop_atr=max(float(payload.stop_atr), 0.1),
            target_atr=max(float(payload.target_atr), 0.1),
        )
        return pattern_learning_service.train(cfg)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/patterns/approved")
def get_approved_patterns(ticker: str = "^NSEI", interval: str = "15m"):
    """
    Return the latest approved patterns trained on historical outcomes.
    """
    try:
        from backend.services.pattern_learning_service import pattern_learning_service

        return pattern_learning_service.get_latest(ticker=ticker, interval=interval)
    except Exception as e:
        return {"status": "error", "message": str(e), "approved_patterns": [], "approved_pattern_ids": []}

@app.get("/api/ict_analysis")
async def get_ict_data(ticker: str = "^NSEI", period: str = "60d", interval: str = "15m"):
    """
    Fetch ICT (Inner Circle Trader) concepts: FVG, Order Blocks.
    """
    from backend.ict_smart_money import ICTSmartMoney
    
    try:
        # Fetch data through standardized service (Async)
        if async_market_data_service:
            df = await async_market_data_service.get_market_data(ticker, period, interval)
        else:
             import asyncio
             loop = asyncio.get_event_loop()
             df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, period, interval))

        if df.empty:
             return {"status": "error", "message": f"No data found for {ticker}"}
             
        # Run Heavy analysis in executor
        loop = asyncio.get_event_loop()
        def _analyze():
            ict = ICTSmartMoney(df)
            return ict.analyze()
            
        analysis = await loop.run_in_executor(None, _analyze)
        
        # Flatten for frontend
        results = []
        for fvg in analysis.get('fvg', []):
            f_type = "FVG_BULL" if fvg['type'] == "bullish" else "FVG_BEAR"
            results.append({
                "type": f_type,
                "top": fvg['top'],
                "bottom": fvg['bottom'],
                "start_time": fvg['start_time'],
                "end_time": fvg['end_time']
            })

        for ifvg in analysis.get('ifvg', []):
            results.append({
                "type": str(ifvg.get('type', 'IFVG')).upper(),
                "top": ifvg.get('top'),
                "bottom": ifvg.get('bottom'),
                "end_time": ifvg.get('end_time'),
                "flipped_at": ifvg.get('flipped_at'),
                "source_type": ifvg.get('source_type')
            })
            
        for ob in analysis.get('ob', []):
            results.append({
                "type": ob['type'].upper(),
                "top": ob['top'],
                "bottom": ob['bottom'],
                "time": ob['time']
            })

        for snd in analysis.get('snd', []):
            results.append({
                "type": snd['type'].upper() + "_ZONE",
                "top": snd['top'],
                "bottom": snd['bottom'],
                "time": snd['time'],
                "description": snd['description']
            })

        for sweep in analysis.get('sweeps', []):
            results.append({
                "type": "LIQUIDITY_SWEEP",
                "direction": "BULLISH" if "Bullish" in sweep['description'] else "BEARISH",
                "level": sweep['level'],
                "time": sweep['time'],
                "description": sweep['description']
            })
            
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/volume_profile")
async def get_volume_profile(ticker: str = "^NSEI", period: str = "60d", interval: str = "15m"):
    """
    Fetch Volume Profile: POC, VAH, VAL, HVN, LVN.
    """
    from backend.volume_profile import VolumeProfile
    
    try:
        if async_market_data_service:
            df = await async_market_data_service.get_market_data(ticker, period, interval)
        else:
             import asyncio
             loop = asyncio.get_event_loop()
             df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, period, interval))
        
        if df.empty: return {"status": "error", "message": "No data"}
        
        loop = asyncio.get_event_loop()
        vp = await loop.run_in_executor(None, lambda: VolumeProfile(df))
        return {"status": "success", "data": vp.analyze()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/news/impact")
async def get_news_impact_analysis(ticker: str = "^NSEI", interval: str = "15m"):
    """
    Returns latest global news scored by the XGBoost/LR ensemble model
    to indicate market 'Affect Rate'.
    """
    from backend.services.news_ml_service import news_ml_service
    try:
        data = await news_ml_service.get_global_news_impact(benchmark_ticker=ticker, interval=interval)
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"News ML Engine Failure: {str(e)}\n{error_details}")
        
        # Instead of generic 500, we return a structured error that the UI can show
        return {
            "status": "error",
            "message": f"Intelligence Engine Sync Failed: {str(e)}",
            "type": "ML_SERVICE_FAILURE",
            "suggestion": "Check Gemini API quota or network connectivity."
        }


@app.post("/api/news/event_study/train")
def train_news_event_study(payload: dict = Body(default={})):
    """
    Calibrate news impact scores against realized forward returns on a benchmark ticker.
    """
    try:
        from backend.services.news_event_study_service import NewsEventStudyConfig, news_event_study_service

        cfg = NewsEventStudyConfig(
            benchmark_ticker=payload.get("benchmark_ticker", "^NSEI"),
            interval=payload.get("interval", "15m"),
            horizon_bars=int(payload.get("horizon_bars", 12)),
            min_samples=int(payload.get("min_samples", 10)),
            period=payload.get("period", "60d"),
            auto_backfill=bool(payload.get("auto_backfill", True)),
        )
        return news_event_study_service.train(cfg)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/news/event_study/latest")
def get_news_event_study_latest(benchmark_ticker: str = "^NSEI", interval: str = "15m"):
    try:
        from backend.services.news_event_study_service import news_event_study_service

        return news_event_study_service.get_latest(benchmark_ticker=benchmark_ticker, interval=interval)
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/monitor/requests")
async def get_system_metrics():
    """
    Returns real-time backend request history and system stats.
    """
    return {
        "status": "success",
        "stats": monitor.get_stats(),
        "history": monitor.get_history()
    }

@app.get("/api/market_timing")
async def get_market_timing_signals(ticker: str = "^NSEI"):
    """
    Fetch Market Timing and Asian Range signals.
    """
    from backend.market_timing import get_market_timing
    
    try:
        # Run synchronous timing logic in executor
        loop = asyncio.get_event_loop()
        timing = await loop.run_in_executor(None, lambda: get_market_timing(ticker))
        
        signals = timing.get_timing_signals()
        
        # Asian Range specifically for Forex
        asian_range = None
        if hasattr(timing, 'calculate_asian_range'):
            # Fetch data through standardized service
            if async_market_data_service:
                df = await async_market_data_service.get_market_data(ticker, period='5d', interval='1h')
            else:
                 df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, period='5d', interval='1h'))
            
            if not df.empty:
                asian_range = timing.calculate_asian_range(df)
            
        return {
            "status": "success", 
            "session": timing.get_current_session(),
            "signals": signals,
            "asian_range": asian_range
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/alpha/discover")
async def get_alpha_discover(region: str = None):
    """
    Scans markets for high-probability setups.
    """
    from backend.market_scanner import AlphaScanner
    scanner = AlphaScanner()
    results = await scanner.discover_alpha(region_filter=region)
    return {"status": "success", "data": results}

@app.get("/api/order_flow")
async def get_order_flow_analysis(ticker: str = "^NSEI"):
    """
    Fetch Institutional Order Flow: CVD, Sweeps, Imbalance.
    """
    from backend.institutional_order_flow import InstitutionalOrderFlowAnalyzer
    from backend.services.market_data_service import async_market_data_service
    try:
        analyzer = InstitutionalOrderFlowAnalyzer(ticker)
        # Fetch real order book if broker is connected, otherwise fallback to synthetic
        order_book = await async_market_data_service.get_order_book(ticker)
        
        # Also need some price data for trend context
        from backend.services.market_data_service import get_sync_market_data
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, period="1d", interval="1m"))
        
        return {"status": "success", "data": analyzer.analyze_comprehensive_flow(order_book, df)}
    except Exception as e:
        return {"status": "error", "message": f"Order Flow error: {str(e)}"}

@app.get("/api/intel/bundle")
async def get_intel_bundle(ticker: str = "^NSEI", period: str = "30d", interval: str = "15m"):
    """
    [ULTRA-OPTIMIZED] Consolidates Volume, ICT, Flow, and Timing into 1 call.
    Reduces network roundtrips and reuses a single market dataframe.
    """
    cache_key = f"{ticker}|{period}|{interval}"
    try:
        return await _get_intel_bundle_cached(
            cache_key=cache_key,
            compute_fn=lambda: _compute_intel_bundle_payload(ticker, period, interval),
        )
    except Exception as e:
        print(f"Bundle Error: {str(e)}")
        return {"status": "error", "message": f"Intelligence Bundle Failure: {str(e)}"}
        return {"status": "error", "message": f"Intelligence Bundle Failure: {str(e)}"}

@app.get("/api/microstructure/vbp")
async def get_vbp_analysis(ticker: str = "^NSEI", period: str = "5d", interval: str = "15m"):
    """
    Fetch Intraday Volume By Price (VBP) and POC.
    """
    from backend.microstructure import analyze_intraday_vbp
    try:
        if async_market_data_service:
            df = await async_market_data_service.get_market_data(ticker, period, interval)
        else:
             import asyncio
             loop = asyncio.get_event_loop()
             df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, period, interval))
        
        if df.empty: return {"status": "error", "message": "No data"}
        
        loop = asyncio.get_event_loop()
        vbp = await loop.run_in_executor(None, lambda: analyze_intraday_vbp(df))
        return {"status": "success", "data": vbp}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/intraday")
async def get_intraday_data(ticker: str = "^NSEI", interval: str = "5m"):
    """
    Fetch live intraday data for options trading (5m, 15m intervals)
    Optimized for intraday with VWAP, faster indicators, and strike recommendations
    """
    import yfinance as yf
    import pandas as pd
    import numpy as np
    from backend.market_data import calculate_sma, calculate_rsi, calculate_atr
    from backend.intraday_utils import (
        is_market_open, calculate_vwap, calculate_option_strikes, 
        get_next_expiry, should_square_off, load_params
    )
    
    # Load learned parameters
    PARAMS = load_params()
    
    try:
        
        # Fetch data through standardized service (Async)
        if async_market_data_service:
            df = await async_market_data_service.get_market_data(ticker, "5d", interval)
        else:
             import asyncio
             loop = asyncio.get_event_loop()
             df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, "5d", interval))
        
        if df.empty:
            return {
                "data": [],
                "market_open": is_market_open(),
                "message": "Real-time data fetch failed. Using fallback simulation if possible."
            }
        
        # Indicators
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        
        # Fill missing data to avoid indicator crashes
        df = df.ffill().bfill()
        
        # DEBUG: Print latest index
        if not df.empty:
            print(f"DEBUG: Latest data point time: {df.index[-1]}")
            
            # Filter for TODAY only if market is open, otherwise show last available
            # But for now, let's just return the last 75 candles to show context
            # This fixes the 'empty chart' issue if '1d' returns nothing at 9:16 AM
            if len(df) > 75:
                 df = df.iloc[-75:]
                 close = df['Close']
                 high = df['High']
                 low = df['Low']
                 volume = df['Volume']
        
        # Intraday indicators (faster periods)
        sma_9 = calculate_sma(close, 9)
        sma_21 = calculate_sma(close, 21)
        rsi_9 = calculate_rsi(close, 9)
        atr = calculate_atr(high, low, close, 14)
        vwap = calculate_vwap(high, low, close, volume)
        vol_sma = volume.rolling(window=20).mean()
        
        history = []
        in_position = False
        position_type = None  # "LONG" or "SHORT"
        entry_price = 0
        stop_loss = None
        take_profit = None
        
        for i in range(len(df)):
            date_obj = df.index[i]
            date_str = date_obj.strftime('%H:%M')  # Just time for intraday
            
            price = float(close.iloc[i])
            s9 = float(sma_9.iloc[i]) if not np.isnan(sma_9.iloc[i]) else None
            s21 = float(sma_21.iloc[i]) if not np.isnan(sma_21.iloc[i]) else None
            r_val = float(rsi_9.iloc[i]) if not np.isnan(rsi_9.iloc[i]) else 50
            atr_val = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else 0
            vwap_val = float(vwap.iloc[i]) if not np.isnan(vwap.iloc[i]) else price
            vol_val = float(volume.iloc[i]) if not np.isnan(volume.iloc[i]) else 0
            v_sma = float(vol_sma.iloc[i]) if not np.isnan(vol_sma.iloc[i]) else 0
            
            signal = None
            confidence = 0.0
            reason = ""
            action = "WAIT"
            
            # Intraday Signal Logic
            if s9 and s21 and atr_val > 0:
                # LONG ENTRY CONDITIONS
                if not in_position:
                    entry_signal = False
                    
                    # Scenario A: VWAP Pullback
                    if price > s21 and (price < vwap_val * 1.002) and r_val < PARAMS.get('rsi_threshold', 50):
                        entry_signal = True
                        reason = "Pullback to Support"
                        confidence = 0.70
                    
                    # Scenario B: Breakout with volume (or SMA crossover if no volume)
                    prev_high = float(high.iloc[max(0, i-5):i].max()) if i > 5 else price
                    volume_spike = vol_val > (v_sma * 1.2) if v_sma > 0 else True # Default to True if no volume data
                    
                    if price > prev_high and volume_spike and price > s9:
                        entry_signal = True
                        reason = "Momentum Breakout"
                        confidence = 0.80
                    
                    # Scenario C: Oversold bounce
                    if r_val < 35 and price > s9:
                        entry_signal = True
                        reason = "Oversold Recovery"
                        confidence = 0.65
                    
                    if entry_signal and confidence > 0.6:
                        signal = "ENTRY"
                        in_position = True
                        position_type = "LONG"
                        entry_price = price
                        stop_loss = price - (1.5 * atr_val)  # Tighter stop for intraday
                        take_profit = price + (2 * (price - stop_loss))  # 2:1 R/R
                        action = "ENTER NOW"
                
                # SHORT ENTRY CONDITIONS
                if not in_position:
                    short_signal = False
                    
                    # Scenario D: VWAP Rejection (Downtrend)
                    # Price < SMA21 (Downtrend), Rallies to VWAP, RSI > 50
                    if price < s21 and price > vwap_val and r_val > 50:
                        short_signal = True
                        reason = "VWAP Rejection (Short)"
                        confidence = 0.75
                    
                    # Scenario E: Breakdown
                    prev_low = float(low.iloc[max(0, i-3):i].min()) if i > 3 else price
                    volume_spike = vol_val > (v_sma * 1.5) if v_sma > 0 else False
                    
                    if price < prev_low and volume_spike and price < vwap_val:
                        short_signal = True
                        reason = "Breakdown + Volume (Short)"
                        confidence = 0.85

                    # Scenario F: Overbought Rejection
                    if r_val > 70 and price < s9:
                        short_signal = True
                        reason = "Overbought Rejection (Short)"
                        confidence = 0.65
                    
                    if short_signal and confidence > 0.6:
                        signal = "ENTRY"
                        in_position = True
                        position_type = "SHORT"
                        entry_price = price
                        # For short: SL is above, Target is below
                        stop_loss = price + (1.5 * atr_val)
                        take_profit = price - (2 * (stop_loss - price))
                        action = "ENTER NOW"
                
                # EXIT CONDITIONS
                elif in_position:
                    stop_hit = False
                    take_profit_hit = False
                    trend_break = False
                    
                    if position_type == "LONG":
                        # Trail stop loss (Long)
                        current_stop = price - (1.5 * atr_val)
                        if stop_loss and current_stop > stop_loss:
                            stop_loss = current_stop
                            
                        stop_hit = price < stop_loss if stop_loss else False
                        take_profit_hit = price > take_profit if take_profit else False
                        trend_break = price < s9 and price < vwap_val
                        
                    elif position_type == "SHORT":
                        # Trail stop loss (Short) - Move SL DOWN
                        current_stop = price + (1.5 * atr_val)
                        if stop_loss and current_stop < stop_loss:
                            stop_loss = current_stop
                            
                        stop_hit = price > stop_loss if stop_loss else False
                        take_profit_hit = price < take_profit if take_profit else False
                        trend_break = price > s9 and price > vwap_val
                    
                    # Force exit if market closing soon
                    if should_square_off():
                        signal = "EXIT"
                        reason = "Square Off (Market Close)"
                        in_position = False
                        position_type = None
                        action = "EXIT NOW"
                    elif stop_hit:
                        signal = "EXIT"
                        reason = "Stop Loss Hit"
                        in_position = False
                        position_type = None
                        action = "EXIT NOW"
                    elif take_profit_hit:
                        signal = "EXIT"
                        reason = "Target Hit"
                        in_position = False
                        position_type = None
                        action = "EXIT NOW"
                    elif trend_break:
                        signal = "EXIT"
                        reason = "Trend Broken"
                        in_position = False
                        position_type = None
                        action = "EXIT NOW"
                    else:
                        action = "HOLD"
            
            history.append({
                "time": date_str,
                "price": price,
                "sma9": s9,
                "sma21": s21,
                "rsi": r_val,
                "vwap": vwap_val,
                "stop_loss": stop_loss if in_position or signal == "ENTRY" else None,
                "take_profit": take_profit if in_position or signal == "ENTRY" else None,
                "confidence": confidence if signal == "ENTRY" else None,
                "reason": reason if signal else None,
                "signal": signal,
                "action": action,
                "direction": position_type  # Track direction
            })
        
        # Get latest signal for options recommendation
        latest = history[-1] if history else None
        options_data = None
        
        if latest:
            try:
                # Determine index type
                index_type = "NIFTY" if "NSEI" in ticker else "BANKNIFTY"
                # Pass direction to get correct CE/PE
                direction = latest.get("direction", "LONG")
                strikes = calculate_option_strikes(latest["price"], "ENTRY", index_type, direction=direction)
                expiry = get_next_expiry()
                
                options_data = {
                    "type": strikes["type"],
                    "atm_strike": strikes["atm"],
                    "otm_strike": strikes["otm"],
                    "itm_strike": strikes["itm"],
                    "recommended_strike": strikes["atm"],  # Default to ATM
                    "expiry": expiry,
                    "entry_range": f"â‚¹{latest['price']:.2f}",
                    "stop_loss": f"â‚¹{latest['stop_loss']:.2f}" if latest['stop_loss'] else None,
                    "target": f"â‚¹{latest['take_profit']:.2f}" if latest['take_profit'] else None,
                    "direction": direction
                }
            except Exception as opt_err:
                print(f"âš ï¸ Error calculating options: {opt_err}")
                # Don't crash entire response if options logic fails
                pass
        
        return {
            "data": history,
            "market_open": is_market_open(),
            "latest_signal": latest,
            "options": options_data,
            "interval": interval
        }
    
    except Exception as e:
        import traceback
        error_msg = f"âŒ ERROR in get_intraday_data: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        
        # Write to log file for GSD watchdog
        with open("backend/system_error.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{pd.Timestamp.now()}] {error_msg}")
            
        return {
            "data": [],
            "market_open": is_market_open(),
            "error": str(e)
        }

# --- HELPER: Robust Generation with Fallback ---
def generate_content_with_fallback(prompt, image=None):
    """
    Attempts to generate content using a prioritized list of models.
    Falls back to the next model if 404 (Not Found) or 429 (Quota) errors occur.
    """
    # Priority list based on availability and capability
    MODELS = [
        'gemini-2.0-flash',       # Latest Stable
        'gemini-1.5-flash',       # Standard Flash
        'gemini-1.5-pro',         # High-reasoning fallback
    ]

    if client is None:
        class FallbackAIResponse:
            def __init__(self, text):
                self.text = text
        return FallbackAIResponse(
            "C0MR4DE Intelligence Engine (Offline Mode): Gemini API key is not configured. "
            "Please configure your GEMINI_API_KEY under Settings -> API Credentials to activate full LLM reasoning."
        )

    last_error = None

    for model_name in MODELS:
        try:
            print(f"DEBUG: Attempting generation with model: {model_name}")
            
            # Optimized Generation Config for Speed & Reliability
            gen_config = {
                "temperature": 0.1,  # Low temperature for precise technical analysis
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 1024,
                "response_mime_type": "application/json"
            }

            if image:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt, image],
                    config=gen_config
                )
            else:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=gen_config
                )
                
            return response
        except Exception as e:
            error_str = str(e)
            print(f"WARNING: Model {model_name} failed: {error_str}")
            last_error = e
            # Continue to next model
            continue

    # If all failed, raise the last error
    if last_error:
        raise last_error
    else:
        raise Exception("No models available.")

def resize_image_for_ai(image: Image.Image, max_size=(1024, 1024)) -> Image.Image:
    """
    Resizes and compresses image to optimize API payload size and processing speed.
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Calculate aspect ratio
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image


def _extract_balanced_json_object(text: str) -> str:
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        return text

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            elif ch in "\r\n":
                # Keep scanning; recovery happens in the sanitizer.
                pass
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]

    return text[start:]


def _sanitize_json_candidate(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = cleaned.replace("```json", "").replace("```JSON", "").replace("```", "")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")

    # Escape raw newlines inside JSON strings.
    out: List[str] = []
    in_string = False
    escape = False
    for ch in cleaned:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                continue
        else:
            if ch == '"':
                in_string = True
        out.append(ch)

    cleaned = "".join(out)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned.strip()


def _extract_string_field(text: str, key: str) -> Optional[str]:
    patterns = [
        rf'"{key}"\s*:\s*"([^"]*)"',
        rf'"{key}"\s*:\s*([A-Za-z0-9^._/\- %]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip(",")
            return value if value else None
    return None


def _extract_partial_string_field(text: str, key: str) -> Optional[str]:
    pattern = rf'"{key}"\s*:\s*"(.+?)(?=",\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:|\Z)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip().rstrip('}", ')
    value = value.replace("\\n", "\n")
    return value or None


def _parse_chart_analysis_fallback(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    compact = re.sub(r"\s+", " ", raw)

    confidence = 0.0
    confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', raw, re.IGNORECASE)
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
        except Exception:
            confidence = 0.0
    else:
        pct_match = re.search(r"([0-9]{1,3})\s*%", raw)
        if pct_match:
            confidence = max(0.0, min(1.0, float(pct_match.group(1)) / 100.0))

    ticker = _extract_string_field(raw, "ticker_detected")
    timeframe = _extract_string_field(raw, "timeframe")
    action_type = _extract_string_field(raw, "action_type")
    sentiment = _extract_string_field(raw, "sentiment")
    entry_zone = _extract_string_field(raw, "entry_zone")
    recommendation = _extract_string_field(raw, "recommendation")
    analysis_text = _extract_partial_string_field(raw, "analysis")
    recommendation = recommendation or _extract_partial_string_field(raw, "recommendation")

    if not action_type:
        action_match = re.search(r"\b(BUY CALL|BUY PUT|WAIT|HOLD|ENTER NOW|EXIT NOW)\b", raw, re.IGNORECASE)
        action_type = action_match.group(1).upper() if action_match else "WAIT"

    if not sentiment:
        sentiment_match = re.search(r"\b(Bullish|Bearish|Neutral)\b", raw, re.IGNORECASE)
        sentiment = sentiment_match.group(1).capitalize() if sentiment_match else "Neutral"

    target = None
    target_match = re.search(r'"target"\s*:\s*([0-9.]+)', raw, re.IGNORECASE)
    if target_match:
        try:
            target = float(target_match.group(1))
        except Exception:
            target = None

    stop_loss = None
    stop_match = re.search(r'"stop_loss"\s*:\s*([0-9.]+)', raw, re.IGNORECASE)
    if stop_match:
        try:
            stop_loss = float(stop_match.group(1))
        except Exception:
            stop_loss = None

    pattern_hits: List[str] = []
    known_patterns = [
        ("FVG", "FVG"),
        ("IFVG", "IFVG"),
        ("ORDER BLOCK", "Order Block"),
        ("LIQUIDITY SWEEP", "Liquidity Sweep"),
        ("BREAKOUT", "Breakout"),
        ("BOS", "Break Of Structure"),
        ("CHOCH", "Change Of Character"),
        ("SUPPORT", "Support"),
        ("RESISTANCE", "Resistance"),
        ("TRENDLINE", "Trendline"),
        ("FLAG", "Flag"),
        ("TRIANGLE", "Triangle"),
    ]
    upper_raw = raw.upper()
    for needle, label in known_patterns:
        if needle in upper_raw and label not in pattern_hits:
            pattern_hits.append(label)

    if not pattern_hits:
        pattern_hits = ["Recovered From Malformed Model Output"]

    if not recommendation:
        recommendation = action_type or "WAIT"

    return {
        "is_chart": True,
        "ticker_detected": ticker or "NULL",
        "timeframe": timeframe or "NULL",
        "current_price": 0.0,
        "patterns": pattern_hits,
        "sentiment": sentiment or "Neutral",
        "confidence": max(0.0, min(1.0, confidence)),
        "action_type": action_type or "WAIT",
        "entry_zone": entry_zone or "Watch Price Action",
        "target": target,
        "stop_loss": stop_loss,
        "recommendation": recommendation,
        "analysis": analysis_text or compact or "Model returned malformed output; fallback parser recovered partial analysis.",
        "status": "success",
        "recovered": True,
    }


def _parse_chart_analysis_response(response_text: str) -> Dict[str, Any]:
    text = (response_text or "").strip()
    candidate = _extract_balanced_json_object(text)
    candidate = _sanitize_json_candidate(candidate)

    try:
        result = json.loads(candidate)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    fallback = _parse_chart_analysis_fallback(candidate or text)
    if fallback.get("analysis"):
        fallback["analysis"] += "\n\nRecovered after malformed JSON from the model."
    return fallback


def _normalize_pattern_interval(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "60m": "1h",
        "1d": "1d",
        "1w": "1wk",
        "1wk": "1wk",
    }
    return mapping.get(raw, "15m")

@app.post("/api/analyze")
async def analyze_image_file(files: List[UploadFile] = File(...)):
    """
    Analyze SINGLE or MULTIPLE chart images for patterns using Gemini Vision API.
    Supports Cross-Timeframe Analysis and Sensex/BSE Charts.
    """
    started = time.time()
    _chart_analyzer_status["total_requests"] += 1
    _chart_analyzer_status["last_request_at"] = datetime.now().isoformat()
    _chart_analyzer_status["last_duration_ms"] = 0.0
    _chart_analyzer_status["last_files_count"] = len(files or [])
    _chart_analyzer_status["last_model"] = None
    _chart_analyzer_status["last_error"] = None
    _chart_analyzer_status["last_attempted_models"] = []

    def fail_payload(summary: str, recommendation: str = "Analysis Failed") -> Dict[str, Any]:
        _chart_analyzer_status["failure_count"] += 1
        _chart_analyzer_status["last_error"] = summary
        _chart_analyzer_status["last_duration_ms"] = round((time.time() - started) * 1000.0, 2)
        return {
            "status": "error",
            "error": summary,
            "patterns": ["System Error"],
            "sentiment": "Neutral",
            "confidence": 0.0,
            "action_type": "WAIT",
            "recommendation": recommendation,
            "analysis": summary,
        }

    try:
        import os
        import hashlib
        from PIL import Image
        import io
        model_timeout_sec = float(os.getenv("CHART_ANALYZER_MODEL_TIMEOUT_SEC", "22"))
        max_files = max(1, int(os.getenv("CHART_ANALYZER_MAX_FILES", "4")))
        files = list(files or [])[:max_files]
        _chart_analyzer_status["last_files_count"] = len(files)
        
        # Configure Gemini API
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return fail_payload(
                "Cannot analyze without GEMINI_API_KEY.",
                recommendation="API Key Missing"
            ) | {
                "patterns": ["API Key Missing"],
                "recommendation": "Please set GEMINI_API_KEY environment variable.",
            }
        
        # Reuse global client when available, otherwise initialize from runtime env.
        _client = client or _create_gemini_client(api_key)
        if _client is None:
            return fail_payload(
                "Gemini client could not be initialized. Install google-genai or configure API access.",
                recommendation="Gemini Client Error"
            )
        
        # Read and PRE-PROCESS ALL uploaded files
        image_parts = []
        file_signatures: List[str] = []
        for file in files:
            try:
                contents = await file.read()
                file_signatures.append(hashlib.sha1(contents).hexdigest()[:16])
                image = Image.open(io.BytesIO(contents))
                image.load()
                # Optimization: Resize and compress image for faster API transfer & processing
                image = resize_image_for_ai(image)
                image_parts.append(image)
            except Exception as image_err:
                print(f"[WARN] Skipping invalid uploaded file: {image_err}")

        if not image_parts:
            return fail_payload("No valid image files were provided.")
            
        print(f"Analyzing {len(image_parts)} optimized images...")
        
        # Craft detailed prompt for Multi-Image + Sensex Analysis
        prompt = """Analyze the provided financial chart(s) as an elite Hedge Fund Analyst.
        
        If multiple images are provided, treat them as CROSS-TIMEFRAME context (e.g., Higher Timeframe + Entry Timeframe).
        Synthesize a single, unified trade plan.

        YOUR TASKS:
        1. **OCR & Context**: 
           - EXTRACT Ticker (e.g., "NIFTY", "BANKNIFTY", "RELIANCE").
           - **CRITICAL**: If you see "SENSEX", "BSE", or "S&P BSE SENSEX", identify the ticker as "^BSESN".
           - Identify Timeframes (e.g., 5m, 1H, 1D).
        
        2. **Technical Analysis**: 
           - Identify patterns (Head & Shoulders, Flags, ICT FVG, Order Blocks).
           - Key Support/Resistance levels.
        
        3. **Action Plan (The "Trade Intelligence"):**
           - Decide: **BUY CALL** (Long), **BUY PUT** (Short), or **WAIT**.
           - Define specific **Entry Zone**.
           - Define **Target** (Take Profit).
           - Define **Stop Loss**.
        
        OUTPUT RULES:
        - Return JSON only. No markdown. No code fences.
        - Every string value must be a single line.
        - Do not use double quotes inside string values.
        - Keep recommendation and analysis concise and plain text.

        Return ONLY a valid JSON object:
        {
            "is_chart": true,
            "ticker_detected": "SYMBOL OR NULL",
            "timeframe": "15m OR NULL",
            "current_price": 123.45,
            "patterns": ["Pattern1", "Pattern2"],
            "sentiment": "Bullish/Bearish/Neutral",
            "confidence": 0.85,
            "action_type": "BUY CALL | BUY PUT | WAIT", 
            "entry_zone": "120-122",
            "target": 130.0,
            "stop_loss": 115.0,
            "recommendation": "Detailed summary (e.g. 'Enter Long on pullback')",
            "analysis": "Comprehensive technical breakdown..."
        }"""

        async def _run_chart_model():
            model_input = [prompt] + image_parts

            available_models: List[str] = []
            for model_name in [
                os.getenv("CHART_ANALYZER_PRIMARY_MODEL", "gemini-2.5-flash"),
                os.getenv("CHART_ANALYZER_SECONDARY_MODEL", "gemini-2.0-flash"),
                os.getenv("CHART_ANALYZER_TERTIARY_MODEL", "gemini-2.0-flash-lite"),
            ]:
                if model_name and model_name not in available_models:
                    available_models.append(model_name)
            _chart_analyzer_status["last_attempted_models"] = available_models

            response = None
            last_error = None

            gen_config = {
                "temperature": 0.2,
                "max_output_tokens": 1024,
                "response_mime_type": "application/json"
            }

            for model_name in available_models:
                try:
                    print(f"Attempting analysis with model: {model_name}...")
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            _client.models.generate_content,
                            model=model_name,
                            contents=model_input,
                            config=gen_config
                        ),
                        timeout=model_timeout_sec
                    )

                    if response and response.text:
                        print(f"Success with {model_name}")
                        _chart_analyzer_status["last_model"] = model_name
                        break
                except Exception as e:
                    print(f"Failed with {model_name}: {e}")
                    last_error = e
                    continue

            if not response or not response.text:
                raise last_error or Exception("All models failed to return content")
            return response

        try:
            response = await request_coordinator.run(
                key=f"chart:{'|'.join(file_signatures)}",
                workload="chart",
                work_fn=_run_chart_model,
                ttl_sec=20.0,
                cache_success_predicate=lambda result: bool(getattr(result, "text", "")),
            )
        except Exception as e:
            return fail_payload(f"AI Model failed. Error: {str(e)}")
        
        # Parse response
        try:
            response_text = response.text.strip()
            result = _parse_chart_analysis_response(response_text)
            if not isinstance(result, dict):
                raise ValueError("Model output was not a JSON object")

            # Ensure UI-required fields always exist.
            if not isinstance(result.get("patterns"), list) or len(result.get("patterns", [])) == 0:
                result["patterns"] = ["No clear pattern"]
            result.setdefault("sentiment", "Neutral")
            result.setdefault("confidence", 0.0)
            result.setdefault("action_type", "WAIT")
            result.setdefault("recommendation", "Monitor setup")
            result.setdefault("analysis", "Model returned limited details.")
            try:
                result["confidence"] = float(result.get("confidence", 0.0))
            except Exception:
                result["confidence"] = 0.0

            # Attach historically approved pattern matches when available.
            try:
                from backend.services.pattern_learning_service import pattern_learning_service

                interval_key = _normalize_pattern_interval(result.get("timeframe"))
                artifact = pattern_learning_service.get_latest(ticker=result.get("ticker_detected") or "^NSEI", interval=interval_key)
                matched_pattern_ids = pattern_learning_service.match_detected_patterns(result.get("patterns", []))
                approved_ids = set(artifact.get("approved_pattern_ids", [])) if artifact.get("status") == "success" else set()
                approved_rows = [
                    row for row in artifact.get("approved_patterns", [])
                    if row.get("pattern_id") in matched_pattern_ids
                ] if artifact.get("status") == "success" else []

                result["recognized_pattern_ids"] = matched_pattern_ids
                result["approved_patterns"] = approved_rows

                if approved_rows:
                    approved_labels = ", ".join(row["pattern_id"] for row in approved_rows)
                    result["analysis"] += f"\n\nPATTERN GOVERNOR: Approved historical pattern match detected: {approved_labels}."
                    result["confidence"] = min(0.95, max(result["confidence"], 0.7))
                elif matched_pattern_ids and approved_ids:
                    result["analysis"] += "\n\nPATTERN GOVERNOR: Pattern recognized, but not in the trained >80% approved set."
                    result["confidence"] = min(result["confidence"], 0.55)
            except Exception as pattern_err:
                result["analysis"] += f"\n\nPATTERN GOVERNOR skipped: {pattern_err}"

            # Deterministic OHLC structure overlay so chart analysis is not only LLM-vision driven.
            try:
                from backend.services.chart_pattern_service import chart_pattern_service

                overlay = chart_pattern_service.analyze(
                    ticker=result.get("ticker_detected") or "^NSEI",
                    timeframe=result.get("timeframe"),
                )
                if overlay.get("status") == "success":
                    existing_patterns = [str(p) for p in result.get("patterns", [])]
                    for pattern in overlay.get("patterns", []):
                        if pattern not in existing_patterns:
                            existing_patterns.append(pattern)
                    result["patterns"] = existing_patterns
                    result["deterministic_overlay"] = overlay
                    result["analysis"] += (
                        "\n\nDETERMINISTIC STRUCTURE OVERLAY: "
                        f"{overlay.get('analysis', 'ok')} "
                        f"Bias={overlay.get('sentiment')} Action={overlay.get('action_type')}."
                    )
                    if result.get("action_type") == "WAIT" and overlay.get("action_type") in {"BUY CALL", "BUY PUT"}:
                        result["action_type"] = overlay["action_type"]
                        result["sentiment"] = overlay.get("sentiment", result.get("sentiment"))
                        result["entry_zone"] = overlay.get("entry_zone", result.get("entry_zone"))
                        result["target"] = overlay.get("target", result.get("target"))
                        result["stop_loss"] = overlay.get("stop_loss", result.get("stop_loss"))
                    result["confidence"] = round(
                        min(
                            0.95,
                            max(float(result.get("confidence", 0.0)), float(overlay.get("confidence", 0.0)) * 0.9),
                        ),
                        4,
                    )
            except Exception as overlay_err:
                result["analysis"] += f"\n\nDETERMINISTIC STRUCTURE OVERLAY skipped: {overlay_err}"
            
            # --- HYBRID INTELLIGENCE: REAL DATA SYNC ---
            ticker = result.get("ticker_detected")
            
            # Normalize Sensex Ticker
            if ticker and isinstance(ticker, str) and any(x in ticker.upper() for x in ["SENSEX", "BSE"]):
                ticker = "^BSESN"
                result["ticker_detected"] = ticker
            
            if ticker and isinstance(ticker, str) and ticker not in {"NULL", "Unknown"}:
                normalized_ticker = ticker.strip().upper()
                if re.fullmatch(r"[A-Z0-9^._-]{1,20}", normalized_ticker):
                    print(f"Autonomous Entity: Detected Ticker {normalized_ticker}. Fetching Real Data...")
                    try:
                        from backend.market_intelligence import get_market_intelligence

                        # Auto-correct ticker for Yahoo Finance
                        search_ticker = normalized_ticker
                        if not normalized_ticker.startswith("^") and normalized_ticker.isalpha() and not normalized_ticker.endswith(".NS"):
                            search_ticker = f"{normalized_ticker}.NS"

                        tech_data = get_market_intelligence(search_ticker)

                        # SYNTHESIS: Verify AI Vision with Hard Data
                        if "error" not in tech_data:
                            result['analysis'] += f"\n\n**REAL-TIME DATA VERIFICATION**:\n"
                            result['analysis'] += f"- Trend: {tech_data.get('trend', 'N/A')}\n"
                            result['analysis'] += f"- RSI: {tech_data.get('momentum_rsi', 'N/A')} (Momentum)\n"
                            result['analysis'] += f"- Volatility: {tech_data.get('volatility_atr', 'N/A')}\n"

                            # Sanity Check Confidence
                            if tech_data.get('trend') == 'Bullish' and result['action_type'] == 'BUY PUT':
                                result['analysis'] += "\nWARNING: Chart looks Bearish but real-time trend is Bullish. Reduce position size."
                                base_conf = float(result.get('confidence', 0.0))
                                result['confidence'] = max(0.0, base_conf - 0.2)
                    except Exception as enrich_err:
                        result['analysis'] += f"\n\nREAL-TIME DATA VERIFICATION skipped: {enrich_err}"
                else:
                    result['analysis'] += "\n\nREAL-TIME DATA VERIFICATION skipped: noisy ticker detection."
            
            _chart_analyzer_status["success_count"] += 1
            _chart_analyzer_status["last_error"] = None
            _chart_analyzer_status["last_duration_ms"] = round((time.time() - started) * 1000.0, 2)
            result["status"] = "success"
            return result
            
        except Exception as e:
            return fail_payload(f"JSON Parse Error: {str(e)}", recommendation="Parsing Failed") | {
                "patterns": ["Error"],
                "recommendation": "Parsing Failed",
            }
            
    except Exception as e:
        return fail_payload(f"System Error: {str(e)}", recommendation="Analysis failed.") | {
            "patterns": ["Error"],
            "recommendation": "Analysis failed.",
        }

@app.get("/api/chart/deterministic_context")
def get_chart_deterministic_context(ticker: str = "^NSEI", timeframe: str = "15m"):
    try:
        from backend.services.chart_pattern_service import chart_pattern_service

        return chart_pattern_service.analyze(ticker=ticker, timeframe=timeframe)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/quant/institutional")
async def get_institutional_quant(ticker: str = "^NSEI"):
    """
    Fetch Institutional Quant Analysis: OU Process + MST + Regimes
    """
    try:
        # Use lazy-loaded quant system from service manager
        system = service_manager.advanced_trading_system.quant_system
        if ticker != system.ticker:
            from backend.integrated_quant_system import IntegratedQuantSystem
            system = IntegratedQuantSystem(ticker)
            
        # Run analysis
        data = system.run_comprehensive_analysis()
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- DASHBOARD ENDPOINTS (Consolidated) ---

@app.get("/api/dashboard/summary")
async def get_dashboard_summary(ticker: str = "^NSEI"):
    """Get high-level dashboard summary for a specific ticker"""
    timing = service_manager.market_timing

    analysis = await _get_dashboard_analysis_cached(ticker)
    
    return {
        "market_status": {
            "is_open": timing.is_market_open(),
            "session": timing.get_current_session(),
            "next_event": timing.get_timing_signals()[0] if timing.get_timing_signals() else None
        },
        "trade_signals": {
            "action": analysis.get("combined_entry_decision", {}).get("action", "WAIT"),
            "confidence": analysis.get("combined_entry_decision", {}).get("confidence", 0),
            "active_trades": len(service_manager.advanced_trading_system.active_trades)
        },
        "risk_metrics": {
            "market_volatility": analysis.get("quant_institutional", {}).get("risk_assessment", {}).get("risk_level", "MEDIUM"),
            "var_95": f"{analysis.get('quant_institutional', {}).get('risk_assessment', {}).get('composite_risk_score', 0.5) * 10:.1f}%"
        }
    }

@app.get("/api/dashboard/market_analysis")
async def get_market_analysis_details(ticker: str = "^NSEI"):
    """Get detailed market analysis"""
    analysis = await _get_dashboard_analysis_cached(ticker)
    
    # Get Monte Carlo risk assessment
    from backend.monte_carlo import quick_risk_assessment
    loop = asyncio.get_event_loop()
    risk = await loop.run_in_executor(None, lambda: quick_risk_assessment(ticker=ticker, days_ahead=5))
    
    return {
        "technical": analysis,
        "risk_forecast": risk
    }

@app.get("/api/dashboard/strategy_performance")
async def get_dashboard_strategy_performance():
    """Get Bayesian strategy performance metrics"""
    model = service_manager.bayesian_model
    beliefs = model.get_current_beliefs()
    
    return {
        "win_rate": beliefs["win_rate"],
        "profitability_prob": beliefs["probabilities"]["profitable"],
        "recommendation": beliefs["recommendation"],
        "trade_history": model.trade_history[-10:]
    }

@app.get("/api/dashboard/options_chain")
async def get_dashboard_options_chain(ticker: str = "^NSEI"):
    """
    Get synthetic/analytical options chain with Greeks for dashboard rendering.
    Falls back to Black-Scholes Greeks when broker option-chain feed is unavailable.
    """
    from datetime import datetime as dt
    import pytz
    from backend.intraday_utils import get_next_expiry
    from backend.options_indicators import OptionsGreeksAnalyzer

    try:
        if async_market_data_service:
            df = await async_market_data_service.get_market_data(ticker, "5d", "5m")
        else:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, lambda: get_sync_market_data(ticker, "5d", "5m"))

        if df.empty:
            return {
                "status": "error",
                "message": f"No market data available for {ticker}",
                "spot_price": 0.0,
                "expiry": "-",
                "chain": []
            }

        spot_price = float(df["Close"].iloc[-1])
        expiry_label = get_next_expiry()

        # Convert expiry label like "20-Feb-2026" to days-to-expiry.
        ist = pytz.timezone("Asia/Kolkata")
        try:
            expiry_dt = dt.strptime(expiry_label, "%d-%b-%Y").replace(tzinfo=ist)
            days_to_expiry = max((expiry_dt - dt.now(ist)).days, 1)
        except Exception:
            days_to_expiry = 7

        strike_step = 50 if ("NSEI" in ticker or "NIFTY" in ticker) else 100
        atm_strike = round(spot_price / strike_step) * strike_step
        strikes = [atm_strike + i * strike_step for i in range(-5, 6)]

        analyzer = OptionsGreeksAnalyzer()
        iv_assumption = 0.20
        chain = []

        for strike in strikes:
            call = analyzer.calculate_black_scholes_greeks(
                spot_price=spot_price,
                strike_price=strike,
                time_to_expiry_days=days_to_expiry,
                implied_volatility=iv_assumption,
                option_type="CE"
            )
            put = analyzer.calculate_black_scholes_greeks(
                spot_price=spot_price,
                strike_price=strike,
                time_to_expiry_days=days_to_expiry,
                implied_volatility=iv_assumption,
                option_type="PE"
            )

            chain.append({
                "strike": strike,
                "call": {
                    "price": round(float(analyzer._calculate_option_price(spot_price, strike, days_to_expiry / 365.0, iv_assumption, "CE")), 2),
                    "oi": 0,
                    "greeks": call["greeks"]
                },
                "put": {
                    "price": round(float(analyzer._calculate_option_price(spot_price, strike, days_to_expiry / 365.0, iv_assumption, "PE")), 2),
                    "oi": 0,
                    "greeks": put["greeks"]
                }
            })

        return {
            "status": "success",
            "spot_price": round(spot_price, 2),
            "expiry": expiry_label,
            "chain": chain
        }
    except Exception as e:
        logger.exception("Failed to build dashboard options chain")
        return {
            "status": "error",
            "message": str(e),
            "spot_price": 0.0,
            "expiry": "-",
            "chain": []
        }


@app.post("/api/chat_analysis")
async def chat_with_analysis(
    context: str = Form(...),
    question: str = Form(...),
    file: UploadFile = File(None)
):
    """
    Follow-up chat with the AI. Supports optional image upload for context.
    Using Form data to allow file upload alongside text.
    """
    try:
        import hashlib
        prompt = f"""
        You are an expert financial analyst assistant. 
        
        Previous Analysis Context:
        {context}
        
        User Question: {question}
        
        Answer the user's question concisely based on the context provided.
        If an image is attached, the user is referring to it in their question.
        """
        
        image = None
        file_signature = "nofile"
        if file:
            contents = await file.read()
            file_signature = hashlib.sha1(contents).hexdigest()[:16]
            image = Image.open(io.BytesIO(contents))
            print("Chat: Image attached to message.")

        async def _run_chat():
            chat_timeout_sec = float(os.getenv("CHART_CHAT_TIMEOUT_SEC", "18"))
            return await asyncio.wait_for(
                asyncio.to_thread(generate_content_with_fallback, prompt, image),
                timeout=chat_timeout_sec
            )

        response = await request_coordinator.run(
            key=f"chat:{hashlib.sha1((context + '|' + question + '|' + file_signature).encode('utf-8')).hexdigest()[:20]}",
            workload="chat",
            work_fn=_run_chat,
            ttl_sec=15.0,
            cache_success_predicate=lambda result: bool(getattr(result, "text", "")),
        )
        return {"status": "success", "answer": response.text}

    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Self-Learning & Continuous Improvement APIs ---

# Learning manager initialized via service manager
@app.on_event("startup")
async def startup_event():
    """
    Initialize systems on startup without blocking the main event loop.
    """
    if _core_dependency_error is not None:
        logger.warning("Skipping startup warm tasks in degraded mode: %s", _core_dependency_error_message)
        return

    # Pre-warm Learning Manager
    if service_manager.learning_manager:
        print("Initializing Learning Manager in background...")
        import threading
        def init_learning():
            try:
                service_manager.learning_manager.initialize()
                print("Learning Manager initialized successfully.")
            except Exception as e:
                print(f"Warning: Learning manager initialization failed: {e}")
        threading.Thread(target=init_learning, daemon=True).start()

    # Pre-warm Alpha Scanner
    try:
        from backend.market_scanner import AlphaScanner
        import asyncio
        scanner = AlphaScanner()
        asyncio.create_task(scanner._run_background_scan())
        print("AlphaScanner pre-warming started in background.")
    except Exception as e:
        print(f"Warning: Could not pre-warm AlphaScanner: {e}")

@app.post("/api/learning/track_trade")
async def track_trade(trade_data: dict):
    """
    Track a live trade outcome for continuous learning.
    """
    if not service_manager.learning_manager:
        return {"status": "error", "message": "Learning manager not available"}
        
    try:
        result = service_manager.learning_manager.process_trade(trade_data)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/learning/performance")
def get_learning_performance(days: int = 30):
    """
    Get performance report of the self-learning models.
    """
    if not service_manager.learning_manager:
        return {"status": "error", "message": "Learning manager not available"}
        
    try:
        report = service_manager.learning_manager.get_performance_report()
        return {"status": "success", "data": report}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/learning/suggestions")
def get_learning_suggestions():
    """
    Get AI-driven improvement suggestions based on recent performance.
    """
    if not service_manager.learning_manager:
        return {"status": "error", "message": "Learning manager not available"}

    try:
        suggestions = service_manager.learning_manager.get_improvement_suggestions()
        return {"status": "success", "data": suggestions}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/learning/optimized_signals")
def get_optimized_signals(ticker: str = "^NSEI", interval: str = "5m"):
    """
    Get trading signals generated by the self-learning model.
    """
    if not service_manager.learning_manager:
        return {"status": "error", "message": "Learning manager not available"}

    from backend.services.market_data_service import get_sync_market_data
    
    try:
        # Fetch data through standardized service
        df = get_sync_market_data(ticker, "5d", interval)
        if df.empty:
            return {"status": "error", "message": "No data fetched"}
            
        signals = service_manager.learning_manager.get_optimized_signals(df)
        return {"status": "success", "data": signals}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/learning/retrain")
def force_retrain():
    """
    Manually trigger a retraining session.
    """
    if not service_manager.learning_manager:
        return {"status": "error", "message": "Learning manager not available"}

    try:
        result = service_manager.learning_manager.learner.learn_from_history(
            start_date=(datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d'),
            interval="15m"
        )
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/learning/dashboard")
def get_learning_dashboard():
    """
    Get the Plotly dashboard JSON for learning performance.
    """
    if not service_manager.learning_manager:
        return {"status": "error", "message": "Learning manager not available"}

    try:
        fig = service_manager.learning_manager.get_dashboard()
        if fig:
            import json
            return {"status": "success", "data": json.loads(fig.to_json())}
        return {"status": "error", "message": "Dashboard not available"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/broker/connect")
def connect_broker(payload: dict = Body(...)):
    """
    Connect to a broker.
    Payload: {"mode": "PAPER" | "ANGEL_ONE"}
    """
    mode = payload.get("mode", "PAPER")
    try:
        result = service_manager.execution_engine.switch_mode(mode)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/broker/status")
def get_broker_status():
    """Get connection status and P&L Summary"""
    return service_manager.execution_engine.get_status()

@app.get("/api/broker/providers/status")
def get_broker_provider_status():
    """Get sanitized market data provider readiness details."""
    try:
        return {"status": "success", "providers": async_market_data_service.get_provider_status()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/broker/portfolio")
def get_broker_portfolio():
    """Get active positions and order history"""
    return service_manager.execution_engine.get_portfolio()

@app.post("/api/broker/order")
def place_order(order: dict = Body(...)):
    """
    Place a manual order.
    """
    result = service_manager.execution_engine.execute_order(order)

    broker_status = (result or {}).get("status", "")
    if broker_status in {"FILLED", "SUBMITTED", "EXECUTED", "SUCCESS"}:
        return {"status": "success", "data": result}

    reason = (result or {}).get("reason") or (result or {}).get("message") or "Order rejected"
    return {"status": "error", "message": reason, "data": result}


@app.get("/api/execution/quality")
def get_execution_quality(ticker: Optional[str] = None):
    """Get execution quality summary for manual/live execution feedback."""
    try:
        from backend.services.execution_quality_service import execution_quality_service

        return execution_quality_service.get_summary(ticker=ticker)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/execution/forecast")
def get_execution_forecast(
    ticker: str = "^NSEI",
    side: str = "BUY",
    broker: Optional[str] = None,
    order_type: str = "MARKET",
):
    """Predict expected execution friction before placing an order."""
    try:
        from backend.services.execution_quality_service import execution_quality_service

        broker_name = broker or type(service_manager.execution_engine.broker).__name__
        return execution_quality_service.forecast_execution(
            symbol=ticker,
            side=side,
            broker=broker_name,
            order_type=order_type,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/execution/models")
def get_execution_models(
    ticker: Optional[str] = None,
    broker: Optional[str] = None,
):
    """Inspect broker/session/order-type execution models derived from fill history."""
    try:
        from backend.services.execution_quality_service import execution_quality_service

        return execution_quality_service.get_models(symbol=ticker, broker=broker)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/execution/models/rebuild")
def rebuild_execution_models():
    """Rebuild broker-specific execution models from stored execution events."""
    try:
        from backend.services.execution_quality_service import execution_quality_service

        return execution_quality_service.rebuild_models()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/routing/status")
def get_routing_status(ticker: str = "^NSEI"):
    """Get ranked execution and data routing snapshot."""
    try:
        from backend.services.routing_service import routing_service

        return routing_service.get_routing_snapshot(ticker=ticker)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/routing/apply")
def apply_routing_switch(payload: dict = Body(default={})):
    """Attempt safe automatic broker switching if controls allow it."""
    try:
        from backend.services.routing_service import routing_service

        return routing_service.apply_auto_switch(ticker=payload.get("ticker", "^NSEI"))
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ops/config")
def get_ops_config():
    try:
        from backend.services.ops_control_service import ops_control_service

        return ops_control_service.get_config()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ops/config")
def update_ops_config(payload: dict = Body(default={})):
    try:
        from backend.services.ops_control_service import ops_control_service

        return ops_control_service.update_config(payload)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Unified Fusion / ML / Walk-forward / EA Bridge APIs ---

@app.get("/api/fusion/strategies")
def get_registered_fusion_strategies():
    """
    List all registered strategy modules in the fusion engine.
    """
    try:
        from backend.services.decision_fusion_service import fusion_service
        return {
            "status": "success",
            "data": {
                "strategies": fusion_service.registry.list_ids()
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/fusion/status")
def get_fusion_runtime_status():
    """
    Runtime coordination status for fusion subsystem.
    """
    try:
        from backend.services.decision_fusion_service import fusion_service
        return fusion_service.get_runtime_status()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/memory/status")
def get_memory_runtime_status():
    try:
        from backend.services.memory_service import memory_service

        return memory_service.get_runtime_status()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/memory/search")
def search_memory(
    query: str = "",
    limit: int = 8,
    memory_type: str = "",
    ticker: str = "",
    interval: str = "",
    regime: str = "",
    session_bucket: str = "",
    setup_family: str = "",
):
    try:
        from backend.services.memory_service import memory_service

        return memory_service.retrieve_memories(
            query=query,
            limit=max(min(int(limit), 20), 1),
            memory_type=memory_type or None,
            ticker=ticker or None,
            interval=interval or None,
            regime=regime or None,
            session_bucket=session_bucket or None,
            setup_family=setup_family or None,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/memory/context")
def get_memory_context(
    ticker: str = "^NSEI",
    interval: str = "15m",
    regime: str = "",
    session_bucket: str = "",
    setup_family: str = "",
    query: str = "",
    limit: int = 6,
):
    try:
        from backend.services.memory_service import memory_service

        return memory_service.build_context(
            ticker=ticker,
            interval=interval,
            regime=regime or None,
            session_bucket=session_bucket or None,
            setup_family=setup_family or None,
            query=query,
            limit=max(min(int(limit), 20), 1),
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/memory/write")
def write_memory(payload: dict = Body(default={})):
    try:
        from backend.services.memory_service import memory_service

        success = memory_service.add_memory(
            content=str(payload.get("content") or ""),
            source=str(payload.get("source") or "api_manual_write"),
            metadata=payload.get("metadata") or {},
        )
        return {"status": "success" if success else "error", "stored": bool(success)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/memory/maintenance")
def run_memory_maintenance():
    try:
        from backend.services.memory_service import memory_service

        return memory_service.run_maintenance()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/memory/validate")
def validate_memory(payload: dict = Body(default={})):
    try:
        from backend.services.memory_service import memory_service

        return memory_service.record_validation(
            memory_id=str(payload.get("memory_id") or ""),
            outcome=str(payload.get("outcome") or "failure"),
            details=payload.get("details") or {},
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/memory/research")
def get_memory_research_snapshot(
    ticker: str = "",
    interval: str = "",
):
    try:
        from backend.services.memory_service import memory_service

        return memory_service.get_research_snapshot(
            ticker=ticker or None,
            interval=interval or None,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/social/intel")
def get_social_intel(ticker: str = ""):
    """Returns real-time scraped social media trade calls from Twitter/X, Reddit, and StockTwits"""
    try:
        from backend.services.social_crawler_service import social_crawler_service
        data = social_crawler_service.crawl_social_sources(ticker=ticker)
        return {"status": "success", "count": len(data), "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/social/scan")
def trigger_social_scan(payload: dict = Body(default={})):
    """Triggers an active scan across Twitter/X, Reddit, and StockTwits profilers"""
    try:
        from backend.services.social_crawler_service import social_crawler_service
        ticker = payload.get("ticker", "")
        data = social_crawler_service.crawl_social_sources(ticker=ticker)
        return {"status": "success", "message": f"Scraped {len(data)} social intelligence posts.", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/quant/integrated-decision")
def get_integrated_decision(ticker: str = "^NSEI", capital: float = 1000000.0):
    """Runs IntegratedTradingDecisionEngine across momentum, volatility sizing, regime detection, OU mean reversion, and MST analysis"""
    try:
        from backend.trading_decision_engine import IntegratedTradingDecisionEngine
        engine = IntegratedTradingDecisionEngine(ticker=ticker, capital=capital)
        results = engine.run_comprehensive_analysis()
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/quant/integrated-decision")
def post_integrated_decision(payload: dict = Body(default={})):
    """Triggers IntegratedTradingDecisionEngine with custom payload"""
    try:
        ticker = payload.get("ticker", "^NSEI")
        capital = float(payload.get("capital", 1000000.0))
        from backend.trading_decision_engine import IntegratedTradingDecisionEngine
        engine = IntegratedTradingDecisionEngine(ticker=ticker, capital=capital)
        results = engine.run_comprehensive_analysis()
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/credentials")
def get_credentials():
    """Returns current configuration status of API keys (masked for privacy)"""
    def _mask(val: Optional[str]) -> str:
        if not val or "your_" in val or len(val) < 6:
            return ""
        return val[:3] + "..." + val[-3:]

    angel_key = os.getenv("ANGEL_API_KEY") or os.getenv("ANGEL_ONE_API_KEY")
    angel_client = os.getenv("ANGEL_CLIENT_ID") or os.getenv("ANGEL_ONE_CLIENT_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")
    news_key = os.getenv("NEWS_API_KEY")

    return {
        "status": "success",
        "angel_one": {
            "is_configured": bool(angel_key and "your_" not in angel_key and angel_client and "your_" not in angel_client),
            "client_id": _mask(angel_client),
            "api_key": _mask(angel_key),
        },
        "gemini": {
            "is_configured": bool(gemini_key and "your_" not in gemini_key),
            "api_key": _mask(gemini_key),
        },
        "news_api": {
            "is_configured": bool(news_key and "your_" not in news_key),
            "api_key": _mask(news_key),
        }
    }

@app.post("/api/credentials")
def update_credentials(payload: dict = Body(default={})):
    """Dynamically update API keys in environment and persist to backend/.env"""
    try:
        env_updates = {}
        if payload.get("angel_api_key"):
            val = str(payload["angel_api_key"]).strip()
            os.environ["ANGEL_API_KEY"] = val
            os.environ["ANGEL_ONE_API_KEY"] = val
            env_updates["ANGEL_ONE_API_KEY"] = val
            env_updates["ANGEL_API_KEY"] = val

        if payload.get("angel_client_id"):
            val = str(payload["angel_client_id"]).strip()
            os.environ["ANGEL_CLIENT_ID"] = val
            os.environ["ANGEL_ONE_CLIENT_ID"] = val
            env_updates["ANGEL_ONE_CLIENT_ID"] = val
            env_updates["ANGEL_CLIENT_ID"] = val

        if payload.get("angel_password"):
            val = str(payload["angel_password"]).strip()
            os.environ["ANGEL_PASSWORD"] = val
            os.environ["ANGEL_ONE_PASSWORD"] = val
            env_updates["ANGEL_ONE_PASSWORD"] = val
            env_updates["ANGEL_PASSWORD"] = val

        if payload.get("angel_totp_key"):
            val = str(payload["angel_totp_key"]).strip()
            os.environ["ANGEL_TOTP_KEY"] = val
            os.environ["ANGEL_ONE_TOTP_KEY"] = val
            env_updates["ANGEL_ONE_TOTP_KEY"] = val
            env_updates["ANGEL_TOTP_KEY"] = val

        if payload.get("gemini_api_key"):
            val = str(payload["gemini_api_key"]).strip()
            os.environ["GEMINI_API_KEY"] = val
            env_updates["GEMINI_API_KEY"] = val

        if payload.get("news_api_key"):
            val = str(payload["news_api_key"]).strip()
            os.environ["NEWS_API_KEY"] = val
            env_updates["NEWS_API_KEY"] = val

        # Persist to backend/.env file
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = []
        updated_keys = set()
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                k, _ = line.split("=", 1)
                k = k.strip()
                if k in env_updates:
                    new_lines.append(f"{k}={env_updates[k]}\n")
                    updated_keys.add(k)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        for k, v in env_updates.items():
            if k not in updated_keys:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        return {"status": "success", "message": "API credentials updated and persisted successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/fusion/decision")
async def get_fusion_decision(payload: dict = Body(default={})):
    """
    Unified trading decision endpoint.
    Fuses strategies + quant + regime + news + Monte Carlo risk.
    """
    try:
        from backend.services.decision_fusion_service import fusion_service

        ticker = payload.get("ticker", "^NSEI")
        period = payload.get("period", "60d")
        interval = payload.get("interval", "15m")
        capital = float(payload.get("capital", 100000.0))

        response = await request_coordinator.run(
            key=f"fusion:{ticker}|{period}|{interval}|{round(capital, 2)}",
            workload="fusion",
            work_fn=lambda: fusion_service.generate_decision(
                ticker=ticker,
                period=period,
                interval=interval,
                capital=capital,
            ),
            ttl_sec=8.0,
            cache_success_predicate=lambda result: isinstance(result, dict) and result.get("status") == "success",
        )
        if payload.get("track_signal") and response.get("status") == "success":
            try:
                from backend.services.live_signal_tracker_service import live_signal_tracker_service

                decision = response.get("decision") or {}
                live_signal_tracker_service.record_signal(
                    ticker=ticker,
                    interval=interval,
                    source="fusion_decision",
                    action=str(decision.get("action", "HOLD")),
                    entry=float(decision.get("entry", response.get("market", {}).get("price", 0.0)) or 0.0),
                    stop_loss=float(decision.get("stop_loss", 0.0) or 0.0),
                    take_profit=float(decision.get("take_profit", 0.0) or 0.0),
                    confidence=float(decision.get("confidence", 0.0) or 0.0),
                    raw_payload=response,
                )
            except Exception:
                pass
        return response
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ml/fusion/dataset")
async def build_fusion_training_dataset(payload: dict = Body(default={})):
    """
    Build supervised training dataset with technical + optional news features.
    """
    try:
        from backend.services.training_data_service import DatasetBuildConfig, training_data_service

        cfg = DatasetBuildConfig(
            ticker=payload.get("ticker", "^NSEI"),
            interval=payload.get("interval", "15m"),
            period=payload.get("period", "1y"),
            horizon=int(payload.get("horizon", 5)),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            include_news=bool(payload.get("include_news", True)),
        )
        return await training_data_service.build_dataset(cfg)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ml/fusion/train")
def train_fusion_model(payload: dict = Body(default={})):
    """
    Train the fusion classifier from a built dataset CSV.
    """
    try:
        from backend.services.fusion_model_service import fusion_model_service

        dataset_path = payload.get("dataset_path")
        if not dataset_path:
            return {"status": "error", "message": "dataset_path is required"}

        return fusion_model_service.train_from_dataset(
            dataset_path=dataset_path,
            target=payload.get("target", "target_direction"),
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ml/fusion/predict")
def predict_fusion_direction(payload: dict = Body(default={})):
    """
    Predict up/down direction using the trained fusion model.
    """
    try:
        from backend.services.fusion_model_service import fusion_model_service

        features = payload.get("features") or {}
        if not isinstance(features, dict) or not features:
            return {"status": "error", "message": "features dict is required"}

        return fusion_model_service.predict(features)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/backtest/walkforward")
def run_walkforward_backtest(payload: dict = Body(default={})):
    """
    Walk-forward out-of-sample backtest with rolling retraining.
    """
    try:
        from backend.backtest_walkforward import WalkForwardBacktester, WalkForwardConfig

        cfg = WalkForwardConfig(
            ticker=payload.get("ticker", "^NSEI"),
            interval=payload.get("interval", "15m"),
            period=payload.get("period", "1y"),
            horizon=int(payload.get("horizon", 5)),
            train_window=int(payload.get("train_window", 320)),
            test_window=int(payload.get("test_window", 80)),
            step_size=int(payload.get("step_size", 40)),
            slippage_bps=float(payload.get("slippage_bps", 3.0)),
            transaction_cost_bps=float(payload.get("transaction_cost_bps", 2.0)),
        )
        return WalkForwardBacktester(cfg).run()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ea/export_signal")
async def export_ea_signal(payload: dict = Body(default={})):
    """
    Generate a fusion decision and export a normalized EA signal JSON.
    """
    try:
        from backend.adapters.ea_bridge import ea_bridge_adapter
        from backend.services.decision_fusion_service import fusion_service

        fusion_response = await fusion_service.generate_decision(
            ticker=payload.get("ticker", "^NSEI"),
            period=payload.get("period", "60d"),
            interval=payload.get("interval", "15m"),
            capital=float(payload.get("capital", 100000.0)),
        )
        if fusion_response.get("status") != "success":
            return fusion_response

        signal_payload = ea_bridge_adapter.build_signal_payload(
            fusion_response=fusion_response,
            strategy_tag=str(payload.get("strategy_tag", "C0MR4DE_TERMINAL_FUSION_V1")),
        )
        try:
            from backend.services.live_signal_tracker_service import live_signal_tracker_service

            tracked = live_signal_tracker_service.record_signal(
                ticker=str(signal_payload.get("symbol", "^NSEI")),
                interval=str((signal_payload.get("meta") or {}).get("interval") or payload.get("interval", "15m")),
                source=str(signal_payload.get("source", "ea_export")),
                action=str(signal_payload.get("action", "HOLD")),
                entry=float(signal_payload.get("entry", 0.0) or 0.0),
                stop_loss=float(signal_payload.get("stop_loss", 0.0) or 0.0),
                take_profit=float(signal_payload.get("take_profit", 0.0) or 0.0),
                confidence=float(signal_payload.get("confidence", 0.0) or 0.0),
                raw_payload=signal_payload,
                generated_at=str(signal_payload.get("generated_at") or ""),
            )
            tracked_signal = tracked.get("signal") or {}
            if tracked_signal.get("signal_id"):
                signal_payload["signal_id"] = tracked_signal.get("signal_id")
                signal_payload.setdefault("meta", {})["signal_id"] = tracked_signal.get("signal_id")
        except Exception as tracker_err:
            tracked = {"status": "error", "message": str(tracker_err)}
        write_result = ea_bridge_adapter.write_signal(signal_payload)

        return {
            "status": "success",
            "signal": signal_payload,
            "write": write_result,
            "tracking": tracked,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ea/latest_signal")
def get_latest_ea_signal():
    """
    Get latest signal exported for Expert Advisor consumption.
    """
    try:
        from backend.adapters.ea_bridge import ea_bridge_adapter
        return ea_bridge_adapter.get_latest_signal()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/signals/settle")
def settle_live_signals(payload: dict = Body(default={})):
    try:
        from backend.services.live_signal_tracker_service import live_signal_tracker_service

        return live_signal_tracker_service.settle_open_signals(ticker=payload.get("ticker"))
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/signals/performance")
def get_live_signal_performance(ticker: Optional[str] = None):
    try:
        from backend.services.live_signal_tracker_service import live_signal_tracker_service

        return live_signal_tracker_service.get_summary(ticker=ticker)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ea/execution_feedback")
def ingest_ea_execution_feedback(payload: dict = Body(default={})):
    """
    Persist EA execution feedback for post-trade learning/analysis.
    """
    try:
        from backend.adapters.ea_bridge import ea_bridge_adapter
        write_result = ea_bridge_adapter.save_execution_feedback(payload)
        tracking_result = None
        execution_result = None
        try:
            from backend.services.live_signal_tracker_service import live_signal_tracker_service

            signal_id = payload.get("signal_id")
            if signal_id:
                tracking_result = live_signal_tracker_service.save_execution_feedback(str(signal_id), payload)
        except Exception as tracker_err:
            tracking_result = {"status": "error", "message": str(tracker_err)}
        try:
            from backend.services.execution_quality_service import execution_quality_service

            execution_result = execution_quality_service.save_feedback(payload)
        except Exception as exec_err:
            execution_result = {"status": "error", "message": str(exec_err)}
        return {"status": "success", "write": write_result, "tracking": tracking_result, "execution_quality": execution_result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


