from __future__ import annotations

import asyncio
import json
import time

import websockets


async def _collect(ws, classify, timeout_s: int = 20) -> tuple[int, int]:
    trades = 0
    books = 0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and (trades == 0 or books == 0):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            break
        msg = json.loads(raw)
        kind = classify(msg)
        if kind == "trade":
            trades += 1
        elif kind == "book":
            books += 1
    return trades, books


async def test_kraken() -> tuple[str, int, int]:
    url = "wss://ws.kraken.com/v2"
    async with websockets.connect(url, ping_interval=20, close_timeout=5) as ws:
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": ["BTC/USD"]}}))
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "book", "symbol": ["BTC/USD"], "depth": 10, "snapshot": True}}))

        def classify(msg: dict) -> str | None:
            channel = msg.get("channel")
            if channel == "trade" and msg.get("data"):
                return "trade"
            if channel == "book" and msg.get("data"):
                return "book"
            return None

        t, b = await _collect(ws, classify)
        return "kraken", t, b


async def test_aster() -> tuple[str, int, int]:
    url = "wss://fstream.asterdex.com/ws"
    async with websockets.connect(url, ping_interval=20, close_timeout=5) as ws:
        await ws.send(json.dumps({"method": "SUBSCRIBE", "params": ["btcusdt@aggTrade", "btcusdt@depth"], "id": 1}))

        def classify(msg: dict) -> str | None:
            event = msg.get("e")
            if event == "aggTrade":
                return "trade"
            if event == "depthUpdate":
                return "book"
            return None

        t, b = await _collect(ws, classify)
        return "aster", t, b


async def test_apex() -> tuple[str, int, int]:
    ts = int(time.time() * 1000)
    url = f"wss://quote.omni.apex.exchange/realtime_public?v=2&timestamp={ts}"
    async with websockets.connect(url, ping_interval=None, close_timeout=5) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": ["recentlyTrade.H.BTCUSDT", "orderBook200.H.BTCUSDT"]}))

        def classify(msg: dict) -> str | None:
            topic = str(msg.get("topic") or "")
            if topic.startswith("recentlyTrade") and msg.get("data"):
                return "trade"
            if topic.startswith("orderBook") and msg.get("data"):
                return "book"
            return None

        t, b = await _collect(ws, classify)
        return "apex", t, b


async def main() -> None:
    tests = [test_kraken, test_aster, test_apex]
    failures = []
    for fn in tests:
        name = fn.__name__.removeprefix("test_")
        try:
            exchange, trades, books = await fn()
            ok = trades > 0 and books > 0
            print(f"{exchange}: trades={trades} books={books} status={'PASS' if ok else 'FAIL'}")
            if not ok:
                failures.append(exchange)
        except Exception as exc:
            print(f"{name}: ERROR {type(exc).__name__}: {exc}")
            failures.append(name)
    if failures:
        raise SystemExit(f"secondary sensor smoke failed: {', '.join(failures)}")


if __name__ == "__main__":
    asyncio.run(main())
