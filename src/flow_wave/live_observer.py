from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from dataclasses import asdict
from pathlib import Path

import websockets

from src.flow_wave.engine import FlowWaveDetector, WaveObservation


def now_ms() -> int:
    return int(time.time() * 1000)


class TradeWaveFeatureBuilder:
    """Builds simple trade-flow wave features from live public trades.

    v0.1 deliberately uses trade flow only. Order-book stress is added later after
    each venue's stateful book semantics are validated. This avoids pretending
    book features are comparable before normalization is proven.
    """

    def __init__(self, recent_ms: int = 5_000, baseline_ms: int = 60_000, warmup_ms: int = 20_000):
        self.recent_ms = recent_ms
        self.baseline_ms = baseline_ms
        self.warmup_ms = warmup_ms
        self.trades = defaultdict(deque)
        self.first_ts = {}

    def on_trade(self, event: dict) -> WaveObservation | None:
        ex, symbol, ts = event["exchange"], event["symbol"], int(event["ts_ms"])
        key = (ex, symbol)
        q = self.trades[key]
        q.append(event)
        self.first_ts.setdefault(key, ts)
        cutoff = ts - self.baseline_ms
        while q and q[0]["ts_ms"] < cutoff:
            q.popleft()
        if ts - self.first_ts[key] < self.warmup_ms:
            return None

        recent = [x for x in q if x["ts_ms"] >= ts - self.recent_ms]
        older = [x for x in q if x["ts_ms"] < ts - self.recent_ms]
        if len(recent) < 2 or len(older) < 2:
            return None

        recent_qty = sum(max(float(x.get("qty") or 0.0), 0.0) for x in recent)
        older_qty = sum(max(float(x.get("qty") or 0.0), 0.0) for x in older)
        recent_rate = recent_qty / max(self.recent_ms / 1000.0, 1e-9)
        older_span_ms = max((ts - self.recent_ms) - older[0]["ts_ms"], 1000)
        baseline_rate = older_qty / (older_span_ms / 1000.0)
        if baseline_rate <= 0:
            return None
        burst = min(recent_rate / baseline_rate, 20.0)

        p0 = float(recent[0]["price"])
        p1 = float(recent[-1]["price"])
        if p0 <= 0:
            return None
        move_bps = (p1 / p0 - 1.0) * 10_000
        if abs(move_bps) < 1.0:
            return None
        direction = "UP" if move_bps > 0 else "DOWN"

        buys = sum(float(x.get("qty") or 0.0) for x in recent if x.get("side") == "buy")
        sells = sum(float(x.get("qty") or 0.0) for x in recent if x.get("side") == "sell")
        side_total = buys + sells
        imbalance = abs(buys - sells) / side_total if side_total > 0 else 0.0
        micro_score = min(100.0, 35.0 * min(burst / 4.0, 1.0) + 35.0 * min(abs(move_bps) / 20.0, 1.0) + 30.0 * imbalance)

        return WaveObservation(
            exchange=ex,
            symbol=symbol,
            ts_ms=ts,
            direction=direction,
            volume_burst=burst,
            micro_score=micro_score,
            price_move_bps=move_bps,
            liquidity_stress=0.0,
            dependency_break=False,
            connectivity_health="CONNECTED",
        )


async def recv_json(ws):
    raw = await ws.recv()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def upbit(queue, stop_at):
    uri = "wss://api.upbit.com/websocket/v1"
    req = [{"ticket": f"magi-{uuid.uuid4()}"}, {"type": "trade", "codes": ["KRW-BTC"], "is_only_realtime": True}]
    async with websockets.connect(uri, open_timeout=8, ping_interval=20) as ws:
        await ws.send(json.dumps(req))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if m.get("type") == "trade":
                await queue.put({"exchange": "upbit", "symbol": "BTC", "ts_ms": now_ms(), "price": m.get("trade_price"), "qty": m.get("trade_volume"), "side": "buy" if m.get("ask_bid") == "BID" else "sell"})


async def bithumb(queue, stop_at):
    uri = "wss://ws-api.bithumb.com/websocket/v1"
    req = [{"ticket": f"magi-{uuid.uuid4()}"}, {"type": "trade", "codes": ["KRW-BTC"], "isOnlyRealtime": True}]
    async with websockets.connect(uri, open_timeout=8, ping_interval=20) as ws:
        await ws.send(json.dumps(req))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if m.get("type") == "trade":
                await queue.put({"exchange": "bithumb", "symbol": "BTC", "ts_ms": now_ms(), "price": m.get("trade_price"), "qty": m.get("trade_volume"), "side": "buy" if m.get("ask_bid") == "BID" else "sell"})


async def bybit(queue, stop_at):
    async with websockets.connect("wss://stream.bybit.com/v5/public/spot", open_timeout=8, ping_interval=20) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": ["publicTrade.BTCUSDT"]}))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if str(m.get("topic", "")).startswith("publicTrade."):
                for t in m.get("data") or []:
                    await queue.put({"exchange": "bybit", "symbol": "BTC", "ts_ms": now_ms(), "price": t.get("p"), "qty": t.get("v"), "side": "buy" if str(t.get("S", "")).lower() == "buy" else "sell"})


