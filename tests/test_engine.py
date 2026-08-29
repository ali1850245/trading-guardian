import unittest

from engine import TIMEFRAMES, build_signal, higher_timeframe_context, targets


class BuildSignalTests(unittest.TestCase):
    TIMEFRAME_NAMES = tuple(TIMEFRAMES.keys())

    def analysis(self, score=4, atr=100):
        return {"score": score, "atr": atr, "bullish_votes": 1 if score > 0 else 0,
                "bearish_votes": 1 if score < 0 else 0, "reasons": ["test"]}

    def market(self): return {"last": 10000}
    def depth(self, imbalance=0.0, spread_pct=0.1): return {"imbalance": imbalance, "spread_pct": spread_pct}
    def all_bullish(self, score=4): return {tf: self.analysis(score) for tf in self.TIMEFRAME_NAMES}
    def all_bearish(self, score=-4): return {tf: self.analysis(score) for tf in self.TIMEFRAME_NAMES}

    def test_expected_timeframe_hierarchy_exists(self):
        self.assertEqual(self.TIMEFRAME_NAMES, ("5m", "10m", "15m", "30m", "1h", "4h", "1d"))
        self.assertEqual(TIMEFRAMES["1d"]["role"], "macro")
        self.assertEqual(TIMEFRAMES["10m"]["role"], "trigger")

    def test_long_has_targets(self):
        r = build_signal("BTCUSDT", self.market(), self.depth(0.2), {"buy_ratio": 0.6},
                         {"funding_rate": 0.0}, self.all_bullish())
        self.assertEqual(r["decision"], "LONG")
        self.assertEqual(r["entry"], 10000)
        self.assertEqual(r["stop"], 9850)
        self.assertEqual(r["tp1"], 10180)
        self.assertEqual(r["tp2"], 10300)
        self.assertEqual(r["tp3"], 10450)

    def test_short_has_targets(self):
        r = build_signal("BTCUSDT", self.market(), self.depth(-0.2), {"buy_ratio": 0.4},
                         {"funding_rate": 0.0}, self.all_bearish())
        self.assertEqual(r["decision"], "SHORT")
        self.assertEqual(r["stop"], 10150)
        self.assertEqual(r["tp1"], 9820)
        self.assertEqual(r["tp2"], 9700)
        self.assertEqual(r["tp3"], 9550)

    def test_weak_signal_is_no_trade(self):
        r = build_signal("BTCUSDT", self.market(), self.depth(), {"buy_ratio": 0.5},
                         {"funding_rate": 0.0}, {tf: self.analysis(0) for tf in self.TIMEFRAME_NAMES})
        self.assertEqual(r["decision"], "NO TRADE")
        self.assertIsNone(r["entry"])

    def test_missing_timeframes_force_no_trade(self):
        r = build_signal("BTCUSDT", self.market(), self.depth(0.2), {"buy_ratio": 0.6},
                         {"funding_rate": 0.0}, {"15m": self.analysis(4), "1h": self.analysis(4)})
        self.assertEqual(r["decision"], "NO TRADE")
        self.assertIn("حداقل ۵ تایم‌فریم", r["reason"])

    def test_wide_spread_blocks_trade(self):
        r = build_signal("BTCUSDT", self.market(), {"imbalance": 0.2, "spread_pct": 1.0},
                         {"buy_ratio": 0.6}, {"funding_rate": 0.0}, self.all_bullish())
        self.assertEqual(r["decision"], "NO TRADE")

    def test_macro_structure_conflict_blocks_trade(self):
        a = self.all_bullish()
        a["1d"] = self.analysis(-4)
        r = build_signal("BTCUSDT", self.market(), self.depth(), {"buy_ratio": 0.5},
                         {"funding_rate": 0.0}, a)
        self.assertEqual(r["decision"], "NO TRADE")

    def test_higher_timeframe_context(self):
        c = higher_timeframe_context(self.all_bullish())
        self.assertEqual(c["macro_direction"], 1)
        self.assertEqual(c["structure_direction"], 1)
        self.assertEqual(c["bias"], 1)


class TargetTests(unittest.TestCase):
    def test_no_trade_has_no_levels(self):
        r = targets(10000, 100, "NO TRADE")
        self.assertIsNone(r["entry"])
        self.assertIsNone(r["stop"])
        self.assertIsNone(r["tp1"])

    def test_risk_reward_levels_are_monotonic(self):
        r = targets(10000, 100, "LONG")
        self.assertLess(r["risk_reward_tp1"], r["risk_reward_tp2"])
        self.assertLess(r["risk_reward_tp2"], r["risk_reward_tp3"])


if __name__ == "__main__":
    unittest.main()
