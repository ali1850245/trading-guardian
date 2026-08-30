import unittest

from execution import ExecutionBlocked, LiveExecutionAdapter, OrderIntent, PaperExecutionAdapter, intent_from_signal


class ExecutionBoundaryTests(unittest.TestCase):
    def signal(self, side="LONG"):
        return {
            "symbol": "BTCUSDT",
            "decision": side,
            "entry": 100.0,
            "stop": 98.0 if side == "LONG" else 102.0,
            "tp1": 102.0 if side == "LONG" else 98.0,
            "tp2": 104.0 if side == "LONG" else 96.0,
            "tp3": 106.0 if side == "LONG" else 94.0,
            "signal_id": "test-1",
        }

    def test_long_intent_validates(self):
        intent = intent_from_signal(self.signal("LONG"), 0.5)
        self.assertEqual(intent.side, "LONG")
        self.assertEqual(intent.quantity, 0.5)

    def test_short_intent_validates(self):
        intent = intent_from_signal(self.signal("SHORT"), 0.5)
        self.assertEqual(intent.side, "SHORT")

    def test_paper_adapter_is_idempotent(self):
        adapter = PaperExecutionAdapter()
        intent = intent_from_signal(self.signal(), 1.0)
        first = adapter.submit(intent)
        second = adapter.submit(intent)
        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertTrue(second["idempotent"])

    def test_live_adapter_is_disabled(self):
        adapter = LiveExecutionAdapter()
        with self.assertRaises(ExecutionBlocked):
            adapter.submit(intent_from_signal(self.signal(), 1.0))

    def test_invalid_direction_is_rejected(self):
        bad = self.signal("NO TRADE")
        with self.assertRaises(ValueError):
            intent_from_signal(bad, 1.0)

    def test_invalid_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            intent_from_signal(self.signal(), 0)


if __name__ == "__main__":
    unittest.main()
