from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import List, Optional


class ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"


@dataclass
class ExchangeHealth:
    exchange: str
    stale_after_ms: int = 5000
    state: ConnectionState = ConnectionState.DISCONNECTED
    last_recv_ms: Optional[int] = None
    last_exchange_ms: Optional[int] = None
    reconnect_count: int = 0
    message_count: int = 0
    error_count: int = 0
    sequence_gap_count: int = 0
    observed_delta_ms: List[int] = field(default_factory=list)

    def on_connect(self) -> None:
        self.state = ConnectionState.CONNECTED

    def on_disconnect(self) -> None:
        self.state = ConnectionState.DISCONNECTED

    def on_reconnect(self) -> None:
        self.reconnect_count += 1
        self.state = ConnectionState.CONNECTED

    def on_error(self) -> None:
        self.error_count += 1
        if self.state != ConnectionState.DISCONNECTED:
            self.state = ConnectionState.DEGRADED

    def on_sequence_gap(self) -> None:
        self.sequence_gap_count += 1
        self.state = ConnectionState.DEGRADED

    def on_message(self, recv_ms: int, exchange_ms: Optional[int] = None) -> None:
        self.last_recv_ms = recv_ms
        self.last_exchange_ms = exchange_ms
        self.message_count += 1
        if exchange_ms is not None:
            self.observed_delta_ms.append(recv_ms - exchange_ms)
            if len(self.observed_delta_ms) > 5000:
                del self.observed_delta_ms[:1000]
        if self.state in {ConnectionState.STALE, ConnectionState.DEGRADED, ConnectionState.DISCONNECTED}:
            self.state = ConnectionState.CONNECTED

    def refresh(self, now_ms: int) -> ConnectionState:
        if self.state == ConnectionState.DISCONNECTED:
            return self.state
        if self.last_recv_ms is None or now_ms - self.last_recv_ms > self.stale_after_ms:
            self.state = ConnectionState.STALE
        return self.state

    @property
    def signal_eligible(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    def snapshot(self, now_ms: int) -> dict:
        self.refresh(now_ms)
        values = sorted(self.observed_delta_ms)
        p95 = None
        if values:
            p95 = values[min(len(values) - 1, int((len(values) - 1) * 0.95))]
        return {
            "exchange": self.exchange,
            "state": self.state.value,
            "last_recv_ms": self.last_recv_ms,
            "last_exchange_ms": self.last_exchange_ms,
            "reconnect_count": self.reconnect_count,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "sequence_gap_count": self.sequence_gap_count,
            "observed_delta_p50_ms": median(values) if values else None,
            "observed_delta_p95_ms": p95,
            "signal_eligible": self.signal_eligible,
        }
