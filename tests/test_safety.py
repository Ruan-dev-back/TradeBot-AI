import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from safety import PERIODS, validate_config
from research_entrypoint import build_command


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "user_data/config.json").read_text())

    def test_checked_in_config_is_research_only(self):
        validate_config(self.config, {})

    def test_live_futures_and_wallet_changes_are_refused(self):
        for name, value in (("dry_run", False), ("dry_run", 1),
                            ("trading_mode", "futures"), ("margin_mode", "isolated"),
                            ("dry_run_wallet", 2000), ("force_entry_enable", True)):
            with self.subTest(name=name, value=value):
                config = deepcopy(self.config)
                config[name] = value
                with self.assertRaises(ValueError):
                    validate_config(config, {})

    def test_credentials_and_ccxt_overrides_are_refused(self):
        for name in ("key", "secret", "api_key", "apiKey", "password", "privateKey"):
            with self.subTest(name=name):
                config = deepcopy(self.config)
                config["exchange"][name] = "synthetic-test-value"
                with self.assertRaises(ValueError):
                    validate_config(config, {})
        config = deepcopy(self.config)
        config["exchange"]["ccxt_config"]["apiKey"] = "synthetic-test-value"
        with self.assertRaises(ValueError):
            validate_config(config, {})

    def test_environment_override_is_refused(self):
        with self.assertRaises(ValueError):
            validate_config(self.config, {"FREQTRADE__DRY_RUN": "false"})

    def test_strategy_overrides_are_refused(self):
        config = deepcopy(self.config)
        config["stoploss"] = -0.99
        with self.assertRaises(ValueError):
            validate_config(config, {})

    def test_periods_are_disjoint_and_ordered(self):
        self.assertLess(PERIODS["development"][0], PERIODS["development"][1])
        self.assertEqual(PERIODS["development"][1], PERIODS["validation"][0])
        self.assertLess(PERIODS["validation"][0], PERIODS["validation"][1])

    def test_cli_refuses_trade_and_alternate_configs(self):
        for args in (["trade"], ["backtesting", "--config", "/tmp/other.json"],
                     ["backtesting", "--strategy", "Other"],
                     ["backtesting", "--output-dir", "/tmp/escape"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    build_command(args)
                self.assertEqual(error.exception.code, 2)

    def test_backtest_builds_fixed_period_and_fee(self):
        command = build_command(["backtesting", "--period", "validation"])
        self.assertEqual(command[0:2], ["freqtrade", "backtesting"])
        for flag, value in (("--timerange", "20250101-20250701"),
                            ("--fee", "0.001"), ("--cache", "none"),
                            ("--strategy", "SmaRsiStrategy")):
            self.assertEqual(command[command.index(flag) + 1], value)


if __name__ == "__main__":
    unittest.main()
