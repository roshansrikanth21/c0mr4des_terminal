# C0MR4DE Terminal

Intraday decision support for **NIFTY 50 and SENSEX index options**. It reads live candles,
understands candle structure, patterns, market structure, trend, time of day and expiry, scans
news and social feeds for anything that moves Indian indices, and ends with one word:

- **BUY**: buy a Call (CE)
- **SELL**: buy a Put (PE)
- **NO TRADE**: the evidence is mixed or the setup isn't there; it still shows which way it leans

Every conclusion comes with the reasons in plain English, a trade plan (strike, premium stop and target,
index stop and target, lots sized to your risk) and the reasons it would refuse to trade.

> Decision support. Real orders stay off unless you set `LIVE_TRADING=true`, and even then it is one
> confirmed click per order, with a server-side re-check of your caps. You manage the exit.

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

## 2-year evidence (what the live autopilot trades)

Tested on real hourly NIFTY/SENSEX bars, Nov 2023 to Oct 2026, 1 lot. Option premiums are modelled from real index moves, real India VIX and real time to expiry (theta included), with slippage and full charges.

**The live First-Hour and First-30 rules skip expiry days** (since 25 Oct), so the number that applies
to the First-Hour is the "excluding expiry days" one: **PF 1.15, +₹65k** — roughly break-even. The 1.41
below is the same rule *trading* expiry days, where ~70% of the modelled profit came from premiums we
trust least.

| Strategy | NIFTY | SENSEX |
|---|---|---|
| **First-hour breakout, 2R** (main) | 549 trades, 44% won, PF 1.41, **+₹2.07L**, 11/13 quarters up | PF 1.32, +₹1.71L, 12/13 quarters up |
| — same, excluding expiry days | PF 1.15, +₹65k | — |
| First-hour direction (the First-30 idea at 1 hour) | PF 1.11, +₹66k, drawdown −₹85k | PF 1.17 |
| 5 EMA (Power of Stocks), 60 days | sell-only PF 1.26, both sides PF 0.98 | sell-only PF 1.13 |
| TJR sweep → BOS → FVG, 60 days | 14 trades, PF 1.68 | PF 0.29 (loses) |

Caveat: about 70% of the first-hour profit came on expiry days, where modelled premiums are least reliable. Without expiry days NIFTY is PF 1.15 (+₹65k). With ₹10k, one lot is ~70% of the account and the worst historical drawdown (−₹28.7k) is about 3x the account.

Shock days (NIFTY daily 2008-2026): after India VIX jumps 15%+ in a day, NIFTY rose the next day 60% of the time. After −3% days it was higher 20 days later 64% of the time. The app shows a Shock-mode playbook on those days.

## Live test checklist (prototype)

1. Rotate your Angel One credentials (the old ones leaked), then put the NEW ones in `backend/.env` (see `.env.example`).
   Without them everything still works on Yahoo's delayed data.
2. Run `start.bat` before 09:15. Leave it running all session.
3. The **Autopilot** paper-trades each enabled strategy separately, at live prices, with all charges:
   - **First-Hour** (main): first 5-minute close outside the 09:15-**10:15** range, with yesterday's close as a filter (1/day)
   - **First-30**: your rule. The first 30 minutes went up = BUY, down = SELL, stop at mid-range, hold to 15:15 (1/day)
   - **Engine**: the full candle/structure/trend/news model (up to 2 trades/day). **Off by default** — weakest
     backtest and it lost its first two live trades. Turn it back on in Settings.
4. After 15:30 open **Trade Journal** for each trade (entry, exit, why, charges, P&L) and the per-strategy scoreboard.
5. Real orders stay off unless you set `LIVE_TRADING=true`. Even then, it's one confirmed click per order and you manage exits.

Strategy lab (real 5m data, Jul to Oct 2026, 1 lot, modelled option premiums plus costs):

| Strategy | NIFTY net / win% | SENSEX net / win% |
|---|---|---|
| Opening Range breakout + prev-close filter | +₹53.4k / 56% | +₹30.3k / 46% |
| First-30 direction, stop at mid-range | +₹48.5k / 31% | +₹57.3k / 31% |
| First-30 direction, stop at range | +₹35.4k / 39% | +₹44.5k / 40% |
| Engine | +₹5.6k / 42% | +₹5.1k / 41% |
| Engine, SELL-only | +₹0.9k / 38% | - |

Most of the profit came in the falling Sep-Oct half, and sells carried it. Treat these rules as on probation.

## Layout

```
backend/app.py          FastAPI: /api/signal, /api/candles, /api/news, /api/global, /api/backtest, /ws
backend/engine/         config, data, indicators, candles, structure, timeline, options, news, macro, signal, backtest
backend/tests/          offline tests (pytest)
src/                    React UI: Dashboard, News Radar, Backtest, Signal Log, Risk Settings
```
