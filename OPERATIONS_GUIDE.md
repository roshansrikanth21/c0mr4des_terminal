# C0MR4DE TERMINAL Guide

## What This System Is

C0MR4DE TERMINAL is a multi-engine market analysis and signal platform. It combines:

- live/persistent market data
- market-structure logic
- ML-based directional confirmation
- news impact scoring
- news event-study calibration
- Monte Carlo and quant risk analysis
- chart-image analysis
- walk-forward backtesting
- live signal tracking
- EA/MT bridge export

It is not a single model. It is a coordinated system.

## Memory Layer

Primary file:

- [memory_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/memory_service.py)

Purpose:

- persist typed long-term memory locally under `data/memory`
- optionally sync memory writes to Supermemory
- retrieve only scoped memories relevant to the current ticker, interval, regime, session, and setup
- attach advisory memory influence to fusion decisions

Memory types:

- `market`
- `strategy`
- `execution`
- `operator`
- `news`

Each memory item carries:

- `confidence`
- `sample_count`
- `freshness_score`
- `trust_score`
- `trust_tier`
- `drift_score`
- `validation_state`
- `validation_count`
- `expires_at`
- `last_validated_at`
- `ticker`
- `interval`
- `regime`
- `session_bucket`
- `setup_family`

Current write sources:

- regime shifts
- high-impact news
- approved pattern-governor artifacts
- settled live signals

Memory maintenance:

- stale low-trust memories are pruned automatically
- drifted memories are downranked in retrieval and fusion influence
- settled live signals now validate matching strategy memories automatically
- realized execution feedback now validates matching execution memories automatically
- matured event-study outcomes now validate matching news memories automatically

Important:

- memory is advisory, not authoritative
- memory can bias weights and explain context
- memory does not bypass risk vetoes or execution gating

## Core Architecture

### Data Layer

Primary files:

- [market_data_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/market_data_service.py)
- [historical_data_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/historical_data_service.py)
- [main.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/main.py)

Responsibilities:

- fetch market data from broker providers and fallbacks
- cache and deduplicate requests
- persist historical OHLCV data under `data/historical`
- provide quality-aware access to price series

Provider order:

1. TrueData / broker providers when available
2. Yahoo Finance fallback
3. Alpha Vantage backup
4. Synthetic data only as last resort or explicit fallback paths

### Intelligence Layer

Primary files:

- [decision_fusion_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/decision_fusion_service.py)
- [pattern_learning_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/pattern_learning_service.py)
- [news_ml_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/news_ml_service.py)
- [news_event_study_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/news_event_study_service.py)
- [chart_pattern_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/chart_pattern_service.py)
- [data_quality_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/data_quality_service.py)

Responsibilities:

- structure signals: FVG, IFVG, order blocks, sweeps
- ML confirmation
- regime analysis
- quant analysis
- news impact and calibration
- scoped memory retrieval and influence
- data-quality penalty/veto
- final action/risk sizing

### Evaluation Layer

Primary files:

- [backtest_walkforward.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/backtest_walkforward.py)
- [backtest.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/backtest.py)
- [fusion_model_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/fusion_model_service.py)
- [training_data_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/training_data_service.py)
- [live_signal_tracker_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/live_signal_tracker_service.py)

Responsibilities:

- build datasets
- train fusion model
- run walk-forward validation
- run legacy heuristic sim
- track real live/exported signal outcomes

### Interface Layer

Primary files:

- [Dashboard.tsx](/k:/ai-market-analyser-main/ai-market-analyser-main/src/pages/Dashboard.tsx)
- [Backtest.tsx](/k:/ai-market-analyser-main/ai-market-analyser-main/src/pages/Backtest.tsx)
- [ScanDialog.tsx](/k:/ai-market-analyser-main/ai-market-analyser-main/src/components/ScanDialog.tsx)
- [SystemMonitor.tsx](/k:/ai-market-analyser-main/ai-market-analyser-main/src/components/analytics/SystemMonitor.tsx)

Responsibilities:

- display market intelligence
- expose validation/training tools
- run chart analysis
- surface deep system health

## Models Used

### Fusion Direction Model

File:

