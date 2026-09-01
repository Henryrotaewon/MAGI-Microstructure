from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PropagationSignal:
    symbol: str
    origin_exchange: str
    follower_exchange: str
    origin_ts_ms: int
    follower_ts_ms: int
    lead_ms: int
    origin_score: float
    follower_score: float
    direction_consensus: float
    propagation_strength: float


class PropagationEngine:
    """Cross-exchange propagation detector fed by exchange-local micro signals."""

    def __init__(self, max_lead_ms: int = 5000, min_origin_score: float = 50.0):
        self.max_lead_ms = max_lead_ms
        self.min_origin_score = min_origin_score
        self.latest: Dict[tuple[str, str], dict] = {}

    def on_micro_signal(self, signal: dict) -> List[PropagationSignal]:
        symbol = signal.get("symbol")
        exchange = signal.get("exchange")
        ts_ms = int(signal.get("ts_ms") or 0)
        score = float(signal.get("score") or 0.0)
        if not symbol or not exchange or not ts_ms:
            return []

        key = (exchange, symbol)
        self.latest[key] = signal
        if score < self.min_origin_score:
            return []

        out: List[PropagationSignal] = []
        for (other_exchange, other_symbol), other in list(self.latest.items()):
            if other_symbol != symbol or other_exchange == exchange:
                continue
            other_ts = int(other.get("ts_ms") or 0)
            if other_ts <= ts_ms:
                continue
            lead_ms = other_ts - ts_ms
            if lead_ms > self.max_lead_ms:
                continue

            other_score = float(other.get("score") or 0.0)
            direction_consensus = self._direction_consensus(signal, other)
            propagation_strength = min(
                100.0,
                0.45 * score + 0.35 * other_score + 20.0 * direction_consensus,
            )
            out.append(
                PropagationSignal(
                    symbol=symbol,
                    origin_exchange=exchange,
                    follower_exchange=other_exchange,
                    origin_ts_ms=ts_ms,
                    follower_ts_ms=other_ts,
                    lead_ms=lead_ms,
                    origin_score=score,
                    follower_score=other_score,
                    direction_consensus=round(direction_consensus, 4),
                    propagation_strength=round(propagation_strength, 4),
                )
            )
        return out

    @staticmethod
    def _direction_consensus(a: dict, b: dict) -> float:
        da = a.get("direction")
        db = b.get("direction")
        if da is None or db is None:
            return 0.0
        return 1.0 if da == db else 0.0
