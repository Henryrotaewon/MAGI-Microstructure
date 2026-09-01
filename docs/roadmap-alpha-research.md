# MAGI Microstructure — Staged Alpha Research Roadmap

## Objective

Build a modular research pipeline that detects observable abnormal/mechanical market activity, learns recurring fingerprints, measures cross-exchange propagation, and evaluates whether any signal survives executable prices, fees, spread, and slippage.

Public CEX market data cannot identify the trading account or prove self-trading/wash trading. Therefore the system stores observable evidence and predictive outcomes separately. DEX wallet-level analysis, where public addresses exist, is a separate optional sensor.

## Stage 0 — Exchange Connectivity Layer

Goal: make every venue a replaceable adapter.

Responsibilities:
- native public WebSocket streams for trades/orderbooks
- CCXT/REST metadata and fallback where appropriate
- reconnect / resubscribe / heartbeat
- rate-limit handling
- canonical symbol mapping
- connection health: CONNECTED / DEGRADED / STALE / DISCONNECTED
- last message time, reconnect count, message gaps

Rule: downstream engines must not depend on exchange-specific payload formats.

## Stage 1 — Normalized Event & Market-State Layer (v0.5)

Goal: create trustworthy time and book state before scoring patterns.

Required work:
- retain raw exchange timestamp
- normalize seconds/ms/us/ns to integer milliseconds
- add local recv_ts_ms and recv_monotonic_ns
- calculate observed receive-minus-exchange timestamp delta separately from true market lead/lag
- reconstruct snapshot+delta orderbooks statefully
- reject/flag crossed or incomplete books
- filter zero-size top levels
- normalize trade side, price, quantity, trade id
- produce data-quality metrics per exchange

Gate to next stage: timestamp/book validation must pass before sub-second propagation research.

## Stage 2 — Abnormal Activity / Micro Fingerprint Engine (v0.6)

Goal: detect observable exchange-local mechanical patterns without asserting actor identity.

Independent features:
- Trade Burst
- Volume Burst
- Repeated Price/Size
- Buy/Sell Alternation
- Repeated Cadence
- Volume-Price Dislocation
- Aggressor Imbalance
- Orderbook Imbalance
- Absorption
- Quote Replenishment

Every detected event receives a Fingerprint ID and stores the complete feature vector. A high score means unusual/mechanical-looking activity, not proof of manipulation or wash trading.

Output example:
- fingerprint_id
- exchange
- canonical_symbol
- event_ts
- direction
- mechanical_score
- confidence
- feature_vector
- connectivity_health

## Stage 3 — Cross-Exchange Fingerprint Matcher (v0.7)

Goal: determine whether similar activity appears across venues.

Measure:
- fingerprint similarity
- origin candidate
- follower venues
- receive-time lead/lag
- direction consensus
- propagation strength
- propagation path

Example research path:
Bybit -> Bitget -> Bithumb -> Upbit

This is a statistical propagation hypothesis, not an assertion that the same actor traded across venues.

## Stage 4 — Outcome Labeler / Learning Dataset

Goal: learn which fingerprints have predictive value.

For every Fingerprint ID, label future executable market outcomes at:
- T+100ms
- T+250ms
- T+500ms
- T+1s
- T+2s
- T+5s
- T+10s
- T+30s
- T+1m
- T+5m

Store:
- executable bid/ask return
- MFE
- MAE
- spread
- depth/slippage estimate
- follower confirmation count
- remaining response gap

The primary learning target is future price/flow response, not whether an event was 'wash trading'.

## Stage 5 — Alpha Research Layer (v0.8+)

Keep strategy families independent.

### Tick Alpha
Research sub-second to several-second propagation where a follower venue has not yet fully responded.

### Bulk Alpha
Research persistent flow/absorption/replenishment regimes over seconds to minutes, where latency competition is less dominant.

Promotion metric:
Net Executable Alpha = gross outcome - fees - spread - slippage - estimated market impact

No live execution is enabled at this stage. Paper evaluation only.

## Stage 6 — MAGI META Integration

MAGI META consumes independent Truths rather than collapsing them prematurely:
- VPD / flow Truth
- Micro Fingerprint Truth
- Propagation Truth
- Connectivity/Data Quality Truth
- Paper Alpha performance

A venue with STALE/DEGRADED data must have its signal confidence reduced or invalidated.

## Development order

v0.5 Connectivity hardening + Timestamp Normalizer + Stateful OrderBook Builder
-> v0.6 Abnormal Activity / Fingerprint features
-> v0.7 Cross-Exchange Matcher + Propagation Map
-> Outcome Labeler + learning dataset
-> v0.8 Tick/Bulk paper alpha evaluation
-> MAGI META integration

## Research principle

Separate three questions:
1. Is the observed activity mechanically unusual?
2. Does a similar/related effect propagate across exchanges?
3. Does the pattern produce positive net executable alpha out of sample?

Only question 3 determines whether a pattern becomes a trading candidate.
