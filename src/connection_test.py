#!/usr/bin/env python3
"""MAGI Microstructure — CCXT Public Connection Test v0.1.

Public data only. No API keys, private endpoints, orders, or withdrawals.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

CONFIG = Path(__file__).resolve().parents[1] / "config" / "exchanges.json"


def pick_symbol(exchange, preferred):
    for symbol in preferred:
        market = exchange.markets.get(symbol)
        if market and market.get("active", True) is not False:
            return symbol

    for symbol, market in exchange.markets.items():
        if market.get("active", True) is False:
            continue
        if market.get("base") in {"BTC", "ETH", "XRP"} and market.get("quote") in {"KRW", "USDT", "USDC", "USD"}:
            return symbol
    return None


def test_exchange(cfg):
    exchange_id = cfg["id"]
    result = {
        "exchange": exchange_id,
        "group": cfg["group"],
        "status": "FAIL",
        "markets": 0,
        "symbol": None,
        "last": None,
        "latency_ms": None,
        "error": None,
    }

    if exchange_id not in ccxt.exchanges:
        result["error"] = f"not present in installed CCXT {ccxt.__version__}"
        return result

    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 15000})
    try:
        started = time.perf_counter()
        exchange.load_markets()
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        result["markets"] = len(exchange.markets)
        result["symbol"] = pick_symbol(exchange, cfg["preferred_symbols"])

        if not result["symbol"]:
            result["status"] = "PARTIAL"
            result["error"] = "markets loaded but representative symbol not found"
        elif exchange.has.get("fetchTicker"):
            ticker = exchange.fetch_ticker(result["symbol"])
            result["last"] = ticker.get("last")
            result["status"] = "PASS"
        else:
            result["status"] = "PARTIAL"
            result["error"] = "fetchTicker unsupported"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            exchange.close()
        except Exception:
            pass

    return result


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    print("MAGI CCXT Public Connection Test v0.1")
    print("UTC:", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print("CCXT:", ccxt.__version__)
    print("MODE: PUBLIC DATA ONLY / NO ORDERS")
    print("-" * 90)

    results = []
    for cfg in config["exchanges"]:
        result = test_exchange(cfg)
        results.append(result)
        print(
            f"{result['status']:7} {result['group']:6} {result['exchange']:12} "
            f"markets={result['markets']:5} symbol={str(result['symbol']):18} "
            f"last={result['last']} load={result['latency_ms']}ms"
        )
        if result["error"]:
            print("        note:", result["error"])
        time.sleep(0.25)

    passed = sum(r["status"] == "PASS" for r in results)
    partial = sum(r["status"] == "PARTIAL" for r in results)
    failed = sum(r["status"] == "FAIL" for r in results)
    print("-" * 90)
    print(f"PASS={passed} PARTIAL={partial} FAIL={failed} TOTAL={len(results)}")

    # Connectivity failures are reported, not treated as a Python crash.
    return 0


if __name__ == "__main__":
    sys.exit(main())
