from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class MarketEvent:
    exchange: str
    symbol_native: str
    symbol_canonical: str
    event_type: str
    recv_ts_ms: int
    recv_monotonic_ns: int
    exchange_ts_raw: Any = None
    exchange_ts_ms: Optional[int] = None
    exchange_ts_unit: Optional[str] = None
    observed_ts_delta_ms: Optional[int] = None
    sequence: Optional[int] = None
    trade_id: Optional[str] = None
    price: Optional[float] = None
    qty: Optional[float] = None
    side: Optional[str] = None
    best_bid: Optional[float] = None
    best_bid_qty: Optional[float] = None
    best_ask: Optional[float] = None
    best_ask_qty: Optional[float] = None
    spread_bps: Optional[float] = None
    book_valid: Optional[bool] = None
    health_state: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return asdict(self)
