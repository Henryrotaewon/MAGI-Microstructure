# MAGI Microstructure

Multi-exchange market microstructure research POC.

## Phase 1 — Public Connection Test

The first milestone verifies public market-data connectivity through CCXT only.

- No API keys
- No private account access
- No orders
- No withdrawals
- No trading logic

### Initial exchanges

**Korea CEX**
- Upbit
- Bithumb
- Coinone

**Global CEX**
- Binance
- Bybit
- Bitget

**DEX candidates**
- Hyperliquid
- dYdX
- Apex
- Aster

## Roadmap

1. Public CCXT connectivity
2. Common-symbol mapping
3. Public trades/order-book capability test
4. Timestamp normalization
5. Abnormal Liquidity Pattern (ALP) research
6. Cross-exchange lead/lag validation
7. Paper-trading validation using executable bid/ask

This repository is intentionally separate from VPD-Investment. Existing VPD production logic is not modified by this POC.
