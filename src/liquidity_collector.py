import argparse
import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import websockets


def now_ms():
    return int(time.time() * 1000)


def run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def first_level(levels):
    if not levels:
        return None, None
    row = levels[0]
    if isinstance(row, dict):
        price = row.get("price") or row.get("ask_price") or row.get("bid_price")
        qty = row.get("size") or row.get("qty") or row.get("ask_size") or row.get("bid_size")
        return safe_float(price), safe_float(qty)
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return safe_float(row[0]), safe_float(row[1])
    return None, None


def book_record(exchange, symbol, exchange_ts_ms, bids, asks, raw=None):
    bid, bid_qty = first_level(bids)
    ask, ask_qty = first_level(asks)
    spread_bps = None
    if bid and ask and bid > 0 and ask >= bid:
        mid = (bid + ask) / 2
        spread_bps = ((ask - bid) / mid) * 10000 if mid else None
    return {
        "recv_ts_ms": now_ms(),
        "exchange_ts_ms": exchange_ts_ms,
        "exchange": exchange,
        "symbol": symbol,
        "event": "orderbook",
        "best_bid": bid,
        "best_bid_qty": bid_qty,
        "best_ask": ask,
        "best_ask_qty": ask_qty,
        "spread_bps": spread_bps,
        "raw": raw,
    }


def trade_record(exchange, symbol, exchange_ts_ms, price, qty, side, raw=None):
    s = str(side).lower() if side is not None else None
    if s in {"bid", "buy", "b"}:
        s = "buy"
    elif s in {"ask", "sell", "s"}:
        s = "sell"
    return {
        "recv_ts_ms": now_ms(),
        "exchange_ts_ms": exchange_ts_ms,
        "exchange": exchange,
        "symbol": symbol,
        "event": "trade",
        "price": safe_float(price),
        "qty": safe_float(qty),
        "side": s,
        "raw": raw,
    }


class Writer:
    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.files = {}
        self.counts = defaultdict(lambda: defaultdict(int))

    def write(self, rec):
        exchange = rec["exchange"]
        if exchange not in self.files:
            self.files[exchange] = open(self.out_dir / f"{exchange}.jsonl", "a", encoding="utf-8")
        self.files[exchange].write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.files[exchange].flush()
        self.counts[exchange][rec["event"]] += 1

    def close(self):
        for f in self.files.values():
            f.close()


async def recv_json(ws, timeout=5):
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def collect_upbit(writer, duration):
    exchange, symbol = "upbit", "BTC/KRW"
    uri = "wss://api.upbit.com/websocket/v1"
    req = [
        {"ticket": f"magi-{uuid.uuid4()}"},
        {"type": "trade", "codes": ["KRW-BTC"], "is_only_realtime": True},
        {"type": "orderbook", "codes": ["KRW-BTC.15"], "is_only_realtime": True},
        {"format": "DEFAULT"},
    ]
    async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
        await ws.send(json.dumps(req))
        end = time.monotonic() + duration
        while time.monotonic() < end:
            try:
                m = await recv_json(ws, min(5, max(0.2, end - time.monotonic())))
            except asyncio.TimeoutError:
                continue
            typ = m.get("type")
            if typ == "trade":
                ts = m.get("trade_timestamp") or m.get("timestamp")
                writer.write(trade_record(exchange, symbol, ts, m.get("trade_price"), m.get("trade_volume"), m.get("ask_bid"), m))
            elif typ == "orderbook":
                units = m.get("orderbook_units") or []
                bids = [[u.get("bid_price"), u.get("bid_size")] for u in units]
                asks = [[u.get("ask_price"), u.get("ask_size")] for u in units]
                writer.write(book_record(exchange, symbol, m.get("timestamp"), bids, asks, m))


async def collect_bithumb(writer, duration):
    exchange, symbol = "bithumb", "BTC/KRW"
    uri = "wss://ws-api.bithumb.com/websocket/v1"
    req = [
        {"ticket": f"magi-{uuid.uuid4()}"},
        {"type": "trade", "codes": ["KRW-BTC"], "isOnlyRealtime": True},
        {"type": "orderbook", "codes": ["KRW-BTC"], "isOnlyRealtime": True},
        {"format": "DEFAULT"},
    ]
    async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
        await ws.send(json.dumps(req))
        end = time.monotonic() + duration
        while time.monotonic() < end:
            try:
                m = await recv_json(ws, min(5, max(0.2, end - time.monotonic())))
            except asyncio.TimeoutError:
                continue
            typ = m.get("type")
            if typ == "trade":
                ts = m.get("trade_timestamp") or m.get("timestamp")
                writer.write(trade_record(exchange, symbol, ts, m.get("trade_price"), m.get("trade_volume"), m.get("ask_bid"), m))
            elif typ == "orderbook":
                units = m.get("orderbook_units") or []
                bids = [[u.get("bid_price"), u.get("bid_size")] for u in units]
                asks = [[u.get("ask_price"), u.get("ask_size")] for u in units]
                writer.write(book_record(exchange, symbol, m.get("timestamp"), bids, asks, m))


