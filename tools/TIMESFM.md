# TimesFM forecast (owner's option A, 11 Nov 2026)

The dashboard's forecast fan can be computed by **TimesFM 2.5** (Google's pretrained
time-series model, Apache-2.0) running **on the owner's PC**, because the VM is too
small for the model (836 MB RAM; measured 4-6 min/forecast via swap). The PC pushes
the finished fan to the VM every 5 minutes; the backend uses it when fresh and
silently falls back to its own Monte Carlo otherwise. **Nothing here decides a
trade** - the fan is the envelope, the verdict card and the entry rules are separate.

## How it works

```
PC (this repo)                                  VM (server)
tools/timesfm_worker.py                         backend/engine/predict.py
  get_candles("NIFTY","5m")  ->  TimesFM  ->  scp ~/timesfm_push.json  ->  /api/predict
                                                        fresh (< 11 min)? use it
                                                        else: Monte Carlo (always works)
```

- The pushed fan replaces: today's fan + cone + P(close up), next-session fan + cone.
- Barriers ("how often your stop/target gets touched") and key levels stay Monte
  Carlo on the VM - quantile fans cannot count barrier touches.
- The API response carries `forecast_engine` so the dashboard can show which one ran.
- When the PC is off, nothing breaks: the label reads "Monte Carlo (on this server)".

## Setup (one time, on the PC)

```
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install "timesfm[torch]==2.0.2"
```

The ~800 MB model weights download once from Hugging Face on first use, then it
works offline.

## Config (gitignored)

`tools/timesfm_worker.local.json`:

```json
{"vm_host": "20.200.217.1", "vm_user": "azureuser",
 "vm_key": "C:/Users/rosha/.ssh/c0mr4des_key.pem",
 "push_path": "/home/azureuser/timesfm_push.json", "interval_s": 300}
```

No tokens: the push rides on the same SSH key the agents already use.

## Run

```
.venv\Scripts\python tools\timesfm_worker.py            # loop: one forecast every 5 min
.venv\Scripts\python tools\timesfm_worker.py --once     # single cycle, for testing
```

Auto-start at logon (optional):

```
schtasks /Create /TN TimesFMWorker /SC ONLOGON ^
  /TR "D:\c0mr4des_terminal\.venv\Scripts\python.exe D:\c0mr4des_terminal\tools\timesfm_worker.py"
```

Log: `tools/timesfm_worker.log` (gitignored).

## Honest limits

- Yahoo 5m data on the PC is delayed ~15 min; the fan is a few minutes behind the
  live feed during market hours. The VM's own Monte Carlo uses the live feed for
  barrier odds, so the two views complement each other.
- TimesFM is a general-purpose model: it does not know about market holidays, the
  overnight gap, or expiry-day theta. Treat the fan as shape, not promise.
- The 11-minute freshness window means a stopped worker is invisible within minutes.
