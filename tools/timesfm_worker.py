#!/usr/bin/env python3
"""TimesFM forecast worker (owner's option A, 11 Nov).

Runs on the owner's PC: computes the NIFTY forecast fan with TimesFM 2.5 on the same
5-minute closes the terminal reads, and scp-pushes the result to the VM. The backend's
/api/predict uses a pushed fan when it is fresh (11 minutes) and falls back to its own
Monte Carlo whenever this worker is off - the dashboard always works, and its engine
label says which forecast ran. Nothing here decides a trade.

Setup (one time):
    .venv\\Scripts\\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    .venv\\Scripts\\python -m pip install "timesfm[torch]==2.0.2"
Config (gitignored): tools/timesfm_worker.local.json, e.g.
    {"vm_host": "20.200.217.1", "vm_user": "azureuser",
     "vm_key": "C:/Users/rosha/.ssh/c0mr4des_key.pem",
     "push_path": "/home/azureuser/timesfm_push.json", "interval_s": 300}
Run:   .venv\\Scripts\\python tools\\timesfm_worker.py            (one forecast every interval_s)
       .venv\\Scripts\\python tools\\timesfm_worker.py --once     (single cycle, for testing)
Auto-start (optional, at logon):
    schtasks /Create /TN TimesFMWorker /SC ONLOGON /TR "D:\\c0mr4des_terminal\\.venv\\Scripts\\python.exe D:\\c0mr4des_terminal\\tools\\timesfm_worker.py"
The first run downloads the ~800 MB model weights from Hugging Face once, then works offline.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.engine.config import IST, MARKET_OPEN, SQUARE_OFF_BY  # noqa: E402
from backend.engine.data import get_candles  # noqa: E402
from backend.engine.predict import minutes_left_in_session, next_trading_day  # noqa: E402
from backend.engine.timeline import is_trading_day  # noqa: E402

LOG = Path(__file__).with_name("timesfm_worker.log")
CFG_PATH = Path(__file__).with_name("timesfm_worker.local.json")
CFG = {"vm_host": "20.200.217.1", "vm_user": "azureuser",
       "vm_key": str(Path.home() / ".ssh" / "c0mr4des_key.pem"),
       "push_path": "/home/azureuser/timesfm_push.json",
       "interval_s": 300, "context_bars": 512, "min_bars": 96}
LEVELS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
SESSION_STEPS = ((SQUARE_OFF_BY.hour * 60 + SQUARE_OFF_BY.minute)
                 - (MARKET_OPEN.hour * 60 + MARKET_OPEN.minute)) // 5   # 72: 09:15 -> 15:15

_MODEL = None


def log(msg: str):
    line = f"{datetime.now(IST):%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _model():
    global _MODEL
    if _MODEL is None:
        import timesfm
        log("loading TimesFM 2.5-200M (first run downloads ~800 MB once)...")
        m = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            "google/timesfm-2.5-200m-pytorch", torch_compile=False)
        m.compile(timesfm.ForecastConfig(
            max_context=512, max_horizon=128, per_core_batch_size=1,
            use_continuous_quantile_head=True, force_flip_invariance=True,
            infer_is_positive=True, fix_quantile_crossing=True))
        _MODEL = m
        log("model ready")
    return _MODEL


def _ladder(quant, j: int) -> list[float]:
    """Quantile ladder at step j: column 0 repeats the point forecast, columns 1..9 are
    the 0.1..0.9 levels (verified against the 2.0.2 package on both trial machines)."""
    cols = [float(x) for x in quant[0][j]]
    ladder = cols[1:10]
    if len(ladder) != 9 or any(ladder[i] > ladder[i + 1] + 1e-6 for i in range(8)):
        raise ValueError(f"unexpected quantile row: {cols}")
    return ladder


def _p_above(x: float, ladder: list[float]) -> float:
    """P(price > x) read off the 0.1..0.9 quantile ladder (piecewise-linear CDF)."""
    if x <= ladder[0]:
        return 0.95
    if x >= ladder[-1]:
        return 0.05
    for i in range(8):
        a, b = ladder[i], ladder[i + 1]
        if a <= x < b:
            f = (x - a) / (b - a)
            return 1.0 - (LEVELS[i] + f * (LEVELS[i + 1] - LEVELS[i]))
    return 0.5


def _row(quant, j: int, when: datetime, spot: float) -> dict:
    lad = _ladder(quant, j)
    lerp = lambda a, b: a + (b - a) * 0.5
    return {"t": when.isoformat(),
            "q10": round(lad[0], 2), "q25": round(lerp(lad[1], lad[2]), 2),
            "median": round(lad[4], 2), "q75": round(lerp(lad[6], lad[7]), 2),
            "q90": round(lad[8], 2), "p_up": round(_p_above(spot, lad), 4)}


def _cone(last: dict) -> dict:
    return {"q10": last["q10"], "q25": last["q25"], "median": last["median"],
            "q75": last["q75"], "q90": last["q90"],
            "exp_move": round(last["q90"] - last["q10"], 2)}


def build_payload(key: str = "NIFTY") -> dict:
    df5, src5 = get_candles(key, "5m")
    if df5 is None or df5.empty:
        raise RuntimeError("no 5m candles available")
    closes = df5["close"].to_numpy(dtype=float)
    if len(closes) < CFG["min_bars"]:
        raise RuntimeError(f"only {len(closes)} 5m bars (need >= {CFG['min_bars']})")
    ctx = closes[-CFG["context_bars"]:].astype("float32")
    now = datetime.now(IST)
    spot = float(closes[-1])
    log(f"bars {len(closes)} from {src5}, spot {spot:.2f}")

    # NEXT SESSION: whole-day fan anchored at the next trading day's 09:15.
    _, qn = _model().forecast(horizon=SESSION_STEPS, inputs=[ctx])
    start = datetime.combine(next_trading_day(now), MARKET_OPEN, tzinfo=IST)
    next_rows = [_row(qn, j, start + timedelta(minutes=5 * (j + 1)), spot) for j in range(SESSION_STEPS)]
    payload = {"key": key, "engine": "TimesFM 2.5-200M (PC worker)",
               "pushed_at": now.isoformat(), "source5m": src5,
               "next": {"asof": now.isoformat(), "cone": _cone(next_rows[-1]), "fan": next_rows}}

    # TODAY: remainder-of-session fan, only while the market is open.
    if is_trading_day(now.date()):
        left = minutes_left_in_session(now)
        if left > 0:
            n = max(1, min(72, (left + 4) // 5))
            _, qt = _model().forecast(horizon=n, inputs=[ctx])
            rows = [_row(qt, j, now + timedelta(minutes=5 * (j + 1)), spot) for j in range(n)]
            session = df5[df5.index.date == now.date()]
            day_open = float(session["open"].iloc[0]) if not session.empty else spot
            lad = _ladder(qt, n - 1)
            payload["today"] = {"asof": now.isoformat(), "cone": _cone(rows[-1]), "fan": rows,
                                "p_close_up": {"mc": round(_p_above(day_open, lad), 4),
                                               "from_now": round(_p_above(spot, lad), 4),
                                               "day_open": round(day_open, 2)}}
            log(f"today fan {n} steps (minutes_left {left}), next fan {SESSION_STEPS} steps")
        else:
            log("market closed; pushed next-session fan only")
    else:
        log(f"{now:%a}: not a trading day; pushed next-session fan only")
    return payload


def push(payload: dict):
    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "timesfm_push.json"
        local.write_text(json.dumps(payload))
        cmd = ["scp", "-i", CFG["vm_key"], "-o", "StrictHostKeyChecking=accept-new",
               str(local), f"{CFG['vm_user']}@{CFG['vm_host']}:{CFG['push_path']}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"scp failed: {(r.stderr or '').strip()[:300]}")
    log(f"pushed to {CFG['vm_user']}@{CFG['vm_host']}:{CFG['push_path']}")


def cycle():
    payload = build_payload()
    push(payload)


def main():
    global CFG
    ap = argparse.ArgumentParser(description="TimesFM forecast worker -> VM push")
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    args = ap.parse_args()
    if CFG_PATH.exists():
        try:
            CFG.update(json.loads(CFG_PATH.read_text()))
        except Exception as e:
            log(f"config read failed ({e}); defaults in use")
    log(f"worker start (interval {CFG['interval_s']}s, host {CFG['vm_host']})")
    while True:
        t0 = time.time()
        try:
            cycle()
        except Exception:
            log("cycle failed:\n" + traceback.format_exc(limit=4))
        if args.once:
            break
        time.sleep(max(30.0, CFG["interval_s"] - (time.time() - t0)))


if __name__ == "__main__":
    main()
