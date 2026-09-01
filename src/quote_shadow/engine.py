from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import sqrt
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class QuoteShadowSignal:
    symbol: str
    leader: str
    follower: str
    ts_ms: int
    lag_ms: Optional[int]
    quote_similarity: float
    direction_agreement: float
    follower_move_bps: float
    leader_move_bps: float
    dependency_score: float
    dependency_break: bool


class QuoteShadowEngine:
    """Research detector for leader/follower quote dependency.

    It measures observable quote co-movement and lag. It does not infer a
    particular LP, account, routing arrangement, or manipulation mechanism.
    """

    def __init__(self, window_ms: int = 5000, break_threshold: float = 0.65):
        self.window_ms = window_ms
        self.break_threshold = break_threshold
        self.books: Dict[Tuple[str, str], Deque[dict]] = defaultdict(deque)
        self.baseline_dependency: Dict[Tuple[str, str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=500))

    @staticmethod
    def _mid(book: dict) -> Optional[float]:
        bid = book.get("best_bid")
        ask = book.get("best_ask")
        if bid is None or ask is None or bid <= 0 or ask <= bid:
            return None
        return (float(bid) + float(ask)) / 2.0

    @staticmethod
    def _bps(a: float, b: float) -> float:
        return ((b / a) - 1.0) * 10000.0 if a else 0.0

    @staticmethod
    def _corr(xs: List[float], ys: List[float]) -> float:
        n = min(len(xs), len(ys))
        if n < 3:
            return 0.0
        xs, ys = xs[-n:], ys[-n:]
        mx, my = sum(xs) / n, sum(ys) / n
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        if vx <= 0 or vy <= 0:
            return 0.0
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        return max(-1.0, min(1.0, cov / sqrt(vx * vy)))

    def on_book(self, event: dict) -> None:
        if event.get("event") not in {"orderbook", "book", "book_snapshot", "book_delta"} and event.get("event_type") not in {"orderbook", "book", "book_snapshot", "book_delta"}:
            return
        if event.get("book_valid") is False:
            return
        ex = event.get("exchange")
        symbol = event.get("symbol") or event.get("symbol_canonical")
        ts = int(event.get("recv_ts_ms") or 0)
        if not ex or not symbol or not ts or self._mid(event) is None:
            return
        q = self.books[(ex, symbol)]
        q.append(event)
        cutoff = ts - self.window_ms * 3
        while q and int(q[0].get("recv_ts_ms") or 0) < cutoff:
            q.popleft()

    def compare(self, symbol: str, leader: str, follower: str, ts_ms: int, lag_candidates_ms=(0, 50, 100, 250, 500, 1000)) -> Optional[QuoteShadowSignal]:
        lq = list(self.books.get((leader, symbol), []))
        fq = list(self.books.get((follower, symbol), []))
        if len(lq) < 4 or len(fq) < 4:
            return None

        leader_series = [(int(x["recv_ts_ms"]), self._mid(x)) for x in lq if self._mid(x) is not None and int(x["recv_ts_ms"]) >= ts_ms - self.window_ms]
        follower_series = [(int(x["recv_ts_ms"]), self._mid(x)) for x in fq if self._mid(x) is not None and int(x["recv_ts_ms"]) >= ts_ms - self.window_ms]
        if len(leader_series) < 3 or len(follower_series) < 3:
            return None

        best = (None, -2.0, [], [])
        for lag in lag_candidates_ms:
            lx, fy = [], []
            for lts, lm in leader_series:
                target = lts + lag
                nearest = min(follower_series, key=lambda x: abs(x[0] - target))
                if abs(nearest[0] - target) <= max(50, lag // 2 + 25):
                    lx.append(lm)
                    fy.append(nearest[1])
            if len(lx) < 3:
                continue
            lr = [self._bps(a, b) for a, b in zip(lx, lx[1:])]
            fr = [self._bps(a, b) for a, b in zip(fy, fy[1:])]
            corr = self._corr(lr, fr)
            if corr > best[1]:
                best = (lag, corr, lr, fr)

        lag, corr, lr, fr = best
        if lag is None or not lr or not fr:
            return None
        agreements = [1.0 if (a == 0 and b == 0) or a * b > 0 else 0.0 for a, b in zip(lr, fr)]
        direction_agreement = sum(agreements) / len(agreements)
        dependency_score = max(0.0, min(1.0, 0.7 * max(corr, 0.0) + 0.3 * direction_agreement))

        key = (symbol, leader, follower)
        baseline = self.baseline_dependency[key]
        baseline_mean = sum(baseline) / len(baseline) if baseline else dependency_score
        baseline.append(dependency_score)
        dependency_break = len(baseline) >= 20 and baseline_mean >= self.break_threshold and dependency_score < max(0.25, baseline_mean - 0.35)

        return QuoteShadowSignal(
            symbol=symbol,
            leader=leader,
            follower=follower,
            ts_ms=ts_ms,
            lag_ms=int(lag),
            quote_similarity=round(max(corr, 0.0), 4),
            direction_agreement=round(direction_agreement, 4),
            follower_move_bps=round(sum(fr), 4),
            leader_move_bps=round(sum(lr), 4),
            dependency_score=round(dependency_score * 100.0, 2),
            dependency_break=dependency_break,
        )
