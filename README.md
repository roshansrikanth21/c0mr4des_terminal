# C0MR4DE Terminal

Intraday decision support for **NIFTY 50 and SENSEX index options**. It reads live candles,
understands candle structure, patterns, market structure, trend, time of day and expiry, scans
news and social feeds for anything that moves Indian indices, and ends with one word:

- **BUY**: buy a Call (CE)
- **SELL**: buy a Put (PE)
- **NO TRADE**: the evidence is mixed or the setup isn't there; it still shows which way it leans

Every conclusion comes with the reasons in plain English, a trade plan (strike, premium stop and target,
index stop and target, lots sized to your risk) and the reasons it would refuse to trade.

> Decision support, not financial advice. It never places orders. You do.

## Run it

```bat
start.bat
```

Or by hand:

```bash
python -m venv .venv && .venv\Scripts\pip install -r backend\requirements.txt
.venv\Scripts\python -m uvicorn backend.app:app --port 8100
npm install && npm run dev        # http://localhost:5173
```

Data comes from **Yahoo Finance** by default, delayed by a few minutes. For real-time candles and live option
premiums and OI, copy `backend/.env.example` to `backend/.env` and add your Angel One SmartAPI keys.

## How it decides

| Factor | Weight | What it looks at |
|---|---|---|
| Trend (15m) | 2.5 | 20/50 EMA, Supertrend, ADX strength, +DI/-DI |
| Structure (5m) | 2.0 | Confirmed swings, HH/HL vs LH/LL, break of structure / change of character |
| Momentum (5m) | 1.5 | Wilder RSI, 9/21 EMA, regression slope and its R² |
| Candles | 1.5 | 18 patterns, counted only with the right prior trend and boosted at support/resistance |
| Levels | 1.0 | Previous day H/L/C, CPR, 15-min opening range, swing zones, round numbers |
| News | 0.75 | Keyword-scored headlines with recency decay; social posts weighted at 40% |
| Global cues | 0.5 | S&P/Nasdaq futures, Nikkei, Hang Seng, Brent, USD/INR, DXY, US 10Y, gold |

**Gates (anything here forces NO TRADE):** outside 09:30–15:00, score below threshold (stricter at midday and on expiry afternoon), trading against the 15m trend, no trend and no breakout, no fresh trigger candle, price stretched more than 1.5 ATR from the 9 EMA, or reward:risk below 1.5.

Constants (Oct 2026): NIFTY lot 65, strike step 50, weekly expiry **Tuesday**; SENSEX lot 20, step 100,
expiry **Thursday**. When expiry falls on a holiday, it moves to the previous trading day. The 2026
holidays are in `backend/engine/config.py`. Check the lot sizes every quarter.

## Honest numbers

`/backtest` replays the exact live engine bar by bar on real 5-minute NIFTY/SENSEX data (last ~60 days):
next-bar fills, the strike the engine would pick priced with Black-Scholes from the real index move, that
day's real India VIX and time to expiry (so theta is included), 0.5% slippage per side and full charges.
Run on 27 Jul to 16 Oct 2026, 1 lot per trade, with multi-timeframe levels on:

| | Trades | Winners (profit) | Losers (loss) | Net | Profit factor |
|---|---|---|---|---|---|
| NIFTY | 46 | 18 (+₹26,191) | 28 (−₹24,181) | **+₹2,010** | 1.08 |
| SENSEX | 57 | 21 (+₹28,497) | 36 (−₹28,205) | **+₹292** | 1.01 |

Multi-timeframe highs and lows (previous week, daily swings, 1-hour swings) improved both: NIFTY went from +₹1,070
to +₹2,010, and SENSEX went from −₹8,167 to +₹292 with its drawdown roughly halved. **That is break-even, not an edge**,
and 50 trades is too few to prove anything. Watch the Signal Log in a live market before you trade size.

## Layout

```
backend/app.py          FastAPI: /api/signal, /api/candles, /api/news, /api/global, /api/backtest, /ws
backend/engine/         config, data, indicators, candles, structure, timeline, options, news, macro, signal, backtest
backend/tests/          offline tests (pytest)
src/                    React UI: Dashboard, News Radar, Backtest, Signal Log, Risk Settings
```
