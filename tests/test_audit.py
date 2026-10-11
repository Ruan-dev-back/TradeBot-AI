from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "user_data/strategies"))
from audit_guard import require_development_dates, require_legacy_research_allowed, require_locked_holdout, verify_baseline
from audit_bias import prefix_differences, read_development_only, rolling_startup
from check_ci import parse_run_page
from run_audit import validate_bias
from SmaRsiStrategy import SmaRsiStrategy


def fixture(dates):
    close = 100 + np.sin(np.arange(len(dates)) / 7) * 5 + np.arange(len(dates)) * .01
    return pd.DataFrame({"date": dates, "open": close, "high": close + 1,
                         "low": close - 1, "close": close, "volume": 10.0})


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs").mkdir()
        policy = {"status": "reserved_locked", "timezone": "UTC", "start": "2025-07-01T00:00:00+00:00",
                  "end_exclusive": "2026-07-01T00:00:00+00:00"}
        (self.root / "docs/holdout-lock.json").write_text(json.dumps(policy))

    def test_legacy_acquisition_and_runner_are_blocked_even_without_docs_mount(self):
        for argv in ([], ["download-data"], ["download-archive"], ["validate-data"], ["backtesting"]):
            with self.subTest(argv=argv), self.assertRaisesRegex(ValueError, "Holdout reservado"):
                require_legacy_research_allowed(argv, self.root)
        require_legacy_research_allowed(["test"], self.root)
        (self.root / "docs/holdout-lock.json").unlink()
        with self.assertRaisesRegex(ValueError, "Holdout reservado"):
            require_legacy_research_allowed(["download-archive"], self.root)

    def test_holdout_unlock_and_date_changes_are_refused(self):
        path = self.root / "docs/holdout-lock.json"
        policy = json.loads(path.read_text())
        require_locked_holdout(self.root)
        for key, value in (("status", "unlocked"), ("start", "2025-07-02T00:00:00+00:00")):
            changed = {**policy, key: value}
            path.write_text(json.dumps(changed))
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_locked_holdout(self.root)

    def test_direct_legacy_scripts_fail_before_acquisition_or_price_reads(self):
        import download_archive
        import offline_backtest
        import validate_data
        for module, guarded_call in ((download_archive, "get_bytes"),
                                     (offline_backtest, "inspect_data"), (validate_data, "inspect_data")):
            with self.subTest(module=module.__name__), patch.object(module, guarded_call) as access:
                with self.assertRaisesRegex(ValueError, "Holdout reservado"):
                    module.main()
                access.assert_not_called()

    def test_baseline_tampering_is_detected(self):
        (self.root / "docs/audit").mkdir()
        data = self.root / "example.txt"
        data.write_text("frozen")
        lock = {"files": {"example.txt": hashlib.sha256(data.read_bytes()).hexdigest()}}
        (self.root / "docs/audit/baseline-lock.json").write_text(json.dumps(lock))
        verify_baseline(self.root)
        data.write_text("modified")
        with self.assertRaisesRegex(ValueError, "Baseline publicada alterada"):
            verify_baseline(self.root)

    def test_utc_and_exclusive_development_boundary_are_required(self):
        require_development_dates([datetime(2024, 1, 1, tzinfo=timezone.utc)])
        for date in (datetime(2024, 1, 1), datetime(2025, 1, 1, tzinfo=timezone.utc),
                     datetime(2025, 7, 1, tzinfo=timezone.utc)):
            with self.subTest(date=date), self.assertRaises(ValueError):
                require_development_dates([date])

    def test_arrow_scanner_excludes_held_out_and_observed_2025_prices(self):
        # Valores sintéticos inválidos em 2025 detectariam um vazamento ao validador.
        dates = pd.date_range("2023-12-01", "2025-07-02", freq="1h", tz="UTC", inclusive="left")
        data = fixture(dates)
        data.loc[data["date"] >= pd.Timestamp("2025-01-01", tz="UTC"), "close"] = -999
        path = self.root / "synthetic.feather"
        data.to_feather(path)
        filtered = read_development_only(path)
        self.assertEqual(len(filtered), 9528)
        self.assertEqual(str(filtered["date"].iloc[-1]), "2024-12-31 23:00:00+00:00")

    def test_prefix_negative_control_detects_an_injected_future_indicator(self):
        class FutureStrategy(SmaRsiStrategy):
            def populate_indicators(self, dataframe, metadata):
                data = super().populate_indicators(dataframe, metadata)
                data["sma_fast"] = data["close"].shift(-1)
                return data
        data = fixture(pd.date_range("2024-01-01", periods=160, freq="1h", tz="UTC"))
        differences = prefix_differences(FutureStrategy({}), data, [80, 120])
        self.assertGreater(differences["differences"]["sma_fast"], 0)

    def test_insufficient_recursive_history_fails_with_missing_values(self):
        data = fixture(pd.date_range("2023-12-20", periods=320, freq="1h", tz="UTC"))
        result = rolling_startup(SmaRsiStrategy({}), data, startup=5)
        self.assertGreater(result["missing_values"], 0)
        self.assertFalse(result["passed"])

    def test_ci_requires_exact_commit_and_explicit_success(self):
        sha = "a" * 40
        page = f'<a href="/Ruan-dev-back/TradeBot-AI/commit/{sha}"></a><span class="h4 color-fg-default">Success</span>'
        self.assertEqual(parse_run_page(page, sha), "success")
        self.assertEqual(parse_run_page(page.replace("Success", "Failure"), sha), "failure")
        with self.assertRaises(ValueError):
            parse_run_page(page, "b" * 40)
        with self.assertRaises(ValueError):
            parse_run_page(f'passing badge /Ruan-dev-back/TradeBot-AI/commit/{sha}', sha)

    def test_stale_bias_cache_is_refused(self):
        (self.root / "docs/evidence").mkdir()
        (self.root / "scripts").mkdir()
        for name in ("audit_bias.py", "offline_backtest.py"):
            (self.root / "scripts" / name).write_text(name)
        (self.root / "docs/evidence/data_manifest.json").write_text(json.dumps({"sha256": "source-sha"}))
        summary = {"baseline_files": {"x": "sha"}, "period": "20240101-20250101",
                   "holdout_prices_inspected": False, "passed": True, "candles": 9528,
                   "source_dataset_sha256": "source-sha", "first": "2023-12-01 00:00:00+00:00",
                   "last": "2024-12-31 23:00:00+00:00",
                   "audit_script_sha256": hashlib.sha256(b"audit_bias.py").hexdigest(),
                   "offline_adapter_sha256": hashlib.sha256(b"offline_backtest.py").hexdigest()}
        lock = {"files": {"x": "sha"}}
        validate_bias(summary, lock, self.root)
        for field, value in (("baseline_files", {"x": "different"}), ("holdout_prices_inspected", True),
                             ("audit_script_sha256", "different"), ("last", "2025-07-01 00:00:00+00:00")):
            changed = {**summary, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_bias(changed, lock, self.root)


if __name__ == "__main__":
    unittest.main()
