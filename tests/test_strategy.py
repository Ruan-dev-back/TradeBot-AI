from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_data/strategies"))
from SmaRsiStrategy import SmaRsiStrategy


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "user_data/config.json").read_text())
        self.strategy = SmaRsiStrategy(self.config)

    def signal_frame(self, rsi=60, volume=1):
        return pd.DataFrame({"sma_fast": [9., 11., 12.], "sma_slow": [10., 10., 10.],
                             "rsi": [float(rsi)] * 3, "volume": [float(volume)] * 3})

    def test_entry_requires_a_new_cross(self):
        result = self.strategy.populate_entry_trend(self.signal_frame(), {})
        self.assertEqual(result["enter_long"].tolist(), [0, 1, 0])

    def test_rsi_entry_boundaries(self):
        for rsi, signal in ((49.99, 0), (50, 1), (69.99, 1), (70, 0), (float("nan"), 0)):
            with self.subTest(rsi=rsi):
                result = self.strategy.populate_entry_trend(self.signal_frame(rsi), {})
                self.assertEqual(result["enter_long"].iloc[1], signal)

    def test_zero_volume_prevents_entry_and_exit(self):
        frame = self.signal_frame(rsi=80, volume=0)
        frame = self.strategy.populate_entry_trend(frame, {})
        frame = self.strategy.populate_exit_trend(frame, {})
        self.assertEqual(frame["enter_long"].sum(), 0)
        self.assertEqual(frame["exit_long"].sum(), 0)

    def test_exit_on_downward_cross_even_with_loss(self):
        frame = self.signal_frame()
        frame["sma_fast"] = [11., 9., 8.]
        result = self.strategy.populate_exit_trend(frame, {})
        self.assertEqual(result["exit_long"].tolist(), [0, 1, 0])
        self.assertFalse(self.strategy.exit_profit_only)

    def test_exit_at_rsi_75(self):
        result = self.strategy.populate_exit_trend(self.signal_frame(rsi=75), {})
        self.assertEqual(result["exit_long"].tolist(), [1, 1, 1])

    def test_missing_indicators_do_not_create_entry(self):
        frame = self.signal_frame()
        frame.loc[:, ["sma_fast", "sma_slow", "rsi"]] = float("nan")
        self.assertEqual(self.strategy.populate_entry_trend(frame, {})["enter_long"].sum(), 0)

    def test_risk_parameters(self):
        self.assertEqual(self.strategy.stoploss, -0.05)
        self.assertEqual(self.strategy.minimal_roi, {})
        self.assertFalse(self.strategy.can_short)
        self.assertFalse(self.strategy.trailing_stop)
        self.assertFalse(self.strategy.position_adjustment_enable)
        self.assertFalse(self.strategy.order_types["stoploss_on_exchange"])

    def test_indicators_and_signals_do_not_depend_on_future_candles(self):
        index = np.arange(800)
        close = 100 + np.cumsum(np.random.default_rng(42).normal(0.01, 1, size=len(index)))
        frame = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=800, freq="1h", tz="UTC"),
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(800),
        })
        def analyze(data):
            data = self.strategy.populate_indicators(data.copy(), {})
            data = self.strategy.populate_entry_trend(data, {})
            return self.strategy.populate_exit_trend(data, {})
        complete = analyze(frame)
        self.assertGreater(complete["enter_long"].sum(), 0)
        for length in (250, 500, 700):
            with self.subTest(length=length):
                assert_frame_equal(complete.iloc[:length], analyze(frame.iloc[:length]))

    def test_additional_entry_guard_refuses_live_short_and_wrong_pair(self):
        def confirm(strategy, pair="BTC/USDT", side="long"):
            return strategy.confirm_trade_entry(pair, "market", 0.01, 100,
                "GTC", datetime.now(timezone.utc), "test", side)
        self.assertTrue(confirm(self.strategy))
        self.assertFalse(confirm(self.strategy, side="short"))
        self.assertFalse(confirm(self.strategy, pair="ETH/USDT"))
        config = deepcopy(self.config)
        config["dry_run"] = False
        self.assertFalse(confirm(SmaRsiStrategy(config)))


if __name__ == "__main__":
    unittest.main()
