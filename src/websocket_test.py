import asyncio
import json
import time
import uuid

import websockets

TIMEOUT_SEC = 10


def now_ms():
    return int(time.time() * 1000)


async def recv_json(ws, timeout=TIMEOUT_SEC):
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def test_upbit():
    name = "upbit"
    uri = "wss://api.upbit.com/websocket/v1"
    req = [
        {"ticket": f"magi-{uuid.uuid4()}"},
        {"type": "trade", "codes": ["KRW-BTC"], "is_only_realtime": True},
        {"type": "orderbook", "codes": ["KRW-BTC.15"], "is_only_realtime": True},
        {"format": "DEFAULT"},
    ]
    try:
        async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
            await ws.send(json.dumps(req))
            trade = orderbook = 0
            deadline = time.time() + TIMEOUT_SEC
            while time.time() < deadline and (trade == 0 or orderbook == 0):
                msg = await recv_json(ws, max(1, deadline - time.time()))
                if msg.get("type") == "trade":
                    trade += 1
                elif msg.get("type") == "orderbook":
                    orderbook += 1
            return name, trade, orderbook, None
    except Exception as e:
        return name, 0, 0, f"{type(e).__name__}: {e}"


async def test_bithumb():
    name = "bithumb"
    uri = "wss://ws-api.bithumb.com/websocket/v1"
    req = [
        {"ticket": f"magi-{uuid.uuid4()}"},
        {"type": "trade", "codes": ["KRW-BTC"], "isOnlyRealtime": True},
        {"type": "orderbook", "codes": ["KRW-BTC"], "isOnlyRealtime": True},
        {"format": "DEFAULT"},
    ]
    try:
        async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
            await ws.send(json.dumps(req))
            trade = orderbook = 0
            deadline = time.time() + TIMEOUT_SEC
            while time.time() < deadline and (trade == 0 or orderbook == 0):
                msg = await recv_json(ws, max(1, deadline - time.time()))
                if msg.get("type") == "trade":
                    trade += 1
                elif msg.get("type") == "orderbook":
                    orderbook += 1
            return name, trade, orderbook, None
    except Exception as e:
        return name, 0, 0, f"{type(e).__name__}: {e}"


async def test_binance():
    name = "binance"
    uri = "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@depth5@100ms"
    try:
        async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
            trade = orderbook = 0
            deadline = time.time() + TIMEOUT_SEC
            while time.time() < deadline and (trade == 0 or orderbook == 0):
                msg = await recv_json(ws, max(1, deadline - time.time()))
                stream = msg.get("stream", "")
                if "@trade" in stream:
                    trade += 1
                elif "@depth" in stream:
                    orderbook += 1
            return name, trade, orderbook, None
    except Exception as e:
        return name, 0, 0, f"{type(e).__name__}: {e}"


async def test_bybit():
    name = "bybit"
    uri = "wss://stream.bybit.com/v5/public/spot"
    req = {
        "op": "subscribe",
        "args": ["publicTrade.BTCUSDT", "orderbook.50.BTCUSDT"],
    }
    try:
        async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
            await ws.send(json.dumps(req))
            trade = orderbook = 0
            deadline = time.time() + TIMEOUT_SEC
            while time.time() < deadline and (trade == 0 or orderbook == 0):
                msg = await recv_json(ws, max(1, deadline - time.time()))
                topic = msg.get("topic", "")
                if topic.startswith("publicTrade."):
                    trade += 1
                elif topic.startswith("orderbook."):
                    orderbook += 1
            return name, trade, orderbook, None
    except Exception as e:
        return name, 0, 0, f"{type(e).__name__}: {e}"


async def test_bitget():
    name = "bitget"
    uri = "wss://ws.bitget.com/v2/ws/public"
    req = {
        "op": "subscribe",
        "args": [
            {"instType": "SPOT", "channel": "trade", "instId": "BTCUSDT"},
            {"instType": "SPOT", "channel": "books5", "instId": "BTCUSDT"},
        ],
    }
    try:
        async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
            await ws.send(json.dumps(req))
            trade = orderbook = 0
            deadline = time.time() + TIMEOUT_SEC
            while time.time() < deadline and (trade == 0 or orderbook == 0):
                msg = await recv_json(ws, max(1, deadline - time.time()))
                arg = msg.get("arg") or {}
                channel = arg.get("channel", "")
                if channel == "trade" and msg.get("data"):
                    trade += 1
                elif channel.startswith("books") and msg.get("data"):
                    orderbook += 1
            return name, trade, orderbook, None
    except Exception as e:
        return name, 0, 0, f"{type(e).__name__}: {e}"


async def test_kraken():
    name = "kraken"
    uri = "wss://ws.kraken.com/v2"
    trade_req = {
        "method": "subscribe",
        "params": {"channel": "trade", "symbol": ["BTC/USD"], "snapshot": True},
    }
    book_req = {
        "method": "subscribe",
        "params": {"channel": "book", "symbol": ["BTC/USD"], "depth": 10, "snapshot": True},
    }
    try:
        async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
            await ws.send(json.dumps(trade_req))
            await ws.send(json.dumps(book_req))
            trade = orderbook = 0
            deadline = time.time() + TIMEOUT_SEC
            while time.time() < deadline and (trade == 0 or orderbook == 0):
                msg = await recv_json(ws, max(1, deadline - time.time()))
                channel = msg.get("channel", "")
                if channel == "trade" and msg.get("data"):
                    trade += 1
                elif channel == "book" and msg.get("data"):
                    orderbook += 1
            return name, trade, orderbook, None
    except Exception as e:
        return name, 0, 0, f"{type(e).__name__}: {e}"


async def main():
    print("MAGI WebSocket Public Stream Test v0.4")
    print(f"UTC_MS={now_ms()} | PUBLIC DATA ONLY | NO API KEYS | NO ORDERS")
    print("=" * 92)

    tests = [test_upbit, test_bithumb, test_binance, test_bybit, test_bitget, test_kraken]
    results = []
    for test in tests:
        results.append(await test())

    pass_count = 0
    for name, trades, orderbooks, err in results:
        ok = trades > 0 and orderbooks > 0
        status = "PASS" if ok else "FAIL"
        if ok:
            pass_count += 1
        print(f"{status:4} {name:10} trades={trades:<3} orderbook={orderbooks:<3}")
        if err:
            print(f"     note: {err}")

    print("=" * 92)
    print(f"PASS={pass_count} FAIL={len(results)-pass_count} TOTAL={len(results)}")
    print("Minimum for Microstructure Sensor: public trade stream + public orderbook stream both received.")


if __name__ == "__main__":
    asyncio.run(main())
