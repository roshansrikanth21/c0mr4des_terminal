"""Replay mode: run the live system on a past trading day as if it were happening now.

A simulated clock starts at 09:10 IST on the chosen day and advances `speed`x faster than real
time (60 = one market minute per real second, a full session in ~6 minutes). Candles are cut
at the simulated time so nothing in the future is visible. Replay trades go to a separate paper
book (data/replay_paper.json) and Telegram alerts are tagged [REPLAY].
"""
from __future__ import annotations

import threading
import time as _time
from datetime import date, datetime, time, timedelta

import pandas as pd

from .config import IST

_lock = threading.Lock()
_state: dict = {"active": False}


def start(day: date, speed: float = 60.0, start_at: time = time(9, 10)) -> dict:
    with _lock:
        _state.clear()
        _state.update({"active": True, "day": day, "speed": max(1.0, min(float(speed), 600.0)),
                       "sim_start": datetime.combine(day, start_at, IST), "real_start": _time.time(),
                       "paused_at": None})
    return status()


def stop() -> dict:
    with _lock:
        _state.clear()
        _state["active"] = False
    return status()


def pause(on: bool) -> dict:
    with _lock:
        if not _state.get("active"):
            return status()
        if on and _state["paused_at"] is None:
            _state["paused_at"] = _time.time()
        elif not on and _state["paused_at"] is not None:
            _state["real_start"] += _time.time() - _state["paused_at"]
            _state["paused_at"] = None
    return status()


def active() -> bool:
    return bool(_state.get("active"))


def now() -> datetime:
    """Simulated time when replaying, real IST time otherwise."""
    with _lock:
        if not _state.get("active"):
            return datetime.now(IST)
        ref = _state["paused_at"] or _time.time()
        sim = _state["sim_start"] + timedelta(seconds=(ref - _state["real_start"]) * _state["speed"])
        end = datetime.combine(_state["day"], time(15, 35), IST)
        return min(sim, end)


def finished() -> bool:
    return active() and now() >= datetime.combine(_state["day"], time(15, 35), IST)


def cut(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Keep only bars fully closed at the simulated time (no peeking at the future)."""
    if not active() or df is None or df.empty:
        return df
    t = now()
    if interval == "1d":
        return df[df.index.date < t.date()]
    minutes = {"1m": 1, "5m": 5, "15m": 15}[interval]
    return df[df.index + pd.Timedelta(minutes=minutes) <= t]


def status() -> dict:
    if not active():
        return {"active": False}
    t = now()
    return {"active": True, "day": _state["day"].isoformat(), "speed": _state["speed"],
            "sim_time": t.isoformat(timespec="seconds"), "paused": _state["paused_at"] is not None,
            "finished": t >= datetime.combine(_state["day"], time(15, 35), IST)}
