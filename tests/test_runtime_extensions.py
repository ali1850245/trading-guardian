import unittest
import pandas as pd

import runtime_extensions as ext
import engine


class RuntimeExtensionTests(unittest.TestCase):
    def test_2d_aggregation_builds_closed_pairs(self):
        daily = pd.DataFrame({
            "timestamp": [1, 2, 3, 4],
            "open": [10, 12, 14, 13],
            "high": [13, 15, 16, 17],
            "low": [9, 11, 12, 12],
            "close": [12, 14, 13, 16],
            "volume": [1, 2, 3, 4],
        })
        old = ext._original_get_candles
        try:
            ext._original_get_candles = lambda symbol, resolution, limit: daily
            out = ext.get_candles("BTCUSDT", "2D", 2)
        finally:
            ext._original_get_candles = old
        self.assertEqual(len(out), 2)
        self.assertEqual(float(out.iloc[0]["open"]), 10)
        self.assertEqual(float(out.iloc[0]["high"]), 15)
        self.assertEqual(float(out.iloc[0]["low"]), 9)
        self.assertEqual(float(out.iloc[0]["close"]), 14)
        self.assertEqual(float(out.iloc[0]["volume"]), 3)

    def test_2d_is_registered_as_macro(self):
        self.assertIn("2d", engine.TIMEFRAMES)
        self.assertEqual(engine.TIMEFRAMES["2d"]["role"], "macro")


if __name__ == "__main__":
    unittest.main()
