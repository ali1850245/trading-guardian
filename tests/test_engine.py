import unittest

from engine import build_signal, paper_result


class BuildSignalTests(unittest.TestCase):
    def analysis(self, score=2, atr=100):
        return {"score": score, "atr": atr, "reasons": ["test"]}

    def market(self):
        return {"last": 10000}

    def depth(self, imbalance=0.0):
        return {"imbalance": imbalance, "spread_pct": 0.1}

    def test_long_has_targets_and_valid_risk_reward(self):
        analyses = {tf: self.analysis(2, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), self.depth(0.2), {"buy_ratio": 0.6}, analyses)
        self.assertEqual(result["decision"], "LONG")
        self.assertEqual(result["entry"], 10000)
        self.assertEqual(result["stop"], 9850)
        self.assertEqual(result["tp1"], 10225)
        self.assertEqual(result["tp2"], 10375)
        self.assertEqual(result["risk_reward_tp1"], 1.5)
        self.assertEqual(result["risk_reward_tp2"], 2.5)

    def test_short_has_targets(self):
        analyses = {tf: self.analysis(-2, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), self.depth(-0.2), {"buy_ratio": 0.4}, analyses)
        self.assertEqual(result["decision"], "SHORT")
        self.assertEqual(result["stop"], 10150)
        self.assertEqual(result["tp1"], 9775)
        self.assertEqual(result["tp2"], 9625)

    def test_weak_signal_is_no_trade(self):
        analyses = {tf: self.analysis(0, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), self.depth(), {"buy_ratio": 0.5}, analyses)
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["stop"])
        self.assertIsNone(result["tp1"])
        self.assertIsNone(result["tp2"])

    def test_missing_timeframes_force_no_trade(self):
        analyses = {"15m": self.analysis(4, 100), "1h": self.analysis(4, 100)}
        result = build_signal("BTCUSDT", self.market(), self.depth(), {"buy_ratio": 0.6}, analyses)
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIn("تایم‌فریم ناقص", result["reason"])

    def test_wide_spread_blocks_trade(self):
        analyses = {tf: self.analysis(2, 100) for tf in ("5m", "15m", "1h", "4h")}
        result = build_signal("BTCUSDT", self.market(), {"imbalance": 0.2, "spread_pct": 1.0}, {"buy_ratio": 0.6}, analyses)
        self.assertEqual(result["decision"], "NO TRADE")
        self.assertIn("اسپرد زیاد", result["reason"])


class PaperResultTests(unittest.TestCase):
    def long_signal(self):
        return {"decision": "LONG", "stop": 9850, "tp1": 10225, "tp2": 10375}

    def short_signal(self):
        return {"decision": "SHORT", "stop": 10150, "tp1": 9775, "tp2": 9625}

    def test_long_stop_has_priority(self):
        self.assertEqual(paper_result(self.long_signal(), 10300, 9800), "STOP")

    def test_long_tp2(self):
        self.assertEqual(paper_result(self.long_signal(), 10400, 9950), "TP2")

    def test_short_stop_has_priority(self):
        self.assertEqual(paper_result(self.short_signal(), 10200, 9600), "STOP")

    def test_short_tp1(self):
        self.assertEqual(paper_result(self.short_signal(), 10000, 9700), "TP1")


if __name__ == "__main__":
    unittest.main()