- [fusion_model_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/fusion_model_service.py)

Model:

- `GradientBoostingClassifier`
- wrapped in `CalibratedClassifierCV`

Purpose:

- produces calibrated directional probability
- used as ML confirmation inside fusion
- combined with scoped memory, but memory remains a secondary advisory input

Input features:

- returns
- volatility
- SMA distance/trend
- RSI
- ATR normalized
- MACD
- volume z-score
- calibrated news features

### Walk-Forward Validation Model

File:

- [backtest_walkforward.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/backtest_walkforward.py)

Model:

- `GradientBoostingClassifier`

Purpose:

- out-of-sample validation using rolling train/test windows
- this is the main validation path

### News Impact Model

File:

- [news_ml_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/news_ml_service.py)

Models:

- `VADER`
- `TextBlob`
- `LinearRegression`
- `XGBRegressor`

Purpose:

- generate initial `affect_rate`
- assign directional bias
- estimate severity

Important:

- this is the raw headline-impact layer
- it is now corrected by the event-study calibration layer

### News Event Study

File:

- [news_event_study_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/news_event_study_service.py)

Model type:

- empirical calibration, not a black-box ML classifier

Purpose:

- compare predicted headline impact with realized forward benchmark moves
- produce reliability and multipliers
- calibrate live news output

### Chart Analyzer

Files:

- [main.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/main.py)
- [chart_pattern_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/chart_pattern_service.py)

Models/components:

- Gemini vision models for image understanding
- deterministic OHLC structure analyzer for live overlay

Purpose:

- extract ticker/timeframe/patterns from uploaded charts
- then verify/enrich with real structure from live OHLC data

Important:

- it is no longer purely LLM vision
- deterministic overlay now acts as a second opinion

### Pattern Governor

File:

- [pattern_learning_service.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/services/pattern_learning_service.py)

Model type:

- historical pattern outcome filter

Purpose:

- keep only patterns that pass configured thresholds
- used by chart analysis and research workflow

## How The System Makes A Decision

1. Load and normalize market data.
2. Assess market-data quality.
3. Run structure strategies.
4. Compute ML confirmation features.
5. Fetch and calibrate news context.
6. Run quant and Monte Carlo risk.
7. Retrieve scoped memory context from the local memory layer.
8. Adapt fusion weights using:
   - model quality
   - live settled scorecard
   - execution quality
   - data quality
   - scoped memory hints
9. Fuse scores into one action.
10. Apply routing and execution-forecast constraints.
11. Export or display the final decision.

## Memory APIs

- `GET /api/memory/status`
- `GET /api/memory/search`
- `GET /api/memory/context`
- `GET /api/memory/research`
- `POST /api/memory/write`
- `POST /api/memory/maintenance`
- `POST /api/memory/validate`

Typical use:

1. Load `Memory Lab`
2. Set `ticker`, `interval`, optional `query`, optional `regime`, optional `setup`
3. Click `Load Context`
4. Click `Load Research`
5. Run `Maintenance` when drift or expiry accumulates
6. Inspect:
   - retrieved memories
   - alignment bias
   - risk bias
   - average trust
   - average drift
   - trust tiers
   - validation states

Interpretation:

- positive `alignment_bias` means memory context slightly favors long exposure
- negative `alignment_bias` means memory context slightly favors short exposure
- positive `risk_bias` increases caution
- high `drift_score` means the memory is aging badly against realized outcomes
- `high` trust memories carry more weight than `medium` or `low`
- stale or drifting memories should not be trusted heavily

Flow:

1. Load market data.
2. Score data quality.
3. Detect structure signals from strategy registry.
4. Run ML confirmation if trained model exists.
5. Run regime and quant diagnostics.
6. Fetch and score news.
7. Calibrate news scores using event-study artifact if available.
8. Build adaptive weights.
9. Penalize for stale/weak data and risk regime.
10. Produce final action, confidence, stop, target, and position multiplier.

Main endpoint:

- `/api/fusion/decision`

Key rule:

- weak data can now reduce or veto trades
- synthetic/news fallback states no longer deserve full weight

## How To Operate It As A User

### 1. Start The System

Run backend and frontend.

