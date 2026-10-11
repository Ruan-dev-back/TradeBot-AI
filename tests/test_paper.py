"""Safety invariants for the isolated real-time simulated trader."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PaperTradingTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "user_data/config.paper.json").read_text(encoding="utf-8"))
        self.compose = (ROOT / "docker-compose.paper.yml").read_text(encoding="utf-8")

    def test_paper_mode_cannot_trade_real_money(self):
        self.assertIs(self.config["dry_run"], True)
        self.assertEqual(self.config["trading_mode"], "spot")
        self.assertEqual(self.config["margin_mode"], "")
        self.assertFalse(self.config["exchange"]["key"])
        self.assertFalse(self.config["exchange"]["secret"])
        self.assertFalse(self.config["force_entry_enable"])
        self.assertFalse(self.config["api_server"]["enabled"])
        self.assertIn("--dry-run", self.compose)
        self.assertIn("config.paper.json", self.compose)

    def test_position_limit_and_fake_wallet(self):
        self.assertEqual(self.config["max_open_trades"], 1)
        self.assertLessEqual(self.config["stake_amount"], 25)
        self.assertEqual(self.config["dry_run_wallet"], 1000)
        self.assertLessEqual(self.config["tradable_balance_ratio"], 0.9)
        self.assertEqual(self.config["stake_currency"], "USDT")

    def test_exchange_uses_explicit_spot_pairs(self):
        self.assertEqual(self.config["exchange"]["name"], "kraken")
        self.assertEqual(self.config["exchange"]["pair_whitelist"], ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
        self.assertEqual(self.config["pairlists"], [{"method": "StaticPairList"}])

    def test_research_isolation(self):
        self.assertNotIn("research_entrypoint", self.compose)
        self.assertIn("papertrade:", self.compose)
        self.assertIn("tradesv3.paper.sqlite", self.config["db_url"])


if __name__ == "__main__":
    unittest.main()
