#!/usr/bin/env python3
"""MAGI Microstructure — Public Raw-Data Capability Test v0.2.

Tests whether each configured exchange can actually provide the public raw data
needed for later microstructure research. No API keys and no trading.
"""

import json
import time
from pathlib import Path

import ccxt

CONFIG = Path(__file__).resolve().parents[1] / "config" / "exchanges.json"
METHODS = {
    "ticker": "fetch_ticker",
    "orderbook": "fetch_order_book",
    "trades": "fetch_trades",
    "ohlcv": "fetch_ohlcv",
}
HAS_KEYS = {
    "ticker": "fetchTicker",
    "orderbook": "fetchOrderBook",
    "trades": "fetchTrades",
    "ohlcv": "fetchOHLCV",
}


def pick_symbol(exchange, preferred):
    for symbol in preferred:
        if symbol in exchange.markets and exchange.markets[symbol].get("active", True) is not False:
            return symbol
    for symbol, market in exchange.markets.items():
        if market.get("active", True) is False:
            continue
        if market.get("base") in {"BTC", "ETH", "XRP"} and market.get("quote") in {"KRW", "USDT", "USDC", "USD"}:
            return symbol
    return None


def call_method(exchange, name, symbol):
    if not exchange.has.get(HAS_KEYS[name]):
        return "NO", "CCXT has=false"
    try:
        if name == "orderbook":
            data = exchange.fetch_order_book(symbol, 20)
            ok = bool(data.get("bids") or data.get("asks"))
            detail = f"bids={len(data.get('bids', []))} asks={len(data.get('asks', []))}"
        elif name == "trades":
            data = exchange.fetch_trades(symbol, limit=20)
            ok = len(data) > 0
            ts = sum(1 for x in data if x.get("timestamp") is not None)
            side = sum(1 for x in data if x.get("side") is not None)
            detail = f"rows={len(data)} timestamp={ts} side={side}"
        elif name == "ohlcv":
            data = exchange.fetch_ohlcv(symbol, timeframe="1m", limit=5)
            ok = len(data) > 0
            detail = f"rows={len(data)}"
        else:
            data = exchange.fetch_ticker(symbol)
            ok = data is not None
            detail = f"last={data.get('last')}"
        return ("PASS" if ok else "EMPTY"), detail
    except Exception as exc:
        return "FAIL", f"{type(exc).__name__}: {str(exc)[:220]}"


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    print(f"MAGI Public Raw-Data Capability Test v0.2 | CCXT {ccxt.__version__}")
    print("PUBLIC DATA ONLY / NO API KEYS / NO ORDERS")
    print("=" * 120)

    for cfg in config["exchanges"]:
        eid = cfg["id"]
        print(f"\n[{cfg['group']}] {eid}")
        if eid not in ccxt.exchanges:
            print("  LOAD       FAIL  exchange id not present in installed CCXT")
            continue

        exchange = getattr(ccxt, eid)({"enableRateLimit": True, "timeout": 20000})
        try:
            exchange.load_markets()
            symbol = pick_symbol(exchange, cfg["preferred_symbols"])
            print(f"  LOAD       PASS  markets={len(exchange.markets)} symbol={symbol}")
            if not symbol:
                continue
            for name in ("ticker", "orderbook", "trades", "ohlcv"):
                status, detail = call_method(exchange, name, symbol)
                print(f"  {name.upper():10} {status:5} {detail}")
                time.sleep(0.25)
        except Exception as exc:
            print(f"  LOAD       FAIL  {type(exc).__name__}: {str(exc)[:300]}")
        finally:
            try:
                exchange.close()
            except Exception:
                pass

    print("\n" + "=" * 120)
    print("Microstructure minimum: ORDERBOOK + TRADES must both PASS.")
    print("TRADES output also reports whether CCXT returned timestamp and aggressor side fields.")


if __name__ == "__main__":
    main()
