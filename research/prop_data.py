"""Free history for the markets a prop-firm (CFD) account trades: forex majors, gold, US indices.

Source: HistData.com free one-minute bars (bid, fixed EST = UTC-5), one zip per year, one per month for the
current year. Converted to UTC and resampled to hourly bars.
Writes data/prop_cache.pkl: {symbol: DataFrame[open, high, low, close] indexed by UTC hour}.
"""
import http.cookiejar
import io
import pickle
import re
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "prop_hd"
CACHE = ROOT / "data" / "prop_cache.pkl"

SYMBOLS = {"EURUSD": "eurusd", "GBPUSD": "gbpusd", "USDJPY": "usdjpy", "AUDUSD": "audusd", "XAUUSD": "xauusd",
           "US500": "spxusd", "NAS100": "nsxusd"}
YEARS = range(2020, 2026)
THIS_YEAR, MONTHS = 2026, range(1, 12)
UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes"


def fetch(pair, year, month=None):
    f = RAW / (f"{pair}_{year}.zip" if month is None else f"{pair}_{year}_{month:02d}.zip")
    if f.exists() and f.stat().st_size > 1000:
        return f
    page = f"{BASE}/{pair}/{year}" + (f"/{month}" if month else "")
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    for attempt in range(3):
        try:
            html = op.open(urllib.request.Request(page, headers=UA), timeout=40).read().decode("utf-8", "ignore")
            form = {k: re.search(rf'id="{k}" value="([^"]*)"', html).group(1)
                    for k in ("tk", "date", "datemonth", "platform", "timeframe", "fxpair")}
            body = op.open(urllib.request.Request("https://www.histdata.com/get.php", data=urllib.parse.urlencode(form).encode(),
                                                  headers={**UA, "Referer": page}), timeout=180).read()
            if body[:2] == b"PK":
                f.write_bytes(body)
                time.sleep(1)
                return f
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 * (attempt + 1))
    return None


def read(f):
    z = zipfile.ZipFile(f)
    name = next(n for n in z.namelist() if n.endswith(".csv"))
    df = pd.read_csv(io.BytesIO(z.read(name)), sep=";", header=None, names=["t", "open", "high", "low", "close", "v"])
    df.index = pd.to_datetime(df["t"], format="%Y%m%d %H%M%S") + pd.Timedelta(hours=5)      # EST -> UTC
    return df[["open", "high", "low", "close"]]


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    out = {}
    for sym, pair in SYMBOLS.items():
        files = [fetch(pair, y) for y in YEARS] + [fetch(pair, THIS_YEAR, m) for m in MONTHS]
        m1 = pd.concat([read(f) for f in files if f]).sort_index()
        m1 = m1[~m1.index.duplicated()]
        h = m1.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        out[sym] = h
        print(f"{sym:7s} files {sum(f is not None for f in files)}/{len(files)}  {len(m1):8d} minutes -> {len(h):6d} hours  "
              f"{h.index[0]} .. {h.index[-1]}  last {h['close'].iloc[-1]}", flush=True)
    pickle.dump(out, open(CACHE, "wb"))
