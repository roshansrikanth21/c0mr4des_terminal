"""Market data: Angel One SmartAPI when credentials exist, Yahoo as fallback.

Every frame returned has an IST DatetimeIndex and columns open/high/low/close/volume.
Index spot volume is always 0 on both feeds: nothing downstream may depend on it.
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from datetime import datetime, timedelta

import pandas as pd

from .config import IST, INSTRUMENTS, Instrument

log = logging.getLogger("engine.data")

_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_LOCK = threading.Lock()
CACHE_TTL = {"1m": 20, "5m": 30, "15m": 60, "1d": 600}
YF_PERIOD = {"1m": "5d", "5m": "60d", "15m": "60d", "1d": "2y"}
ANGEL_INTERVAL = {"1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE", "1d": "ONE_DAY"}
ANGEL_LOOKBACK_DAYS = {"1m": 5, "5m": 25, "15m": 55, "1d": 600}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].copy()
    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
    df.index = idx
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    # Reject impossible bars instead of trusting them.
    ok = (df["high"] >= df[["open", "close"]].max(axis=1)) & (df["low"] <= df[["open", "close"]].min(axis=1))
    return df[ok].astype(float)


def _token_error(res) -> bool:
    """SmartAPI returns expired/invalid sessions as a normal response, not an exception."""
    if not isinstance(res, dict) or res.get("status") or res.get("success"):
        return False
    msg = f"{res.get('errorCode', '')} {res.get('message', '')}".lower()
    return any(k in msg for k in ("ag8001", "ag8002", "ag8003", "token", "session"))


class AngelClient:
    """Thin SmartAPI wrapper: login once a day, re-login when the session expires, back off on failure.

    Angel One sessions die at midnight IST, so a long-running server must log in again every day.
    """

    def __init__(self):
        self.api = None
        self._login_day = None
        self._failed_at = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def configured() -> bool:
        return all(os.getenv(k) for k in ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_KEY"))

    def session(self):
        if not self.configured():
            return None
        with self._lock:
            if self.api is not None and self._login_day == datetime.now(IST).date():
                return self.api
            self.api = None
            if _time.time() - self._failed_at < 300:
                return None
            try:
                import pyotp
                from SmartApi import SmartConnect

                logging.getLogger("logzero_default").setLevel(logging.CRITICAL)  # SmartAPI logs full request headers incl. the session token

                api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
                totp = pyotp.TOTP(os.environ["ANGEL_TOTP_KEY"]).now()
                res = api.generateSession(os.environ["ANGEL_CLIENT_ID"], os.environ["ANGEL_PASSWORD"], totp)
                if not res or not res.get("status"):
                    raise RuntimeError(res.get("message") if isinstance(res, dict) else "login failed")
                self.api, self._login_day = api, datetime.now(IST).date()
                log.info("Angel One session established")
                return api
            except Exception as exc:  # noqa: BLE001
                self._failed_at = _time.time()
                log.warning("Angel One login failed: %s", exc)
                return None

    def reset(self):
        with self._lock:
            self.api = None

    def candles(self, inst: Instrument, interval: str) -> pd.DataFrame | None:
        api = self.session()
        if api is None:
            return None
        now = datetime.now(IST)
        params = {
            "exchange": inst.angel_exchange,
            "symboltoken": inst.angel_spot_token,
            "interval": ANGEL_INTERVAL[interval],
            "fromdate": (now - timedelta(days=ANGEL_LOOKBACK_DAYS[interval])).strftime("%Y-%m-%d %H:%M"),
            "todate": now.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            res = api.getCandleData(params)
            if _token_error(res):
                log.warning("Angel session expired - logging in again")
                self.reset()
                return None
            rows = (res or {}).get("data") or []
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")
            return _normalize(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("Angel candles failed (%s %s): %s", inst.key, interval, exc)
            self.reset()
            return None

    def ltp(self, exchange: str, tokens: list[str]) -> dict:
        """FULL quotes for up to 50 tokens: {token: {ltp, oi, volume, ...}}."""
        api = self.session()
        if api is None or not tokens:
            return {}
        out = {}
        try:
            for i in range(0, len(tokens), 50):
                res = api.getMarketData("FULL", {exchange: tokens[i:i + 50]})
                if _token_error(res):
                    log.warning("Angel session expired - logging in again")
                    self.reset()
                    return out
                for q in ((res or {}).get("data") or {}).get("fetched", []) or []:
                    out[str(q.get("symbolToken"))] = q
        except Exception as exc:  # noqa: BLE001
            log.warning("Angel quotes failed: %s", exc)
        return out


angel = AngelClient()


def _yahoo(symbol: str, interval: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf

        df = yf.download(symbol, interval=interval, period=YF_PERIOD[interval], progress=False,
                         auto_adjust=False, multi_level_index=False, threads=False)
        df = _normalize(df)
        if interval == "1d" and not df.empty:
            df.index = df.index.normalize()
        return df if not df.empty else None
    except Exception as exc:  # noqa: BLE001
        log.warning("Yahoo download failed (%s %s): %s", symbol, interval, exc)
        return None


def get_candles(key: str, interval: str = "5m") -> tuple[pd.DataFrame, str]:
    """Return (frame, source). Raises RuntimeError if no feed works. Never fabricates data."""
    inst = INSTRUMENTS[key]
    ck = (key, interval)
    with _LOCK:
        hit = _CACHE.get(ck)
        if hit and _time.time() - hit[0] < CACHE_TTL[interval]:
            return hit[1], hit[1].attrs.get("source", "cache")
    df, source = angel.candles(inst, interval), "angel_one"
    if df is None or df.empty:
        df, source = _yahoo(inst.yf_symbol, interval), "yahoo_delayed"
    if df is None or df.empty:
        raise RuntimeError(f"No market data available for {key} {interval}")
    df.attrs["source"] = source
    with _LOCK:
        _CACHE[ck] = (_time.time(), df)
    return df, source


def get_quote_series(symbol: str, period: str = "5d", interval: str = "1d") -> pd.DataFrame | None:
    """Global cues (Yahoo symbols), cached 5 min."""
    ck = ("q", symbol, period, interval)
    with _LOCK:
        hit = _CACHE.get(ck)
        if hit and _time.time() - hit[0] < 300:
            return hit[1]
    try:
        import yfinance as yf

        df = _normalize(yf.download(symbol, period=period, interval=interval, progress=False,
                                    auto_adjust=False, multi_level_index=False, threads=False))
    except Exception:  # noqa: BLE001
        df = None
    if df is not None and not df.empty:
        with _LOCK:
            _CACHE[ck] = (_time.time(), df)
        return df
    return None


def closed_bars(df: pd.DataFrame, interval: str, now: datetime | None = None) -> pd.DataFrame:
    """Drop the still-forming last bar so signals never peek at an unfinished candle."""
    if df.empty or interval == "1d":
        return df
    now = now or datetime.now(IST)
    minutes = {"1m": 1, "5m": 5, "15m": 15}[interval]
    if df.index[-1] + timedelta(minutes=minutes) > now:
        return df.iloc[:-1]
    return df
