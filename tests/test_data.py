from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_data


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        original_root = validate_data.ROOT
        validate_data.ROOT = Path(self.temp.name)
        self.addCleanup(setattr, validate_data, "ROOT", original_root)
        self.path = validate_data.ROOT / "candles.feather"
        dates = pd.date_range("2023-12-01", "2025-07-01", freq="1h", inclusive="left", tz="UTC")
        price = 100 + np.arange(len(dates)) / 1000
        self.data = pd.DataFrame({"date": dates, "open": price, "high": price + 1,
                                  "low": price - 1, "close": price, "volume": 1.})

    def test_complete_data_and_disjoint_period_counts(self):
        self.data.to_feather(self.path)
        result = validate_data.inspect_data(self.path)
        self.assertEqual(result["periods"]["development"]["candles"], 366 * 24)
        self.assertEqual(result["periods"]["validation"]["candles"], 181 * 24)
        self.assertEqual(len(result["sha256"]), 64)

    def test_gap_is_refused(self):
        self.data.drop(index=1000).reset_index(drop=True).to_feather(self.path)
        with self.assertRaisesRegex(ValueError, "Cobertura"):
            validate_data.inspect_data(self.path)

    def test_duplicate_is_refused(self):
        pd.concat([self.data.iloc[:100], self.data.iloc[99:]], ignore_index=True).to_feather(self.path)
        with self.assertRaisesRegex(ValueError, "duplicados"):
            validate_data.inspect_data(self.path)

    def test_invalid_ohlc_is_refused(self):
        self.data.loc[1000, "high"] = 1
        self.data.to_feather(self.path)
        with self.assertRaisesRegex(ValueError, "OHLC"):
            validate_data.inspect_data(self.path)

    def test_naive_or_unaligned_timestamps_are_refused(self):
        for kind in ("naive", "unaligned"):
            with self.subTest(kind=kind):
                frame = self.data.copy()
                if kind == "naive":
                    frame["date"] = frame["date"].dt.tz_localize(None)
                else:
                    frame["date"] += pd.Timedelta(minutes=1)
                frame.to_feather(self.path)
                with self.assertRaises(ValueError):
                    validate_data.inspect_data(self.path)

    def test_infinite_values_and_short_sample_are_refused(self):
        self.data.loc[20, "close"] = np.inf
        self.data.to_feather(self.path)
        with self.assertRaisesRegex(ValueError, "não finitos"):
            validate_data.inspect_data(self.path)
        self.data.iloc[:200].to_feather(self.path)
        with self.assertRaises(ValueError):
            validate_data.inspect_data(self.path)


if __name__ == "__main__":
    unittest.main()