Backend should expose:

- `/api/system/status`
- `/api/system/deep_status`

Check in UI:

- `System Monitor`

You want to see:

- API online
- market providers available
- prewarm running/idle
- fusion core available

### 2. Load Market Dashboard

Open `Dashboard`.

What happens:

- frontend triggers backend prewarm
- dashboard requests intel bundle
- backend serves cached/prewarmed bundle when possible

If bundle fails:

- UI falls back to individual intel feeds

### 3. Train Pattern Governor

Open `Backtest` -> `Pattern Governor Training`.

Purpose:

- identify patterns that are historically acceptable for the chosen ticker/interval

Recommended process:

1. choose your main ticker
2. choose your real trading interval
3. set history window
4. train approved set
5. load latest after training

Interpretation:

- more samples is better than a small high win-rate artifact
- use realistic thresholds, not vanity thresholds

### 4. Train News Event Study

Open `Backtest` -> `News Event Study`.

Purpose:

- calibrate raw news scores against realized benchmark moves

Important:

- it needs matured events
- a news item is only useful for training after enough forward bars exist

If you see:

- `Not enough matured news events to train event study`

That means:

- the system has not yet accumulated enough recorded news items with enough forward market history after them
- this is expected early on

What to do:

1. let the system run longer with live news enabled
2. use a more active benchmark/interval
3. retrain later

Your screenshot shows `Samples: 9`, which means the pipeline is working but has not crossed the minimum sample threshold yet.

### 5. Use Walk-Forward Backtest

Open `Backtest` -> `Validation Profile`.

Default engine:

- `Walk-Forward`

Use this for:

- realistic validation
- train/test rolling windows
- slippage and transaction cost aware research

Legacy mode:

- quick heuristic check only

Do not use legacy sim as the main measure of system quality.

### 6. Use Chart Analyzer

Open chart scan dialog.

Flow:

1. upload chart
2. Gemini extracts chart information
3. backend parses and repairs malformed JSON if needed
4. pattern governor checks approved historical patterns
5. deterministic OHLC overlay verifies structure
6. real-time market intelligence enriches output

Debug endpoint:

- `/api/chart/deterministic_context?ticker=...&timeframe=15m`

Use this when:

- chart output looks weak
- you want to compare vision output to live OHLC logic

### 7. Export Live Signals

Endpoint:

- `/api/ea/export_signal`

Purpose:

- create normalized signal for MT4/MT5/EA bridge

What happens:

1. fusion decision is generated
2. EA signal JSON is written
3. signal is now also recorded in live signal tracker

### 8. Track Real Signal Performance

Open `Backtest` -> `Live Signal Scoreboard`.

Purpose:

- measure actual post-signal outcomes
- compare sources like `fusion_decision` and `ea_export`

Buttons:

- `Load Scoreboard`
- `Settle Open Signals`

What `Settle Open Signals` does:

- checks open signals against subsequent market data
- marks them settled if enough bars have passed

This is the next layer after backtesting.

### 9. Automatic Live Reweighting

The fusion engine now uses settled live signal outcomes as a secondary weight governor.

What it does:

- analyzes settled signals
- estimates reliability for:
  - `strategy`
  - `ml_confirmation`
  - `regime`
  - `quant`
  - `news`
- boosts modules only after enough settled samples
- reduces modules that are underperforming in live post-signal outcomes

Important:

- this is sample-gated
- it does not overreact to a handful of signals
- early in runtime, there may be no measurable adjustment yet

### 10. Execution-Aware Learning

Open `Backtest` -> `Execution Quality`.

Purpose:

- measure real fill quality instead of only post-signal direction
- track broker rejects and pending orders
- track realized slippage against expected entry
- track fill ratio and time-to-fill
- reduce live aggressiveness when execution quality degrades

Data sources:

- manual broker orders via `/api/broker/order`
- strategy-driven executions inside `ExecutionEngine`
- EA feedback via `/api/ea/execution_feedback`

What happens:

1. every order attempt is stored in `data/execution_quality`
2. the service computes fill rate, reject rate, average slippage, latency, fill ratio, time-to-fill, and quality score
3. the fusion engine reads that score during decision generation
4. if execution quality is poor, confidence and risk budget are reduced
5. if execution quality becomes very poor, trading can be vetoed even if the signal is otherwise strong

