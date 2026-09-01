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


def normalize_ts(v):
    if v is None:
        return None, None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None, "invalid"
    a = abs(n)
    if a >= 10**17:
        return n // 1_000_000, "ns"
    if a >= 10**14:
        return n // 1_000, "us"
    if a >= 10**11:
        return n, "ms"
    if a >= 10**8:
        return n * 1_000, "s"
    return n, "unknown"


def valid_levels(levels):
    out = []
    for row in levels or []:
        if isinstance(row, dict):
            p = row.get("price") or row.get("ask_price") or row.get("bid_price")
            q = row.get("size") or row.get("qty") or row.get("ask_size") or row.get("bid_size")
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            p, q = row[0], row[1]
        else:
            continue
        p, q = safe_float(p), safe_float(q)
        if p is not None and q is not None and p > 0 and q > 0:
            out.append((p, q))
    return out


class BookState:
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.ready = False

    @staticmethod
    def _apply(side, levels):
        for row in levels or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            p, q = safe_float(row[0]), safe_float(row[1])
            if p is None or q is None:
                continue
            if q <= 0:
                side.pop(p, None)
            else:
                side[p] = q

    def update(self, bids, asks, action="snapshot"):
        if action == "snapshot" or not self.ready:
            self.bids.clear(); self.asks.clear()
        self._apply(self.bids, bids)
        self._apply(self.asks, asks)
        self.ready = bool(self.bids and self.asks)

    def top(self):
        if not self.ready:
            return None, None, None, None
        bp = max(self.bids); ap = min(self.asks)
        return bp, self.bids[bp], ap, self.asks[ap]


def base_timing(exchange_ts_raw):
    recv = now_ms()
    mono = time.monotonic_ns()
    ex_ms, unit = normalize_ts(exchange_ts_raw)
    return recv, mono, ex_ms, unit, (recv - ex_ms if ex_ms is not None else None)


def book_record(exchange, symbol, exchange_ts_raw, bids=None, asks=None, raw=None, state=None, action="snapshot"):
    recv, mono, ex_ms, unit, delta = base_timing(exchange_ts_raw)
    if state is not None:
        state.update(bids, asks, action)
        bid, bid_qty, ask, ask_qty = state.top()
    else:
        vb, va = valid_levels(bids), valid_levels(asks)
        bid, bid_qty = max(vb, default=(None, None), key=lambda x: x[0])
        ask, ask_qty = min(va, default=(None, None), key=lambda x: x[0])
    valid = bool(bid and ask and bid > 0 and ask > bid)
    spread_bps = (((ask - bid) / ((bid + ask) / 2)) * 10000) if valid else None
    return {"recv_ts_ms": recv, "recv_monotonic_ns": mono, "exchange_ts_raw": exchange_ts_raw,
            "exchange_ts_ms": ex_ms, "exchange_ts_unit": unit, "observed_ts_delta_ms": delta,
            "exchange": exchange, "symbol": symbol, "event": "orderbook", "book_action": action,
            "best_bid": bid, "best_bid_qty": bid_qty, "best_ask": ask, "best_ask_qty": ask_qty,
            "spread_bps": spread_bps, "book_valid": valid, "raw": raw}


def trade_record(exchange, symbol, exchange_ts_raw, price, qty, side, raw=None, trade_id=None):
    recv, mono, ex_ms, unit, delta = base_timing(exchange_ts_raw)
    s = str(side).lower() if side is not None else None
    if s in {"bid", "buy", "b"}: s = "buy"
    elif s in {"ask", "sell", "s"}: s = "sell"
    return {"recv_ts_ms": recv, "recv_monotonic_ns": mono, "exchange_ts_raw": exchange_ts_raw,
            "exchange_ts_ms": ex_ms, "exchange_ts_unit": unit, "observed_ts_delta_ms": delta,
            "exchange": exchange, "symbol": symbol, "event": "trade", "trade_id": trade_id,
            "price": safe_float(price), "qty": safe_float(qty), "side": s, "raw": raw}


