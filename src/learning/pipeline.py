from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .outcome_labeler import OutcomeConfig, OutcomeLabeler
from .schema import LabeledSignal, SignalFeatures


class LearningPipeline:
    """Bridge observable research signals into a leakage-safe learning dataset.

    This module does not generate trading orders. It freezes only information
    known at signal time, then later attaches future executable outcomes.
    """

    def __init__(self, config: Optional[OutcomeConfig] = None):
        self.labeler = OutcomeLabeler(config)

    @staticmethod
    def _signal_dict(signal: Any) -> Dict[str, Any]:
        if signal is None:
            return {}
        if isinstance(signal, dict):
            return dict(signal)
        if is_dataclass(signal):
            return asdict(signal)
        return {
            key: getattr(signal, key)
            for key in dir(signal)
            if not key.startswith("_") and not callable(getattr(signal, key))
        }

    def freeze_quote_signal(
        self,
        signal: Any,
        entry_book: dict,
        *,
        venue: Optional[str] = None,
        direction_hint: str = "NEUTRAL",
        connectivity_health: str = "UNKNOWN",
        micro_score: Optional[float] = None,
        liquidity_state: Optional[str] = None,
        propagation_strength: Optional[float] = None,
        follower_confirmation_count: int = 0,
        remaining_response_gap_bps: Optional[float] = None,
        vpd: Optional[float] = None,
        delta_vpd: Optional[float] = None,
        global_consensus: Optional[float] = None,
        market_regime: Optional[str] = None,
        extras: Optional[Dict[str, float | int | str | bool | None]] = None,
    ) -> LabeledSignal:
        s = self._signal_dict(signal)
        ts_ms = int(s.get("ts_ms") or entry_book.get("recv_ts_ms") or 0)
        symbol = s.get("symbol") or entry_book.get("symbol") or entry_book.get("symbol_canonical")
        target_venue = venue or s.get("follower") or entry_book.get("exchange")
        if not ts_ms or not symbol or not target_venue:
            raise ValueError("signal time, canonical symbol, and target venue are required")

        features = SignalFeatures(
            signal_id=str(uuid.uuid4()),
            ts_ms=ts_ms,
            symbol=str(symbol),
            venue=str(target_venue),
            direction_hint=direction_hint,
            connectivity_health=connectivity_health,
            leader=s.get("leader"),
            follower=s.get("follower"),
            dependency_score=s.get("dependency_score"),
            dependency_break=s.get("dependency_break"),
            quote_similarity=s.get("quote_similarity"),
            direction_agreement=s.get("direction_agreement"),
            lag_ms=s.get("lag_ms"),
            propagation_strength=propagation_strength,
            follower_confirmation_count=follower_confirmation_count,
            remaining_response_gap_bps=remaining_response_gap_bps,
            micro_score=micro_score,
            liquidity_state=liquidity_state,
            spread_bps=entry_book.get("spread_bps"),
            best_bid=entry_book.get("best_bid"),
            best_ask=entry_book.get("best_ask"),
            best_bid_qty=entry_book.get("best_bid_qty"),
            best_ask_qty=entry_book.get("best_ask_qty"),
            vpd=vpd,
            delta_vpd=delta_vpd,
            global_consensus=global_consensus,
            market_regime=market_regime,
            extras=extras or {},
        )
        return self.labeler.start(features, entry_book)

    def finalize(self, pending: LabeledSignal, future_books: Iterable[dict]) -> LabeledSignal:
        return self.labeler.finalize(pending, future_books)

    @staticmethod
    def append_jsonl(signal: LabeledSignal, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(signal.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
