from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Deque, Dict, List, Optional


@dataclass
class WaveObservation:
    exchange: str
    symbol: str
    ts_ms: int
    direction: str
    volume_burst: float
    micro_score: float
    price_move_bps: float = 0.0
    liquidity_stress: float = 0.0
    dependency_break: bool = False
    connectivity_health: str = "CONNECTED"


@dataclass
class FlowWaveSignal:
    symbol: str
    direction: str
    origin_exchange: str
    origin_ts_ms: int
    last_ts_ms: int
    venues: List[str]
    propagation_count: int
    propagation_lags_ms: Dict[str, int]
    median_lag_ms: float
    wave_strength: float
    price_reaction_bps: Dict[str, float]
    target_exchange: Optional[str]
    target_response_bps: Optional[float]
    remaining_response_gap_bps: Optional[float]
    dependency_break_count: int

    def to_dict(self) -> dict:
        return asdict(self)


class FlowWaveDetector:
    """Detects cross-venue volume/liquidity waves from public market observations.

    A wave is a research signal. It does not infer actor identity or manipulation.
    The detector intentionally separates flow propagation from price propagation.
    """

    def __init__(
        self,
        window_ms: int = 15_000,
        min_volume_burst: float = 2.0,
        min_micro_score: float = 45.0,
        min_venues: int = 2,
        target_exchange: str = "upbit",
    ):
        self.window_ms = window_ms
        self.min_volume_burst = min_volume_burst
        self.min_micro_score = min_micro_score
        self.min_venues = min_venues
        self.target_exchange = target_exchange
        self.events: Dict[tuple[str, str], Deque[WaveObservation]] = defaultdict(deque)

    def on_observation(self, obs: WaveObservation) -> Optional[FlowWaveSignal]:
        if obs.connectivity_health in {"STALE", "DISCONNECTED"}:
            return None
        direction = obs.direction.upper()
        if direction not in {"UP", "DOWN"}:
            return None
        if obs.volume_burst < self.min_volume_burst and obs.micro_score < self.min_micro_score:
            return None

        key = (obs.symbol, direction)
        q = self.events[key]
        q.append(obs)
        cutoff = obs.ts_ms - self.window_ms
        while q and q[0].ts_ms < cutoff:
            q.popleft()

        # Keep the first qualifying observation per venue as propagation arrival.
        arrivals: Dict[str, WaveObservation] = {}
        for x in q:
            arrivals.setdefault(x.exchange, x)
        if len(arrivals) < self.min_venues:
            return None

        ordered = sorted(arrivals.values(), key=lambda x: x.ts_ms)
        origin = ordered[0]
        lags = {x.exchange: x.ts_ms - origin.ts_ms for x in ordered}
        nonzero_lags = sorted(v for v in lags.values() if v > 0)
        if nonzero_lags:
            n = len(nonzero_lags)
            median_lag = float(nonzero_lags[n // 2]) if n % 2 else (nonzero_lags[n // 2 - 1] + nonzero_lags[n // 2]) / 2.0
        else:
            median_lag = 0.0

        avg_burst = sum(min(x.volume_burst, 10.0) / 10.0 for x in ordered) / len(ordered)
        avg_micro = sum(min(max(x.micro_score, 0.0), 100.0) / 100.0 for x in ordered) / len(ordered)
        avg_stress = sum(min(max(x.liquidity_stress, 0.0), 1.0) for x in ordered) / len(ordered)
        venue_factor = min(len(ordered) / 5.0, 1.0)
        break_factor = sum(1 for x in ordered if x.dependency_break) / len(ordered)
        strength = 100.0 * (
            0.30 * avg_burst
            + 0.25 * avg_micro
            + 0.20 * avg_stress
            + 0.15 * venue_factor
            + 0.10 * break_factor
        )

        price_reaction = {x.exchange: round(x.price_move_bps, 4) for x in ordered}
        target = arrivals.get(self.target_exchange)
        target_response = target.price_move_bps if target else None
        # Use median non-target absolute reaction as a simple research gap baseline.
        peer_moves = [abs(x.price_move_bps) for x in ordered if x.exchange != self.target_exchange]
        peer_reaction = sorted(peer_moves)[len(peer_moves) // 2] if peer_moves else None
        remaining_gap = None
        if peer_reaction is not None:
            remaining_gap = max(0.0, peer_reaction - abs(target_response or 0.0))

        return FlowWaveSignal(
            symbol=obs.symbol,
            direction=direction,
            origin_exchange=origin.exchange,
            origin_ts_ms=origin.ts_ms,
            last_ts_ms=ordered[-1].ts_ms,
            venues=[x.exchange for x in ordered],
            propagation_count=len(ordered),
            propagation_lags_ms=lags,
            median_lag_ms=round(median_lag, 2),
            wave_strength=round(strength, 4),
            price_reaction_bps=price_reaction,
            target_exchange=self.target_exchange,
            target_response_bps=None if target_response is None else round(target_response, 4),
            remaining_response_gap_bps=None if remaining_gap is None else round(remaining_gap, 4),
            dependency_break_count=sum(1 for x in ordered if x.dependency_break),
        )
