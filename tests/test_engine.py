import unittest

from engine import build_signal, calculate_targets


class BuildSignalTests(unittest.TestCase):
    def analysis(self, score=2, atr=100):
        return {"score": score, "atr": atr, "reasons": ["test"]}

    def market(self):
        return {"last": 10000}

    def depth(self, imbalance=0.0, spread_pct=0.1):
        return {"imbalance": imbalance, "spread_pct": spread_pct}

    def test_long_has_targets(self):
        analyses = {tf: self.analysis(4, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), self.depth(0.2), {"buy_ratio": 0.6}, {}, analyses)
        self.assertEqual(result["decision"], "LONG")
        self.assertEqual(result["entry"], 10000)
        self.assertEqual(result["stop"], 9850)
        self.assertIsNotNone(result["tp1"])
        self.assertIsNotNone(result["tp2"])
        self.assertIsNotNone(result["tp3"])

    def test_short_has_targets(self):
        analyses = {tf: self.analysis(-4, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), self.depth(-0.2), {"buy_ratio": 0.4}, {}, analyses)
        self.assertEqual(result["decision"], "SHORT")
        self.assertEqual(result["stop"], 10150)
        self.assertIsNotNone(result["tp1"])
        self.assertIsNotNone(result["tp2"])

    def test_weak_signal_is_no_trade(self):
        analyses = {tf: self.analysis(0, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), self.depth(), {"buy_ratio": 0.5}, {}, analyses)
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIsNone(result["entry"])

    def test_missing_timeframes_force_no_trade(self):
        analyses = {"15m": self.analysis(4, 100), "1h": self.analysis(4, 100)}
        result = build_signal("BTCUSDT", self.market(), self.depth(), {"buy_ratio": 0.6}, {}, analyses)
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIn("حداقل ۳ تایم‌فریم", result["reason"])

    def test_wide_spread_blocks_trade(self):
        analyses = {tf: self.analysis(4, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), {"imbalance": 0.2, "spread_pct": 1.0}, {"buy_ratio": 0.6}, {}, analyses)
        self.assertEqual(result["decision"], "NO TRADE")


class TargetTests(unittest.TestCase):
    def test_no_trade_has_no_levels(self):
        import pandas as pd
        frame = pd.DataFrame({"high": [10000], "low": [9900]})
        result = calculate_targets(10000, 100, "NO TRADE", frame)
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["stop"])


if __name__ == "__main__":
    unittest.main()
