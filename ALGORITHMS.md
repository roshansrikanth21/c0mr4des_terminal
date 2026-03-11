## AI Market Analyser – Algorithms & Models

This document catalogs the main indicators, quant/statistical models, options logic and risk management rules implemented in the system, and how they contribute to trading decisions.

---

## 1. Technical Indicators & Price‑Based Features

Most classical technical indicators are implemented in `backend/market_data.py` and consumed by higher‑level systems such as `MomentumTradingSystem` and the intraday engines.

- **Simple Moving Average (SMA)**
  - Used for trend detection and moving‑average crossovers (e.g. 50/200 MA).
  - Higher SMAs (e.g. 200‑day) characterize long‑term trend; shorter SMAs help detect recent shifts.
- **Exponential Moving Average (EMA)**
  - Used in MACD and sometimes as a smoother alternative to SMA.
  - Reacts faster to recent price changes, useful for timely entries and exits.
- **Relative Strength Index (RSI)**
  - Momentum oscillator (commonly 9 or 14 periods).
  - Overbought/oversold regions help identify pullbacks in a trend and reversals.
- **Moving Average Convergence Divergence (MACD)**
  - Trend‑following momentum indicator based on the difference of two EMAs and a signal line.
  - Crossovers and divergences are used as part of momentum scoring.
- **Bollinger Bands**
  - 20‑period moving average with ±2 standard deviation bands.
  - Used to gauge volatility and spot squeezes/breakouts or mean‑reversion zones.
- **Average True Range (ATR)**
  - Measures volatility via true range (high/low and gaps).
  - Central to stop‑loss and target placement (e.g. 2×ATR stop, 3×ATR target) and in intraday exit logic.
- **Average Directional Index (ADX)**
  - Measures trend strength independent of direction.
  - Helps distinguish between trending and ranging markets, influencing whether trend‑following or mean‑reversion tactics are favored.
- **Volume‑Weighted Average Price (VWAP)**
  - Implemented in `backend/intraday_utils.py` and used in `backend/backtest.py`.
  - Serves as a key intraday reference level; pullbacks or rejections around VWAP are central to scalping and intraday entries.

These indicators are combined into composite scores (especially in `MomentumTradingSystem`) rather than being traded in isolation.

---

## 2. Momentum & Trend Models

### 2.1 MomentumTradingSystem (`backend/momentum_trading.py`)

- **Moving‑average crossover**:
  - Classical MA crossover (e.g. 50 crossing above or below 200).
  - Defines bullish vs bearish regimes for trend‑following entries.
- **Momentum scoring**:
  - Aggregates:
    - Slope of moving averages.
    - Recent returns and rate of change.
    - Basic Sharpe‑like metrics on recent windows.
  - Returns an **action** (BUY/SELL/HOLD) and a **confidence score**.
- **Options strategy suggestions**:
  - Given a bullish momentum context, it prefers call‑side structures (e.g. bull call spreads).
  - In bearish conditions, it prefers put‑side structures (e.g. bear put spreads).

The output of this module is a key input to the integrated decision engine’s `_aggregate_signals` method.

---

## 3. Regime Detection & Volatility Models

### 3.1 MarketRegimeDetector (`backend/regime_detection.py`)

- Uses macro/market variables such as:
  - Equity index returns (e.g. Nifty).
  - Volatility indices.
  - Rates/curve proxies (where available).
- Produces a **primary regime label** and **confidence**:
  - `RISK_ON`, `RISK_OFF`, `EXPANSIONARY`, `RECESSIONARY`, `NEUTRAL`.
- These regimes directly alter the **BUY/SELL/HOLD scores** in the integrated engine:
  - `RISK_ON` / `EXPANSIONARY` → bias towards BUY.
  - `RISK_OFF` / `RECESSIONARY` → bias towards SELL.
  - `NEUTRAL` → contributes towards HOLD.

### 3.2 MarkovRegimeSwitching (`backend/regime_detection.py`)

- Fits a **Markov regime‑switching** model on returns.
- Captures volatility clustering by modeling returns as coming from multiple latent states with different volatilities.
- Used for:
  - Diagnosing when the market is in a low, normal, or high‑volatility state.
  - Informing volatility‑aware sizing and risk controls.

### 3.3 Volatility Models (`backend/volatility_position_sizing.py`, `backend/quant_engine.py`)

- **Realized volatility**:
  - Estimated from recent returns to drive position sizing.
- **Target volatility**:
  - The system aims for a fixed target portfolio volatility and caps per‑position volatility.
- **GARCH/SARIMA** (in `backend/time_series_forecast.py`):
  - Used to forecast volatility and intraday patterns where enabled.

---

## 4. Mean‑Reversion & Market Structure

### 4.1 Ornstein–Uhlenbeck (OU) Model (`backend/ornstein_uhlenbeck.py`)

- Models price/returns as a **mean‑reverting stochastic process**:
  - Parameters estimated via maximum likelihood.
  - Computes **z‑scores** of current price relative to the mean and volatility.
