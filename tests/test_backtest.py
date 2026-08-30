import unittest
import pandas as pd

from backtest import run_backtest


class BacktestTests(unittest.TestCase):
    def test_long_hits_tp(self):
        df = pd.DataFrame({
            "open": [100, 100, 101, 102],
            "high": [101, 101.5, 102, 104],
            "low": [99, 99.5, 100.5, 101],
            "close": [100, 101, 102, 103],
        })
        def signal(_):
            return {"decision": "LONG", "entry": 100, "stop": 98, "tp1": 102}
        r = run_backtest(df, "TEST", signal)
        self.assertEqual(r["trades"], 1)
        self.assertEqual(r["wins"], 1)
        self.assertEqual(r["pnl"], 2.0)

    def test_short_hits_stop_conservatively(self):
        df = pd.DataFrame({
            "open": [100, 100, 101],
            "high": [101, 103, 103],
            "low": [99, 99, 100],
            "close": [100, 101, 102],
        })
        def signal(_):
            return {"decision": "SHORT", "entry": 100, "stop": 102, "tp1": 98}
        r = run_backtest(df, "TEST", signal)
        self.assertEqual(r["trades"], 1)
        self.assertEqual(r["losses"], 1)
        self.assertEqual(r["pnl"], -2.0)


if __name__ == "__main__":
    unittest.main()