Important:

- this is not a replacement for broker-side risk checks
- it is a runtime throttle so the system respects real execution friction
- if you only export signals and never send execution feedback, this section will stay sparse

### 11. Pre-Trade Execution Forecast

Open `Backtest` -> `Execution Quality` -> `Load Forecast`.

Purpose:

- estimate execution friction before the order is sent
- predict likely slippage, reject rate, and latency
- predict likely fill ratio and time-to-fill
- reduce strategy size before routing the order if execution conditions are weak

What it uses:

- historical execution records in `data/execution_quality`
- current symbol
- side (`BUY` or `SELL`)
- broker
- session bucket (`open`, `midday`, `close`, `offhours`)

What it does:

1. searches for the best matching execution history slice
2. computes expected slippage, reject rate, latency, fill ratio, time-to-fill, and quality score
3. blends those heuristics with broker/session execution models when enough history exists
3. produces a `risk_multiplier`
4. strategy execution uses that multiplier to scale quantity down before order placement
5. if the forecast is bad enough and sample count is strong enough, strategy execution skips the order

This is distinct from the post-trade `Execution Quality` summary:

- forecast = before the order
- execution quality = after the order

### 12. Broker And Provider Routing

Open:

- `Backtest` -> `Execution Quality` -> `Load Routing`
- `Live Ops`
- `System Monitor`

Purpose:

- rank execution brokers from live execution evidence
- rank market-data providers from current health and fallback state
- prevent the system from trusting a degraded path just because it is configured

What it does:

1. scores execution brokers using:
   - live reject rate
   - realized slippage
   - average fill ratio
   - average time-to-fill
   - execution quality score
   - availability/credentials
2. scores market-data providers using:
   - provider priority
   - cooldown state
   - recent failure count
   - connection status where applicable
3. exposes recommended execution and data routes
4. execution engine can:
   - proceed
   - reduce size
   - halt if current broker route is degraded enough

Important:

- this is currently conservative
- it prefers halting or reducing size over silently rerouting live execution into a different broker
- data routing is automatic through provider fallback logic
- execution routing is now controllable from `Live Ops`
- automatic broker switching only happens when:
  - manual safety lock is enabled
  - auto switch is enabled
  - routing recommends a stronger alternate broker

### 13. Live Ops Control Surface

Open:

- `Live Ops`

Purpose:

- arm or disarm live safety controls
- switch brokers manually
- inspect routing recommendations
- inspect pre-trade execution forecast
- export EA signals
- send execution feedback back into the learning loop

Main controls:

1. `Safety Lock`
2. `Auto Switch`
3. `Preferred Live Broker`
4. `Switch Broker`
5. `Apply Recommended Route`
6. `Export Signal`
7. `Submit Feedback`

How it works:

1. `Safety Lock` is the first gate.
2. `Auto Switch` does nothing unless the safety lock is armed.
3. `Apply Recommended Route` attempts a safe broker switch through `/api/routing/apply`.
4. `Export Signal` writes the latest EA payload and records the signal in the tracker.
5. `Submit Feedback` pushes fill outcome, latency, and quantity back into:
   - live signal tracker
   - execution quality tracker
   - EA feedback store

Recommended use:

1. keep `Auto Switch` off until broker runtime is stable
2. use `Paper` until execution quality and routing evidence look sane
3. only arm safety lock when you are intentionally allowing live route changes
4. use `Rebuild Models` after importing a batch of execution feedback so forecast confidence updates immediately

### 14. Broker-Specific Execution Models

Open:

- `Live Ops` -> `Execution Models`

Purpose:

- convert raw execution logs into reusable broker/session/order-type profiles
- make execution forecast rely on real broker behavior instead of only global averages

What a model represents:

- broker
- order type
- optionally symbol
- optionally session bucket
- enough samples to be statistically usable

What it influences:

- forecast basis
- forecast confidence
- expected slippage
- expected reject rate
- expected fill ratio
- expected time-to-fill

Important:

