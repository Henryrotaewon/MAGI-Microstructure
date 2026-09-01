from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .schema import HorizonOutcome, LabeledSignal, SignalFeatures


DEFAULT_HORIZONS_MS = (100, 250, 500, 1000, 2000, 5000, 10000, 30000, 60000, 300000)


def bps(a: float, b: float) -> float:
    return ((b / a) - 1.0) * 10000.0 if a else 0.0


@dataclass
class OutcomeConfig:
    horizons_ms: tuple[int, ...] = DEFAULT_HORIZONS_MS
    up_threshold_bps: float = 3.0
    down_threshold_bps: float = -3.0
    taker_fee_bps: float = 0.0
    estimated_slippage_bps: float = 0.0


class OutcomeLabeler:
    """Labels future executable outcomes for research signals.

    Features must be frozen at signal time. Future book observations are used only
    for labels, preventing future leakage into the feature snapshot.

    Long-only executable convention:
      entry = signal-time best ask
      exit  = future best bid

    The configurable fee/slippage values are research assumptions and should be
    replaced by venue/tier-specific values during paper evaluation.
    """

    def __init__(self, config: Optional[OutcomeConfig] = None):
        self.config = config or OutcomeConfig()

    @staticmethod
    def _mid(book: dict) -> Optional[float]:
        bid = book.get("best_bid")
        ask = book.get("best_ask")
        if bid is None or ask is None:
            return None
        bid, ask = float(bid), float(ask)
        if bid <= 0 or ask <= bid:
            return None
        return (bid + ask) / 2.0

    @staticmethod
    def _valid_book(book: dict) -> bool:
        if book.get("book_valid") is False:
            return False
        bid = book.get("best_bid")
        ask = book.get("best_ask")
        try:
            return float(bid) > 0 and float(ask) > float(bid)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _nearest_at_or_after(books: List[dict], target_ts_ms: int) -> Optional[dict]:
        for book in books:
            if int(book.get("recv_ts_ms") or 0) >= target_ts_ms:
                return book
        return None

    def start(self, features: SignalFeatures, entry_book: dict) -> LabeledSignal:
        if not self._valid_book(entry_book):
            raise ValueError("entry_book must contain a valid executable best bid/ask")
        bid = float(entry_book["best_bid"])
        ask = float(entry_book["best_ask"])
        return LabeledSignal(
            features=features,
            entry_ask=ask,
            entry_bid=bid,
            entry_mid=(bid + ask) / 2.0,
        )

    def finalize(self, signal: LabeledSignal, future_books: Iterable[dict]) -> LabeledSignal:
        books = sorted(
            [b for b in future_books if self._valid_book(b)],
            key=lambda x: int(x.get("recv_ts_ms") or 0),
        )
        if not books or signal.entry_ask is None or signal.entry_mid is None:
            return signal

        t0 = signal.features.ts_ms
        signal.outcomes = []

        for horizon in self.config.horizons_ms:
            cutoff = t0 + horizon
            window = [b for b in books if t0 < int(b.get("recv_ts_ms") or 0) <= cutoff]
            exit_book = self._nearest_at_or_after(books, cutoff)
            if exit_book is None:
                signal.outcomes.append(HorizonOutcome(horizon_ms=horizon))
                continue

            exit_bid = float(exit_book["best_bid"])
            exit_ask = float(exit_book["best_ask"])
            exit_mid = (exit_bid + exit_ask) / 2.0
            gross_long = bps(signal.entry_ask, exit_bid)
            gross_mid = bps(signal.entry_mid, exit_mid)

            mids = [self._mid(b) for b in window]
            mids = [m for m in mids if m is not None]
            mfe = max((bps(signal.entry_mid, m) for m in mids), default=None)
            mae = min((bps(signal.entry_mid, m) for m in mids), default=None)

            spread = bps(exit_bid, exit_ask)
            total_cost = (2.0 * self.config.taker_fee_bps) + self.config.estimated_slippage_bps
            net_long = gross_long - total_cost

            if gross_mid >= self.config.up_threshold_bps:
                label = "UP"
            elif gross_mid <= self.config.down_threshold_bps:
                label = "DOWN"
            else:
                label = "FLAT"

            signal.outcomes.append(
                HorizonOutcome(
                    horizon_ms=horizon,
                    exit_bid=exit_bid,
                    exit_ask=exit_ask,
                    exit_mid=exit_mid,
                    gross_long_return_bps=round(gross_long, 6),
                    gross_mid_return_bps=round(gross_mid, 6),
                    mfe_bps=None if mfe is None else round(mfe, 6),
                    mae_bps=None if mae is None else round(mae, 6),
                    spread_bps=round(spread, 6),
                    slippage_bps=self.config.estimated_slippage_bps,
                    fee_bps=2.0 * self.config.taker_fee_bps,
                    net_long_return_bps=round(net_long, 6),
                    direction_label=label,
                )
            )

        signal.finalized = all(o.exit_mid is not None for o in signal.outcomes)
        return signal
