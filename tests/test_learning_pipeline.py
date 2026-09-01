import unittest

from src.learning.outcome_labeler import OutcomeConfig
from src.learning.pipeline import LearningPipeline


class LearningPipelineTest(unittest.TestCase):
    def test_freeze_and_finalize_long_outcome(self):
        pipeline = LearningPipeline(
            OutcomeConfig(
                horizons_ms=(1000,),
                up_threshold_bps=3.0,
                down_threshold_bps=-3.0,
                taker_fee_bps=1.0,
                estimated_slippage_bps=0.5,
            )
        )
        quote_signal = {
            "symbol": "BTC/USD",
            "leader": "kraken",
            "follower": "upbit",
            "ts_ms": 1_000_000,
            "lag_ms": 250,
            "quote_similarity": 0.82,
            "direction_agreement": 1.0,
            "dependency_score": 87.0,
            "dependency_break": True,
        }
        entry = {
            "exchange": "upbit",
            "symbol_canonical": "BTC/USD",
            "recv_ts_ms": 1_000_000,
            "best_bid": 100.0,
            "best_ask": 100.1,
            "best_bid_qty": 10.0,
            "best_ask_qty": 9.0,
            "spread_bps": 10.0,
            "book_valid": True,
        }
        pending = pipeline.freeze_quote_signal(
            quote_signal,
            entry,
            direction_hint="UP",
            connectivity_health="CONNECTED",
            micro_score=72.0,
            global_consensus=81.0,
        )
        future = [
            {"recv_ts_ms": 1_000_400, "best_bid": 100.2, "best_ask": 100.3, "book_valid": True},
            {"recv_ts_ms": 1_001_000, "best_bid": 100.5, "best_ask": 100.6, "book_valid": True},
        ]
        labeled = pipeline.finalize(pending, future)

        self.assertTrue(labeled.finalized)
        self.assertEqual(labeled.features.leader, "kraken")
        self.assertEqual(labeled.features.global_consensus, 81.0)
        self.assertEqual(labeled.outcomes[0].direction_label, "UP")
        self.assertGreater(labeled.outcomes[0].gross_long_return_bps, 0)
        self.assertLess(labeled.outcomes[0].net_long_return_bps, labeled.outcomes[0].gross_long_return_bps)

    def test_rejects_invalid_entry_book(self):
        pipeline = LearningPipeline(OutcomeConfig(horizons_ms=(1000,)))
        with self.assertRaises(ValueError):
            pipeline.freeze_quote_signal(
                {"symbol": "BTC/USD", "ts_ms": 1, "follower": "upbit"},
                {"recv_ts_ms": 1, "best_bid": 100.0, "best_ask": 99.0, "book_valid": False},
            )


if __name__ == "__main__":
    unittest.main()