class Writer:
    def __init__(self, out_dir):
        self.out_dir = Path(out_dir); self.out_dir.mkdir(parents=True, exist_ok=True)
        self.files = {}; self.counts = defaultdict(lambda: defaultdict(int)); self.quality = defaultdict(lambda: defaultdict(int))
    def write(self, rec):
        ex = rec["exchange"]
        if ex not in self.files: self.files[ex] = open(self.out_dir / f"{ex}.jsonl", "a", encoding="utf-8")
        self.files[ex].write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"); self.files[ex].flush()
        self.counts[ex][rec["event"]] += 1
        self.quality[ex][f"ts_unit_{rec.get('exchange_ts_unit')}"] += 1
        if rec.get("exchange_ts_ms") is None: self.quality[ex]["timestamp_null"] += 1
        if rec["event"] == "orderbook" and not rec.get("book_valid"): self.quality[ex]["invalid_book"] += 1
    def close(self):
        for f in self.files.values(): f.close()


async def recv_json(ws, timeout=5):
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if isinstance(raw, bytes): raw = raw.decode("utf-8")
    return json.loads(raw)


async def collect_upbit(writer, duration):
    ex, symbol, uri = "upbit", "BTC/KRW", "wss://api.upbit.com/websocket/v1"
    req=[{"ticket":f"magi-{uuid.uuid4()}"},{"type":"trade","codes":["KRW-BTC"],"is_only_realtime":True},{"type":"orderbook","codes":["KRW-BTC.15"],"is_only_realtime":True},{"format":"DEFAULT"}]
    async with websockets.connect(uri,open_timeout=5,ping_interval=20) as ws:
        await ws.send(json.dumps(req)); end=time.monotonic()+duration
        while time.monotonic()<end:
            try: m=await recv_json(ws,min(5,max(.2,end-time.monotonic())))
            except asyncio.TimeoutError: continue
            if m.get("type")=="trade": writer.write(trade_record(ex,symbol,m.get("trade_timestamp") or m.get("timestamp"),m.get("trade_price"),m.get("trade_volume"),m.get("ask_bid"),m,m.get("sequential_id")))
            elif m.get("type")=="orderbook":
                u=m.get("orderbook_units") or []; writer.write(book_record(ex,symbol,m.get("timestamp"),[[x.get("bid_price"),x.get("bid_size")] for x in u],[[x.get("ask_price"),x.get("ask_size")] for x in u],m))


async def collect_bithumb(writer, duration):
    ex, symbol, uri="bithumb","BTC/KRW","wss://ws-api.bithumb.com/websocket/v1"
    req=[{"ticket":f"magi-{uuid.uuid4()}"},{"type":"trade","codes":["KRW-BTC"],"isOnlyRealtime":True},{"type":"orderbook","codes":["KRW-BTC"],"isOnlyRealtime":True},{"format":"DEFAULT"}]
    async with websockets.connect(uri,open_timeout=5,ping_interval=20) as ws:
        await ws.send(json.dumps(req)); end=time.monotonic()+duration
        while time.monotonic()<end:
            try: m=await recv_json(ws,min(5,max(.2,end-time.monotonic())))
            except asyncio.TimeoutError: continue
            if m.get("type")=="trade": writer.write(trade_record(ex,symbol,m.get("trade_timestamp") or m.get("timestamp"),m.get("trade_price"),m.get("trade_volume"),m.get("ask_bid"),m,m.get("sequential_id")))
            elif m.get("type")=="orderbook":
                u=m.get("orderbook_units") or []; writer.write(book_record(ex,symbol,m.get("timestamp"),[[x.get("bid_price"),x.get("bid_size")] for x in u],[[x.get("ask_price"),x.get("ask_size")] for x in u],m))


async def collect_bybit(writer, duration):
    ex,symbol,uri="bybit","BTC/USDT","wss://stream.bybit.com/v5/public/spot"; state=BookState()
    req={"op":"subscribe","args":["publicTrade.BTCUSDT","orderbook.50.BTCUSDT"]}
    async with websockets.connect(uri,open_timeout=5,ping_interval=20) as ws:
        await ws.send(json.dumps(req)); end=time.monotonic()+duration
        while time.monotonic()<end:
            try: m=await recv_json(ws,min(5,max(.2,end-time.monotonic())))
            except asyncio.TimeoutError: continue
            topic=m.get("topic","")
            if topic.startswith("publicTrade."):
                for t in m.get("data") or []: writer.write(trade_record(ex,symbol,t.get("T") or m.get("ts"),t.get("p"),t.get("v"),t.get("S"),t,t.get("i")))
            elif topic.startswith("orderbook."):
                d=m.get("data") or {}; action=m.get("type") or "delta"; writer.write(book_record(ex,symbol,d.get("cts") or m.get("cts") or m.get("ts"),d.get("b") or [],d.get("a") or [],m,state,action))