- no model is trusted without enough samples
- low-sample global fallback still exists
- this is evidence-weighted, not blind auto-learning

## How To Operate It As A Developer

### Main Backend Entry

File:

- [main.py](/k:/ai-market-analyser-main/ai-market-analyser-main/backend/main.py)

This wires:

- API routes
- startup prewarm
- chart analyzer
- fusion APIs
- backtest APIs
- signal tracking APIs

### Important API Endpoints

System:

- `GET /api/system/status`
- `GET /api/system/deep_status`
- `POST /api/system/prewarm`

Fusion:

- `POST /api/fusion/decision`
- `GET /api/fusion/status`

Backtesting:

- `POST /api/backtest/walkforward`
- `POST /api/backtest`
- `POST /api/data/backfill`
- `GET /api/data/quality`

Pattern learning:

- `POST /api/patterns/train`
- `GET /api/patterns/approved`

News calibration:

- `GET /api/news/impact`
- `POST /api/news/event_study/train`
- `GET /api/news/event_study/latest`

Chart analysis:

- `POST /api/analyze`
- `GET /api/chart/deterministic_context`

Signal tracking:

- `GET /api/signals/performance`
- `POST /api/signals/settle`
- `POST /api/ea/export_signal`
- `POST /api/ea/execution_feedback`

Execution quality:

- `GET /api/execution/quality`
- `GET /api/execution/forecast`
- `GET /api/execution/models`
- `POST /api/execution/models/rebuild`

Routing:

- `GET /api/routing/status`
- `POST /api/routing/apply`

Ops control:

- `GET /api/ops/config`
- `POST /api/ops/config`

### Stored Artifacts

Historical data:

- `data/historical`

Pattern governor:

- `data/pattern_quality`

Training datasets:

- `data/training`

News event study:

- `data/news_event_study`

EA signals:

- `data/ea_signals`

Live signal tracker:

- `data/signal_tracker`

Execution quality:

- `data/execution_quality`

### Caches And Warm Paths

Main caches:

- dashboard analysis cache
- intel bundle cache
- market data provider cache
- news cache

Warm flow:

1. startup prewarms common tickers
2. dashboard also triggers ticker-specific prewarm
3. deep status exposes warm state
4. frontend routes are lazy-loaded, so non-active pages do not block initial startup

### How To Extend It Safely

If adding a new module:

1. make it observable
2. make it degrade gracefully
3. do not give it full fusion weight by default
4. add dataset/backtest path before trusting it live
5. add it to signal tracking if it produces actions

## Recommended Daily Workflow

1. Start backend and frontend.
2. Check `System Monitor`.
3. Open dashboard for target ticker.
4. Train/load pattern governor artifact.
5. Train/load news event-study artifact if enough samples exist.
6. Run walk-forward validation for your target ticker/interval.
7. Use chart analyzer for discretionary confirmation.
8. Export live signal only when fusion, structure, and risk are aligned.
9. Periodically settle and review live signal scoreboard.
10. Review `Execution Quality` before increasing size or switching to live broker mode.
11. Review routing snapshot if broker rejects rise or data quality feels inconsistent.
12. Use `Live Ops` to arm safety lock, inspect route recommendations, and manage EA export/feedback when preparing live execution.

## What To Trust Most

Order of trust:

1. walk-forward validation
2. live signal scoreboard
3. execution quality
4. deterministic structure overlay
5. fusion decision with calibrated news
6. legacy backtest
7. raw chart-vision output alone

## Current Limitations

- early event-study training may fail due to insufficient matured events
- chart vision still depends on Gemini quality and API availability
- some repo-wide Pydantic warnings remain outside the core paths
- legacy sim still exists for comparison but should not drive deployment decisions

## Immediate Next Best Improvement

Execution-path learning with broker-specific fill-behavior modeling.

That means:

- track time-to-fill and partial-fill behavior more granularly
- distinguish market-open execution from midday/close more precisely
- add broker-specific execution models beyond the current heuristic scorer
- feed predicted execution drag directly into fusion notional risk sizing before order generation

The current implementation already forecasts and gates execution paths using fill ratio and time-to-fill. The next layer is making that forecast more granular and broker-specific.
