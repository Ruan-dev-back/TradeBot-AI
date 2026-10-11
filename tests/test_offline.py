from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

from freqtrade.enums import RunMode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from offline_backtest import OfflineResearchBinance


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "user_data/config.json").read_text())
        self.config["runmode"] = RunMode.BACKTEST
        # Fixture sintético somente para testar o adaptador, nunca para backtests.
        self.market = {
            "id": "BTCUSDT", "symbol": "BTC/USDT", "base": "BTC", "quote": "USDT",
            "baseId": "BTC", "quoteId": "USDT", "type": "spot", "spot": True,
            "margin": False, "swap": False, "future": False, "option": False,
            "contract": False, "active": True,
            "precision": {"amount": 0.00001, "price": 0.01},
            "limits": {name: {"min": None, "max": None} for name in ("amount", "price", "cost")},
            "info": {},
        }

    def test_live_dry_run_service_and_futures_are_refused(self):
        for field, value in (("runmode", RunMode.LIVE), ("runmode", RunMode.DRY_RUN),
                              ("dry_run", False), ("trading_mode", "futures")):
            with self.subTest(field=field, value=value):
                config = deepcopy(self.config)
                config[field] = value
                with self.assertRaises(ValueError):
                    OfflineResearchBinance(config, self.market)

    def test_credentials_are_refused(self):
        self.config["exchange"]["key"] = "synthetic-test-only"
        with self.assertRaises(ValueError):
            OfflineResearchBinance(self.config, self.market)

    def test_cached_filters_are_used_and_orders_are_blocked(self):
        exchange = OfflineResearchBinance(self.config, self.market)
        self.addCleanup(exchange.close)
        self.assertEqual(exchange.get_precision_price("BTC/USDT"), 0.01)
        self.assertEqual(exchange.get_precision_amount("BTC/USDT"), 0.00001)
        self.assertIsNone(exchange.get_min_pair_stake_amount("BTC/USDT", 100000, -0.05))
        self.assertTrue(math.isinf(exchange.get_max_pair_stake_amount("BTC/USDT", 100000)))
        for call in (exchange.create_order, exchange.reload_markets, exchange.get_fee):
            with self.assertRaises(RuntimeError):
                call()

    def test_unknown_precision_is_refused(self):
        self.market["precision"]["price"] = None
        with self.assertRaises(ValueError):
            OfflineResearchBinance(self.config, self.market)
