# MAGI Equilibrium Break Hypothesis v0.1

## Research objective

Test whether changes in the normally stable cross-venue liquidity/quote relationship can predict subsequent price propagation before the target venue fully reacts.

This is a research hypothesis, not a claim about manipulation, issuer activity, or any venue's internal market-making logic. Only observable public market data are used.

## Core state model

`EQUILIBRIUM -> STRESS -> BREAK -> PROPAGATION / REVERSION -> RE-EQUILIBRIUM`

### 1. EQUILIBRIUM
Learn the normal relationship for each symbol and venue pair:
- best bid/ask and mid-return co-movement
- direction agreement
- response lag distribution
- spread/depth relationship
- quote replenishment behavior
- leader/follower dependency score
- liquidity regime

### 2. STRESS
Detect deterioration before a full relationship break:
- ask/bid depth depletion
- replenishment slowdown/failure
- spread expansion
- aggressive trade imbalance
- abnormal lag expansion
- response-ratio deterioration
- dependency-score decay

### 3. BREAK
A break is an abnormal deviation from the learned normal relationship, not merely a price difference.

Candidate break types:
- FOLLOWER_NON_RESPONSE: follower fails to respond to its normal leader
- FOLLOWER_OVERSHOOT: follower response is abnormally large
- LEADER_REVERSAL: usual follower moves first and becomes a temporary leader
- DIRECTION_DIVERGENCE: normally aligned venues move in opposite directions
- LIQUIDITY_BREAK: depth/spread/replenishment relationship breaks before price

### 4. PROPAGATION / REVERSION
After a break, observe whether:
- other independent venues confirm the move
- the shock propagates to KRW venues
- the original break reverts as local noise
- the normal leader/follower relationship is restored

### 5. OUTCOME
Attach leakage-safe future outcomes at:
`100ms, 250ms, 500ms, 1s, 2s, 5s, 10s, 30s, 1m, 5m`

Measure:
- P(UP), P(DOWN), P(FLAT)
- executable return after bid/ask
- MFE / MAE
- spread and estimated slippage
- propagation confirmation count
- remaining response gap
- net expected value after costs

## Primary hypothesis

A relationship break has predictive value only when the conditional post-break outcome distribution differs materially from the matched normal-state distribution after costs and out of sample.

The highest-priority candidate is:

`LIQUIDITY STRESS -> DEPENDENCY BREAK -> CROSS-VENUE CONFIRMATION -> TARGET UNDER-RESPONSE -> PROPAGATION`

## Validation discipline

1. Learn baselines only from past data.
2. Freeze all signal features at detection time.
3. Use future data only for outcome labels.
4. Compare every break cohort with matched non-break controls by symbol, liquidity regime, volatility regime, and time period.
5. Require adequate sample size and out-of-sample persistence.
6. Do not promote a pattern because of a few impressive examples.
7. Paper-research only until net executable alpha survives costs and OOS validation.

## Data cycle

`WebSocket capture -> normalization -> market state -> baseline relationship -> stress metrics -> break classification -> cross-venue confirmation -> outcome label -> empirical statistics -> calibration -> OOS paper validation`

Raw tick/orderbook data should be retained outside the Git repository when continuous capture becomes large. GitHub should hold code, schemas, configuration, compact feature/outcome datasets, and research summaries.

## Initial promotion gate

A break type becomes a MAGI candidate trigger only after it shows:
- sufficient independent observations across multiple days/regimes
- statistically meaningful difference versus matched controls
- stable direction probability/calibration
- positive net executable EV after realistic fees/spread/slippage
- acceptable MAE/drawdown characteristics
- persistence in held-out/OOS data

Until then, all break scores are research signals only.