async def bitget(queue, stop_at):
    async with websockets.connect("wss://ws.bitget.com/v2/ws/public", open_timeout=8, ping_interval=20) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [{"instType": "SPOT", "channel": "trade", "instId": "BTCUSDT"}]}))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if (m.get("arg") or {}).get("channel") == "trade":
                for t in m.get("data") or []:
                    if isinstance(t, dict):
                        await queue.put({"exchange": "bitget", "symbol": "BTC", "ts_ms": now_ms(), "price": t.get("price"), "qty": t.get("size"), "side": str(t.get("side") or "").lower()})
                    elif isinstance(t, list) and len(t) >= 4:
                        await queue.put({"exchange": "bitget", "symbol": "BTC", "ts_ms": now_ms(), "price": t[1], "qty": t[2], "side": str(t[3]).lower()})


async def kraken(queue, stop_at):
    async with websockets.connect("wss://ws.kraken.com/v2", open_timeout=8, ping_interval=20) as ws:
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": ["BTC/USD"]}}))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if m.get("channel") == "trade":
                for t in m.get("data") or []:
                    await queue.put({"exchange": "kraken", "symbol": "BTC", "ts_ms": now_ms(), "price": t.get("price"), "qty": t.get("qty"), "side": str(t.get("side") or "").lower()})


async def aster(queue, stop_at):
    async with websockets.connect("wss://fstream.asterdex.com/ws", open_timeout=8, ping_interval=20) as ws:
        await ws.send(json.dumps({"method": "SUBSCRIBE", "params": ["btcusdt@aggTrade"], "id": 1}))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if m.get("e") == "aggTrade":
                side = "sell" if m.get("m") else "buy"
                await queue.put({"exchange": "aster", "symbol": "BTC", "ts_ms": now_ms(), "price": m.get("p"), "qty": m.get("q"), "side": side})


async def apex(queue, stop_at):
    uri = f"wss://quote.omni.apex.exchange/realtime_public?v=2&timestamp={now_ms()}"
    async with websockets.connect(uri, open_timeout=8, ping_interval=None) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": ["recentlyTrade.H.BTCUSDT"]}))
        while time.monotonic() < stop_at:
            m = await recv_json(ws)
            if str(m.get("topic") or "").startswith("recentlyTrade"):
                data = m.get("data") or []
                rows = data if isinstance(data, list) else [data]
                for t in rows:
                    if isinstance(t, dict):
                        price = t.get("p") or t.get("price")
                        qty = t.get("v") or t.get("size") or t.get("q")
                        side_raw = str(t.get("S") or t.get("side") or "").lower()
                        side = "buy" if side_raw in {"buy", "b"} else "sell" if side_raw in {"sell", "s"} else None
                        if price is not None and qty is not None:
                            await queue.put({"exchange": "apex", "symbol": "BTC", "ts_ms": now_ms(), "price": price, "qty": qty, "side": side})


async def guarded(name, fn, queue, stop_at, errors):
    try:
        await fn(queue, stop_at)
    except Exception as exc:
        errors[name] = f"{type(exc).__name__}: {exc}"


async def main_async(duration: int, out_path: str):
    queue = asyncio.Queue()
    stop_at = time.monotonic() + duration
    errors = {}
    feature_builder = TradeWaveFeatureBuilder()
    detector = FlowWaveDetector(window_ms=15_000, min_volume_burst=2.0, min_micro_score=45.0, min_venues=2, target_exchange="upbit")
    connectors = {"upbit": upbit, "bithumb": bithumb, "bybit": bybit, "bitget": bitget, "kraken": kraken, "aster": aster, "apex": apex}
    tasks = [asyncio.create_task(guarded(name, fn, queue, stop_at, errors)) for name, fn in connectors.items()]
    counts = defaultdict(int)
    waves = []

    while time.monotonic() < stop_at or not queue.empty():
        timeout = max(0.05, min(1.0, stop_at - time.monotonic())) if time.monotonic() < stop_at else 0.05
        try:
            event = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            if time.monotonic() >= stop_at:
                break
            continue
        counts[event["exchange"]] += 1
        try:
            event["price"] = float(event["price"])
            event["qty"] = float(event["qty"])
        except (TypeError, ValueError):
            continue
        obs = feature_builder.on_trade(event)
        if obs:
            signal = detector.on_observation(obs)
            if signal:
                rec = signal.to_dict()
                waves.append(rec)
                print("FLOW_WAVE", json.dumps(rec, ensure_ascii=False, separators=(",", ":")))

    await asyncio.gather(*tasks, return_exceptions=True)
    result = {"version": "flow-wave-live-v0.1", "mode": "PUBLIC DATA / PAPER RESEARCH ONLY", "duration_sec": duration, "trade_counts": dict(counts), "errors": errors, "wave_count": len(waves), "waves": waves}
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["version", "duration_sec", "trade_counts", "errors", "wave_count"]}, ensure_ascii=False, indent=2))
    if not any(counts.get(x, 0) for x in connectors):
        raise SystemExit("no live trades received")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=int, default=90)
    p.add_argument("--out", default="data/flow_wave/live_observation.json")
    args = p.parse_args()
    asyncio.run(main_async(max(30, min(args.duration, 300)), args.out))


if __name__ == "__main__":
    main()