async def collect_bitget(writer, duration):
    ex,symbol,uri="bitget","BTC/USDT","wss://ws.bitget.com/v2/ws/public"
    req={"op":"subscribe","args":[{"instType":"SPOT","channel":"trade","instId":"BTCUSDT"},{"instType":"SPOT","channel":"books5","instId":"BTCUSDT"}]}
    async with websockets.connect(uri,open_timeout=5,ping_interval=20) as ws:
        await ws.send(json.dumps(req)); end=time.monotonic()+duration
        while time.monotonic()<end:
            try: m=await recv_json(ws,min(5,max(.2,end-time.monotonic())))
            except asyncio.TimeoutError: continue
            ch=(m.get("arg") or {}).get("channel",""); data=m.get("data") or []
            if ch=="trade":
                for t in data:
                    if isinstance(t,dict): writer.write(trade_record(ex,symbol,t.get("ts"),t.get("price"),t.get("size"),t.get("side"),t,t.get("tradeId")))
                    elif isinstance(t,list) and len(t)>=4: writer.write(trade_record(ex,symbol,t[0],t[1],t[2],t[3],t,t[4] if len(t)>4 else None))
            elif ch.startswith("books"):
                for d in data:
                    if isinstance(d,dict): writer.write(book_record(ex,symbol,d.get("ts"),d.get("bids") or [],d.get("asks") or [],m,action=m.get("action") or "snapshot"))


async def run_collector(fn,writer,duration,errors):
    name=fn.__name__.replace("collect_","")
    try: await fn(writer,duration)
    except Exception as e: errors[name]=f"{type(e).__name__}: {e}"


async def main_async(duration,out_root):
    rid=run_id(); out_dir=Path(out_root)/rid; writer=Writer(out_dir); errors={}; started=now_ms()
    collectors=[collect_upbit,collect_bithumb,collect_bybit,collect_bitget]
    try: await asyncio.gather(*(run_collector(fn,writer,duration,errors) for fn in collectors))
    finally: writer.close()
    summary={"version":"0.5","mode":"PUBLIC DATA ONLY / NO API KEYS / NO ORDERS","run_id":rid,"started_ms":started,"ended_ms":now_ms(),"duration_sec":duration,"counts":{e:dict(v) for e,v in writer.counts.items()},"quality":{e:dict(v) for e,v in writer.quality.items()},"errors":errors,"minimum_sensor_rule":"trade > 0 and orderbook > 0 and invalid_book == 0 preferred","note":"Observable microstructure fingerprints do not establish actor identity or prove wash trading."}
    with open(out_dir/"summary.json","w",encoding="utf-8") as f: json.dump(summary,f,ensure_ascii=False,indent=2)
    print("MAGI Liquidity Fingerprint Raw Collector v0.5"); print(f"run_id={rid} duration={duration}s out={out_dir}"); print("="*92)
    for ex in ["upbit","bithumb","bybit","bitget"]:
        c=summary["counts"].get(ex,{}); q=summary["quality"].get(ex,{}); tr,ob=c.get("trade",0),c.get("orderbook",0)
        print(f"{'PASS' if tr and ob else 'FAIL':4} {ex:10} trades={tr:<7} orderbook={ob:<7} invalid_book={q.get('invalid_book',0)} ts_null={q.get('timestamp_null',0)}")
        if ex in errors: print(f"     note: {errors[ex]}")
    print("="*92); print("v0.5: timestamp units normalized, recv_monotonic_ns retained, zero-size levels filtered, Bybit snapshot/delta book state reconstructed.")


def main():
    p=argparse.ArgumentParser(); p.add_argument("--duration",type=int,default=int(os.getenv("MAGI_CAPTURE_SEC","60"))); p.add_argument("--out",default=os.getenv("MAGI_OUT_DIR","data/raw")); a=p.parse_args(); asyncio.run(main_async(max(5,min(a.duration,300)),a.out))

if __name__=="__main__": main()