async def collect_bybit(writer, duration):
    exchange, symbol = "bybit", "BTC/USDT"
    uri = "wss://stream.bybit.com/v5/public/spot"
    req = {"op": "subscribe", "args": ["publicTrade.BTCUSDT", "orderbook.50.BTCUSDT"]}
    async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
        await ws.send(json.dumps(req))
        end = time.monotonic() + duration
        while time.monotonic() < end:
            try:
                m = await recv_json(ws, min(5, max(0.2, end - time.monotonic())))
            except asyncio.TimeoutError:
                continue
            topic = m.get("topic", "")
            if topic.startswith("publicTrade."):
                for t in m.get("data") or []:
                    writer.write(trade_record(exchange, symbol, t.get("T") or m.get("ts"), t.get("p"), t.get("v"), t.get("S"), t))
            elif topic.startswith("orderbook."):
                d = m.get("data") or {}
                writer.write(book_record(exchange, symbol, d.get("cts") or m.get("cts") or m.get("ts"), d.get("b") or [], d.get("a") or [], d))


async def collect_bitget(writer, duration):
    exchange, symbol = "bitget", "BTC/USDT"
    uri = "wss://ws.bitget.com/v2/ws/public"
    req = {
        "op": "subscribe",
        "args": [
            {"instType": "SPOT", "channel": "trade", "instId": "BTCUSDT"},
            {"instType": "SPOT", "channel": "books5", "instId": "BTCUSDT"},
        ],
    }
    async with websockets.connect(uri, open_timeout=5, ping_interval=20) as ws:
        await ws.send(json.dumps(req))
        end = time.monotonic() + duration
        while time.monotonic() < end:
            try:
                m = await recv_json(ws, min(5, max(0.2, end - time.monotonic())))
            except asyncio.TimeoutError:
                continue
            arg = m.get("arg") or {}
            channel = arg.get("channel", "")
            data = m.get("data") or []
            if channel == "trade":
                for t in data:
                    if isinstance(t, dict):
                        writer.write(trade_record(exchange, symbol, t.get("ts"), t.get("price"), t.get("size"), t.get("side"), t))
                    elif isinstance(t, list) and len(t) >= 4:
                        writer.write(trade_record(exchange, symbol, t[0], t[1], t[2], t[3], t))
            elif channel.startswith("books"):
                for d in data:
                    if isinstance(d, dict):
                        writer.write(book_record(exchange, symbol, d.get("ts"), d.get("bids") or [], d.get("asks") or [], d))


async def run_collector(fn, writer, duration, errors):
    name = fn.__name__.replace("collect_", "")
    try:
        await fn(writer, duration)
    except Exception as e:
        errors[name] = f"{type(e).__name__}: {e}"


async def main_async(duration, out_root):
    rid = run_id()
    out_dir = Path(out_root) / rid
    writer = Writer(out_dir)
    errors = {}
    started_ms = now_ms()
    collectors = [collect_upbit, collect_bithumb, collect_bybit, collect_bitget]
    try:
        await asyncio.gather(*(run_collector(fn, writer, duration, errors) for fn in collectors))
    finally:
        writer.close()

    summary = {
        "version": "0.4",
        "mode": "PUBLIC DATA ONLY / NO API KEYS / NO ORDERS",
        "run_id": rid,
        "started_ms": started_ms,
        "ended_ms": now_ms(),
        "duration_sec": duration,
        "counts": {ex: dict(v) for ex, v in writer.counts.items()},
        "errors": errors,
        "minimum_sensor_rule": "trade > 0 and orderbook > 0",
        "note": "Signals are observable microstructure fingerprints; they do not establish actor identity or prove wash trading.",
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("MAGI Liquidity Fingerprint Raw Collector v0.4")
    print(f"run_id={rid} duration={duration}s out={out_dir}")
    print("PUBLIC DATA ONLY / NO API KEYS / NO ORDERS")
    print("=" * 92)
    for ex in ["upbit", "bithumb", "bybit", "bitget"]:
        c = summary["counts"].get(ex, {})
        tr, ob = c.get("trade", 0), c.get("orderbook", 0)
        ok = tr > 0 and ob > 0
        print(f"{'PASS' if ok else 'FAIL':4} {ex:10} trades={tr:<7} orderbook={ob:<7}")
        if ex in errors:
            print(f"     note: {errors[ex]}")
    print("=" * 92)
    print("Output fields include both exchange_ts_ms and local recv_ts_ms for lead/lag research.")
    print("Raw exchange payload is retained for later feature engineering and parser verification.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=int, default=int(os.getenv("MAGI_CAPTURE_SEC", "60")))
    p.add_argument("--out", default=os.getenv("MAGI_OUT_DIR", "data/raw"))
    args = p.parse_args()
    duration = max(5, min(args.duration, 300))
    asyncio.run(main_async(duration, args.out))


if __name__ == "__main__":
    main()
