import unittest

import pandas as pd

from engine import TIMEFRAMES, build_signal, calculate_targets, higher_timeframe_context


class BuildSignalTests(unittest.TestCase):
    TIMEFRAME_NAMES = tuple(TIMEFRAMES.keys())

    def analysis(self, score=4, atr=100):
        return {
            "score": score,
            "atr": atr,
            "bullish_votes": 1 if score > 0 else 0,
            "bearish_votes": 1 if score < 0 else 0,
            "reasons": ["test"],
        }

    def market(self):
        return {"last": 10000}

    def depth(self, imbalance=0.0, spread_pct=0.1):
        return {"imbalance": imbalance, "spread_pct": spread_pct}

    def all_bullish(self, score=4):
        return {tf: self.analysis(score) for tf in self.TIMEFRAME_NAMES}

    def all_bearish(self, score=-4):
        return {tf: self.analysis(score) for tf in self.TIMEFRAME_NAMES}

    def test_expected_timeframe_hierarchy_exists(self):
        self.assertEqual(
            tuple(TIMEFRAMES.keys()),
            ("5m", "10m", "15m", "30m", "1h", "4h", "1d", "2d"),
        )
        self.assertEqual(TIMEFRAMES["1d"]["role"], "macro")
        self.assertEqual(TIMEFRAMES["2d"]["role"], "macro")
        self.assertEqual(TIMEFRAMES["10m"]["role"], "trigger")

    def test_long_has_targets(self):
        result = build_signal(
            "BTCUSDT",
            self.market(),
            self.depth(0.2),
            {"buy_ratio": 0.6},
            {"funding_rate": 0.0, "open_interest": 1, "liquidations_5m": {"count": 0}},
            self.all_bullish(),
        )
        self.assertEqual(result["decision"], "LONG")
        self.assertEqual(result["entry"], 10000)
        self.assertEqual(result["stop"], 9850)
        self.assertIsNotNone(result["tp1"])
        self.assertIsNotNone(result["tp2"])
        self.assertIsNotNone(result["tp3"])

    def test_short_has_targets(self):
        result = build_signal(
            "BTCUSDT",
            self.market(),
            self.depth(-0.2),
            {"buy_ratio": 0.4},
            {"funding_rate": 0.0, "open_interest": 1, "liquidations_5m": {"count": 0}},
            self.all_bearish(),
        )
        self.assertEqual(result["decision"], "SHORT")
        self.assertEqual(result["stop"], 10150)
        self.assertIsNotNone(result["tp1"])
        self.assertIsNotNone(result["tp2"])

    def test_weak_signal_is_no_trade(self):
        result = build_signal(
            "BTCUSDT",
            self.market(),
            self.depth(),
            {"buy_ratio": 0.5},
            {"funding_rate": 0.0},
            {tf: self.analysis(0) for tf in self.TIMEFRAME_NAMES},
        )
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIsNone(result["entry"])

    def test_missing_timeframes_force_no_trade(self):
        analyses = {
            "15m": self.analysis(4),
            "1h": self.analysis(4),
        }
        result = build_signal(
            "BTCUSDT",
            self.market(),
            self.depth(0.2),
            {"buy_ratio": 0.6},
            {"funding_rate": 0.0},
            analyses,
        )
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIn("حداقل ۵ تایم‌فریم", result["reason"])

    def test_wide_spread_blocks_trade(self):
        result = build_signal(
            "BTCUSDT",
            self.market(),
            {"imbalance": 0.2, "spread_pct": 1.0},
            {"buy_ratio": 0.6},
            {"funding_rate": 0.0},
            self.all_bullish(),
        )
        self.assertEqual(result["decision"], "NO TRADE")

    def test_macro_structure_conflict_blocks_trade(self):
        analyses = self.all_bullish()
        analyses["1d"] = self.analysis(-4)
        analyses["2d"] = self.analysis(-4)
        analyses["1h"] = self.analysis(4)
        analyses["4h"] = self.analysis(4)
        result = build_signal(
            "BTCUSDT",
            self.market(),
            self.depth(),
            {"buy_ratio": 0.5},
            {"funding_rate": 0.0},
            analyses,
        )
        self.assertEqual(result["decision"], "NO TRADE")

    def test_higher_timeframe_context_uses_macro_then_structure(self):
        analyses = self.all_bullish()
        context = higher_timeframe_context(analyses)
        self.assertEqual(context["macro_direction"], 1)
        self.assertEqual(context["structure_direction"], 1)
        self.assertEqual(context["bias"], 1)


class TargetTests(unittest.TestCase):
    def test_no_trade_has_no_levels(self):
        frame = pd.DataFrame({"high": [10000], "low": [9900]})
        result = calculate_targets(10000, 100, "NO TRADE")
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["stop"])


if __name__ == "__main__":
    unittest.main()
