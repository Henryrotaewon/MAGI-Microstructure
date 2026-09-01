import unittest

from src.flow_wave.engine import FlowWaveDetector, WaveObservation


class FlowWaveDetectorTest(unittest.TestCase):
    def test_cross_venue_up_wave_and_upbit_gap(self):
        d = FlowWaveDetector(window_ms=10_000, min_volume_burst=2.0, min_micro_score=45, min_venues=3)
        self.assertIsNone(d.on_observation(WaveObservation("aster", "XRP", 1000, "UP", 6.8, 88, 12, .8, True)))
        self.assertIsNone(d.on_observation(WaveObservation("bybit", "XRP", 1380, "UP", 4.2, 79, 9, .6, False)))
        s = d.on_observation(WaveObservation("bitget", "XRP", 2100, "UP", 3.1, 70, 7, .5, False))
        self.assertIsNotNone(s)
        self.assertEqual(s.origin_exchange, "aster")
        self.assertEqual(s.propagation_count, 3)
        self.assertEqual(s.propagation_lags_ms["bybit"], 380)
        self.assertGreater(s.wave_strength, 0)
        self.assertGreater(s.remaining_response_gap_bps, 0)

        s2 = d.on_observation(WaveObservation("upbit", "XRP", 4100, "UP", 2.1, 55, 1, .2, False))
        self.assertIsNotNone(s2)
        self.assertEqual(s2.propagation_count, 4)
        self.assertEqual(s2.target_response_bps, 1)
        self.assertGreater(s2.remaining_response_gap_bps, 0)

    def test_stale_data_is_ignored(self):
        d = FlowWaveDetector(min_venues=2)
        s = d.on_observation(WaveObservation("bybit", "BTC", 1000, "UP", 9, 90, connectivity_health="STALE"))
        self.assertIsNone(s)


if __name__ == "__main__":
    unittest.main()