- Signals:
  - If z‑score is deeply negative (e.g. \( z < -1.5 \)) → **LONG** mean‑reversion.
  - If z‑score is high positive (e.g. \( z > 1.5 \)) → **SHORT** mean‑reversion.
- Also provides:
  - Half‑life estimates for mean reversion.
  - Monte‑Carlo path simulations for stress testing.

The OU signals are a third leg of the integrated engine (alongside momentum and regime).

### 4.2 Minimum Spanning Tree (MST) & Correlations (`backend/mst_analysis.py`)

- Builds a **correlation matrix** of Nifty 50 (and related) stocks.
- Converts correlations \(\rho\) to distances \( d = \sqrt{2(1-\rho)} \).
- Runs a **Minimum Spanning Tree** to identify key structural links and cluster leaders.
- Supports:
  - Pairs trading ideas.
  - Diversification across highly/lowly correlated clusters.

---

## 5. Advanced Quant Engine & Bayesian Layer

### 5.1 QuantEngine (`backend/quant_engine.py`)

- **Wasserstein distance**:
  - Compares recent return distributions to historical baselines.
  - Large distances indicate regime shifts or structural breaks.
- **Entropy measures**:
  - Histogram‑based entropy of returns.
  - Lower entropy → more predictable and structured; higher entropy → noisy/uncertain.
- **Monte‑Carlo risk**:
  - Simulates return paths for Value‑at‑Risk (VaR) and drawdown analysis.

These metrics feed into institutional‑style diagnostics and the frontend institutional cards.

### 5.2 Bayesian Inference & Kelly (`backend/bayesian_inference.py`)

- **Bayesian win‑rate estimation**:
  - Models strategy win‑rate \( p \) with a Beta prior/posterior.
  - Updates as new trade outcomes arrive.
- **Credible intervals & risk**:
  - Computes credible intervals for \( p \) to represent uncertainty.
- **Kelly fraction**:
  - Uses the Bayesian posterior to estimate a **Kelly‑optimal allocation**.
  - Informs how aggressively to size strategies given uncertainty in their edge.

---

## 6. Options & Derivatives Logic

### 6.1 Options Indicators (`backend/options_indicators.py`)

- **Black–Scholes Greeks**:
  - **Delta, Gamma, Theta, Vega** for calls and puts.
  - Used to understand directional, convexity and time‑decay exposure of candidate options trades.
- **Moneyness & selection**:
  - Functions to detect in‑the‑money (ITM), at‑the‑money (ATM) and out‑of‑the‑money (OTM) options.
  - Helps pick strikes for spreads that balance risk and reward.

### 6.2 Order Flow & Market Profile (`backend/order_flow.py`)

- **VPOC (Volume Point of Control)**:
  - Price level with maximum traded volume.
  - Acts as a magnet and reference for mean‑reversion and breakout plays.
- **Value Area (VAH/VAL)**:
  - Range where a large proportion of volume occurs.
  - Entries/exits are evaluated relative to value area boundaries.
- **Support & resistance**:
  - Swing highs/lows and rejection zones around high‑volume nodes.
  - Combined with volume and candle patterns for confirmation.

### 6.2.1 Institutional Order Flow (`backend/institutional_order_flow.py`)

- **Order book imbalance & delta**:
  - Uses broker Level 2 data (bid/ask depth) from the shared market data service to compute:
    - Bid/ask volume imbalance.
    - Order‑flow delta (volume at bid − volume at ask) and its change over time.
  - Classifies phases as `BUYING`, `SELLING`, `STRONG_BUYING`, `STRONG_SELLING`.
- **Large orders & absorption**:
  - Detects large orders (₹10L+ by notional) on bid/ask as institutional footprints.
  - Identifies **absorption** when large orders are filled without much price movement, highlighting strong support/resistance levels.
- **Momentum shifts in flow**:
  - Tracks recent deltas to detect when order flow flips from net selling to buying (and vice versa).
  - Generates BUY/SELL/HOLD style signals with confidence that are consumed by `OrderFlowAnalyzer.get_enhanced_entry_recommendation` and the advanced intraday system when broker data is available.

### 6.3 ICT / Smart Money Concepts (`backend/ict_smart_money.py`)

- **Fair Value Gaps (FVGs)**:
  - Three‑candle patterns where the middle candle leaves a gap between previous and next candle’s extremes.
  - Bullish FVGs → potential demand zones; bearish FVGs → potential supply zones.
- **Order Blocks**:
  - Last opposite candle before a strong impulse move.
  - Mark and track buy/sell zones where large players likely entered.

These concepts are used mainly in the **AdvancedTradingSystem** to refine intraday entries and stops.

---

## 7. Risk Management & Position Sizing

### 7.1 VolatilityPositionSizer (`backend/volatility_position_sizing.py`)

- **Inputs**:
  - Account capital (e.g. ₹1,000,000).
  - Realized volatility of the instrument.
