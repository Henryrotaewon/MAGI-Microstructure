from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional


@dataclass
class MicroSignal:
    exchange: str
    symbol: str
    ts_ms: int
    trade_burst: float
    volume_price_dislocation: float
    alternation: float
    absorption: float
    replenishment: float
    imbalance: float
    score: float


class MicroFingerprintEngine:
    """Exchange-local microstructure feature engine.

    Public-data research only. The score represents an observable mechanical
    liquidity fingerprint; it does not establish actor identity or prove wash trading.
    """

    def __init__(self, window_ms: int = 2000, baseline_ms: int = 30000):
        self.window_ms = window_ms
        self.baseline_ms = baseline_ms
        self.trades: Dict[tuple[str, str], Deque[dict]] = {}
        self.books: Dict[tuple[str, str], Deque[dict]] = {}

    def _q(self, store: Dict, key: tuple[str, str]) -> Deque[dict]:
        if key not in store:
            store[key] = deque()
        return store[key]

    @staticmethod
    def _trim(q: Deque[dict], cutoff_ms: int) -> None:
        while q and int(q[0].get("recv_ts_ms", 0)) < cutoff_ms:
            q.popleft()

    def on_event(self, event: dict) -> Optional[MicroSignal]:
        exchange = event.get("exchange")
        symbol = event.get("symbol")
        ts = int(event.get("recv_ts_ms") or 0)
        if not exchange or not symbol or not ts:
            return None

        key = (exchange, symbol)
        if event.get("event_type") == "trade":
            q = self._q(self.trades, key)
            q.append(event)
            self._trim(q, ts - self.baseline_ms)
        elif event.get("event_type") in {"orderbook", "book", "book_snapshot", "book_delta"}:
            q = self._q(self.books, key)
            q.append(event)
            self._trim(q, ts - self.baseline_ms)
        else:
            return None

        return self.compute(exchange, symbol, ts)

    def compute(self, exchange: str, symbol: str, ts_ms: int) -> MicroSignal:
        key = (exchange, symbol)
        trades = list(self._q(self.trades, key))
        books = list(self._q(self.books, key))
        recent = [x for x in trades if int(x.get("recv_ts_ms", 0)) >= ts_ms - self.window_ms]

        baseline_rate = max(len(trades) / max(self.baseline_ms / 1000, 1e-9), 1e-9)
        recent_rate = len(recent) / max(self.window_ms / 1000, 1e-9)
        trade_burst = min(recent_rate / baseline_rate, 10.0) / 10.0

        prices = [float(x["price"]) for x in recent if x.get("price") is not None]
        qtys = [float(x.get("qty") or x.get("amount") or 0.0) for x in recent]
        volume = sum(qtys)
        price_move = 0.0
        if len(prices) >= 2 and prices[0] != 0:
            price_move = abs(prices[-1] / prices[0] - 1.0)
        volume_price_dislocation = min(volume / max(price_move * 1_000_000, 1e-9), 1.0) if volume else 0.0

        sides = [str(x.get("side", "")).lower() for x in recent if x.get("side")]
        flips = sum(1 for a, b in zip(sides, sides[1:]) if a != b)
        alternation = flips / max(len(sides) - 1, 1)

        latest_book = books[-1] if books else {}
        bid = float(latest_book.get("best_bid") or 0.0)
        ask = float(latest_book.get("best_ask") or 0.0)
        bid_qty = float(latest_book.get("best_bid_qty") or 0.0)
        ask_qty = float(latest_book.get("best_ask_qty") or 0.0)
        imbalance = abs(bid_qty - ask_qty) / max(bid_qty + ask_qty, 1e-9)

        # Placeholders are intentionally conservative until stateful book reconstruction is added.
        absorption = 0.0
        replenishment = 0.0

        score = 100.0 * (
            0.25 * trade_burst
            + 0.20 * volume_price_dislocation
            + 0.15 * alternation
            + 0.15 * absorption
            + 0.15 * replenishment
            + 0.10 * imbalance
        )
        return MicroSignal(
            exchange=exchange,
            symbol=symbol,
            ts_ms=ts_ms,
            trade_burst=trade_burst,
            volume_price_dislocation=volume_price_dislocation,
            alternation=alternation,
            absorption=absorption,
            replenishment=replenishment,
            imbalance=imbalance,
            score=round(score, 4),
        )
