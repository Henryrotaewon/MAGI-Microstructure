from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class SignalFeatures:
    signal_id: str
    ts_ms: int
    symbol: str
    venue: str
    direction_hint: str = "NEUTRAL"
    connectivity_health: str = "UNKNOWN"

    # Quote dependency / propagation context
    leader: Optional[str] = None
    follower: Optional[str] = None
    dependency_score: Optional[float] = None
    dependency_break: Optional[bool] = None
    quote_similarity: Optional[float] = None
    direction_agreement: Optional[float] = None
    lag_ms: Optional[int] = None
    propagation_strength: Optional[float] = None
    follower_confirmation_count: int = 0
    remaining_response_gap_bps: Optional[float] = None

    # Exchange-local microstructure context
    micro_score: Optional[float] = None
    liquidity_state: Optional[str] = None
    spread_bps: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    best_bid_qty: Optional[float] = None
    best_ask_qty: Optional[float] = None

    # Higher-level optional context
    vpd: Optional[float] = None
    delta_vpd: Optional[float] = None
    global_consensus: Optional[float] = None
    market_regime: Optional[str] = None

    # Extensible feature payload. This must contain only information known at ts_ms.
    extras: Dict[str, float | int | str | bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HorizonOutcome:
    horizon_ms: int
    exit_bid: Optional[float] = None
    exit_ask: Optional[float] = None
    exit_mid: Optional[float] = None
    gross_long_return_bps: Optional[float] = None
    gross_mid_return_bps: Optional[float] = None
    mfe_bps: Optional[float] = None
    mae_bps: Optional[float] = None
    spread_bps: Optional[float] = None
    slippage_bps: Optional[float] = None
    fee_bps: Optional[float] = None
    net_long_return_bps: Optional[float] = None
    direction_label: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LabeledSignal:
    features: SignalFeatures
    entry_ask: Optional[float]
    entry_bid: Optional[float]
    entry_mid: Optional[float]
    outcomes: List[HorizonOutcome] = field(default_factory=list)
    finalized: bool = False

    def to_dict(self) -> dict:
        return {
            "features": self.features.to_dict(),
            "entry_ask": self.entry_ask,
            "entry_bid": self.entry_bid,
            "entry_mid": self.entry_mid,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "finalized": self.finalized,
        }