- **Logic**:
  - Targets a fixed **portfolio volatility** (e.g. 15% annualized).
  - Caps **per‑position volatility** (e.g. 2%).
  - Computes a position value and number of contracts/shares such that:
    - Higher volatility → smaller size.
    - Lower volatility → larger size (within caps).

### 7.2 ExitSystem (`backend/exit_system.py`)

- **ATR‑based stops and targets**:
  - Stop loss and take profit are set as multiples of ATR (e.g. stop at 1.8×ATR, target at 2.2×ATR for some configs).
- **Trailing stops**:
  - Trailing ATR‑based logic moves stops in the trade’s favor as price advances.
- **Partial profit‑taking**:
  - For example, taking 30% off at 15% profit, another 30% at 25% profit, and letting the remainder run with a trail.
- **Time‑based exits**:
  - Uses **theta decay** and **option expiry proximity** to close positions when time risk dominates.
  - Also exits near market close to avoid overnight risk in intraday systems.
- **IV‑based exits**:
  - Exits when implied volatility collapses after an event (IV crush) or spikes unreasonably without matching price action.

These rules ensure trades are exited **systematically** rather than emotionally.

---

## 8. Integrated Decision Logic

### 8.1 IntegratedTradingDecisionEngine (`backend/trading_decision_engine.py`)

- **Inputs**:
  - Momentum trading plan (action + confidence).
  - Market regime (primary label + confidence).
  - OU signals (LONG/SHORT with confidence).
  - Realized volatility.
- **Weights in `_aggregate_signals`**:
  - Momentum: **0.4**
  - Regime: **0.3**
  - OU: **0.3**
- **Scoring**:
  - Maintains `scores = {'BUY', 'SELL', 'HOLD'}`.
  - Adds weighted confidence from each module to the relevant action.
  - Final action is the `argmax` over scores, and the confidence is that score.
- **Trading plan**:
  - Uses `VolatilityPositionSizer` for position sizing.
  - Uses ATR for stop and target placement.
  - Chooses **Bull Call Spread** or **Bear Put Spread** according to BUY/SELL.

This engine is responsible for **swing‑style, higher‑timeframe decisions**.

### 8.2 AdvancedTradingSystem (`backend/advanced_analysis.py`)

- **Components**:
  - Order flow and market profile around VWAP, VPOC and value area.
  - ICT structures (FVGs, Order Blocks).
  - Nifty/Bank Nifty specific timing and ORB logic.
- **Confluence logic**:
  - Assigns weights to:
    - Order flow (e.g. ~45%).
    - ORB/timing (e.g. ~25%).
    - Additional timing/session context (e.g. ~20%).
  - Requires:
    - Confluence score above a minimum threshold (e.g. ≥ 0.4).
    - Alignment with ICT zones and broader regime context.
- **Outcome**:
  - Produces **high‑conviction intraday entries** in index options with a full plan (entry, stops, targets, contract selection).

Together, these engines and modules form a **multi‑layered quant + discretionary‑style system** that looks at regime, momentum, mean reversion, smart‑money levels, volatility and risk in an integrated way.

---

## 9. Market Data Providers & Infrastructure

### 9.1 AsyncMarketDataService (`backend/services/market_data_service.py`)

- **Provider orchestration**:
  - `AsyncMarketDataService` maintains an ordered list of providers:
    - Broker providers (if configured) from `backend/services/broker_data_providers.py`:
      - `AngelOneDataProvider` (SmartAPI).
      - `ZerodhaKiteProvider` (Kite Connect).
      - `GrowwDataProvider` (placeholder).
    - Fallback providers:
      - `YahooFinanceProvider` (yfinance).
      - `AlphaVantageProvider` (requires API key).
      - `SyntheticDataProvider` (testing only).
  - Applies basic validation of OHLCV data (columns, monotonic price ranges, positive closes, minimum length).
- **Caching & sync wrapper**:
  - Caches responses for a short TTL (e.g. 5 minutes) to reduce external calls.
  - Exposes `get_market_data` (async) and `get_sync_market_data` (sync wrapper) used by `market_data`, the integrated trading engine, the advanced intraday system, and the backtester.

### 9.2 Broker Data Providers (`backend/services/broker_data_providers.py`)

- **Angel One SmartAPI (`AngelOneDataProvider`)**:
  - Uses SmartAPI to fetch candles via `getCandleData` with interval mapping (`ONE_MINUTE`, `FIVE_MINUTE`, etc.).
  - Standardizes output to `Open/High/Low/Close/Volume` with a datetime index.
  - Supports Level 2 order book via `marketData`, which powers institutional flow analysis.
- **Zerodha Kite Connect (`ZerodhaKiteProvider`)**:
  - Uses `historical_data` for OHLCV with interval mapping (`minute`, `5minute`, `15minute`, etc.).
  - Uses `quote` with depth to get Level 2 order book and option chain information for NFO instruments.
- **Groww (`GrowwDataProvider`)**:
  - Placeholder that raises a clear error until Groww exposes a public API; the architecture is ready for future integration.

