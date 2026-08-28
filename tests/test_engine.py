import unittest

from engine import build_signal


class BuildSignalTests(unittest.TestCase):
    def analysis(self, score=2, atr=100):
        return {"score": score, "atr": atr, "reasons": ["test"]}

    def test_long_has_targets_and_valid_risk_reward(self):
        analyses = {tf: self.analysis(2, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal(
            "BTCUSDT",
            {"last": 10000},
            {"imbalance": 0.2},
            {"buy_ratio": 0.6},
            analyses,
        )
        self.assertEqual(result["decision"], "LONG")
        self.assertEqual(result["entry"], 10000)
        self.assertEqual(result["stop"], 9850)
        self.assertEqual(result["tp1"], 10225)
        self.assertEqual(result["tp2"], 10375)

    def test_short_has_targets(self):
        analyses = {tf: self.analysis(-2, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal(
            "BTCUSDT",
            {"last": 10000},
            {"imbalance": -0.2},
            {"buy_ratio": 0.4},
            analyses,
        )
        self.assertEqual(result["decision"], "SHORT")
        self.assertEqual(result["stop"], 10150)
        self.assertEqual(result["tp1"], 9775)
        self.assertEqual(result["tp2"], 9625)

    def test_weak_signal_is_no_trade(self):
        analyses = {tf: self.analysis(0, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal(
            "BTCUSDT",
            {"last": 10000},
            {"imbalance": 0},
            {"buy_ratio": 0.5},
            analyses,
        )
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["stop"])
        self.assertIsNone(result["tp1"])
        self.assertIsNone(result["tp2"])


if __name__ == "__main__":
    unittest.main()
