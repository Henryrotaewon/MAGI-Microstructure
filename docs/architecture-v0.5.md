# MAGI Liquidity Intelligence Architecture v0.5

## Goal

Detect observable mechanical liquidity fingerprints on each exchange and measure whether those patterns propagate to other exchanges. Public market data alone cannot establish actor identity or prove wash trading, so the system separates observable microstructure evidence from cross-exchange propagation evidence.

## Layer A: Micro Fingerprint Engine

Per-exchange, per-symbol analysis on 100 ms to 10 s horizons.

Inputs:
- normalized trades
- normalized orderbook state
- exchange timestamp
- local receive timestamp

Features:
- Trade Burst
- Volume-Price Dislocation
- Buy/Sell Alternation
- Absorption
- Quote Replenishment
- Orderbook Imbalance

Output:
- exchange-local Micro Fingerprint Score
- direction
- confidence
- feature vector

## Layer B: Propagation Engine

Cross-exchange analysis on 100 ms to minutes horizons.

Inputs:
- Micro Fingerprint signals from Layer A
- normalized price returns
- local receive timing

Outputs:
- Origin Exchange
- Follower Exchange
- Lead Time
- Direction Consensus
- Propagation Strength
- Remaining Response Gap

## Processing Flow

```text
Raw WebSocket streams
        |
        v
Timestamp Normalizer / OrderBook State Builder
        |
        +----------------------+
        |                      |
        v                      v
Micro Fingerprint Engine   Price/Return Normalizer
        |                      |
        +-----------+----------+
                    v
            Propagation Engine
                    |
                    v
          MAGI META Intelligence
                    |
                    v
             PAPER SIGNAL ONLY
```

## Design rules

1. Keep Micro and Propagation engines independent so either can evolve without changing the other.
2. Never interpret a fingerprint score as proof of wash trading or manipulation.
3. Use exchange_ts_ms and recv_ts_ms separately; do not mix exchange clock delay with market lead-lag.
4. Reconstruct stateful orderbooks before using absorption/replenishment as production features.
5. Evaluate on executable bid/ask and include fees/slippage before any strategy promotion.
6. GitHub Actions remains a smoke-test and short-capture environment; continuous collection belongs on a persistent runner.

## Near-term versions

- v0.5: timestamp normalization + stateful orderbook reconstruction
- v0.6: Micro Fingerprint feature validation
- v0.7: Cross-Exchange Propagation Map
- v0.8: paper-signal evaluation with T+100/250/500ms/1/2/5/10s outcomes
