import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_research import read_backtest, render_report, trade_metrics


class ReportTests(unittest.TestCase):
    # Exports sintéticos apenas para testar o parser; nunca usados no relatório financeiro.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.stat = {
            "total_trades": 1, "profit_total_abs": 9.79, "profit_total": 0.00979,
            "final_balance": 1009.79, "max_drawdown_account": 0.01,
            "max_drawdown_abs": 10, "market_change": 0.1,
            "backtest_start": "2024-01-01 00:00:00", "backtest_end": "2024-12-31 23:00:00",
            "trades": [{"amount": 1, "open_rate": 100, "close_rate": 110,
                        "fee_open": 0.001, "fee_close": 0.001, "profit_abs": 9.79}],
        }

    def write_archive(self, name="result.zip"):
        with zipfile.ZipFile(self.directory / name, "w") as archive:
            archive.writestr("result.json", json.dumps({"strategy": {"SmaRsiStrategy": self.stat}}))
            archive.writestr("result_config.json", json.dumps({"dry_run": True}))

    def test_net_profit_and_two_sided_fees_are_read(self):
        self.write_archive()
        stat, fees, _ = read_backtest(self.directory)
        self.assertEqual(stat["profit_total_abs"], 9.79)
        self.assertAlmostEqual(fees, 0.21)

    def test_missing_or_ambiguous_exports_are_refused(self):
        with self.assertRaises(ValueError):
            read_backtest(self.directory)
        self.write_archive()
        self.write_archive("older.zip")
        with self.assertRaises(ValueError):
            read_backtest(self.directory)

    def test_inconsistent_aggregate_is_refused(self):
        self.stat["profit_total_abs"] = 999
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "Lucro agregado"):
            read_backtest(self.directory)

    def test_failed_download_is_not_reported_as_zero_profit(self):
        text = render_report("synthetic-parser-test", [], {}, None, {})
        self.assertIn("sem métricas", text)
        self.assertIn("| Lucro líquido (USDT) | N/D | N/D |", text)
        self.assertIn("| Drawdown máximo relativo da conta | N/D | N/D |", text)

    def metric_stat(self):
        return {"backtest_start": "2024-01-01 00:00:00", "backtest_end": "2024-01-02 00:00:00",
                "trades": [
                    {"open_date": "2024-01-01 01:00:00+00:00", "close_date": "2024-01-01 04:00:00+00:00", "profit_abs": 10},
                    {"open_date": "2024-01-01 12:00:00+00:00", "close_date": "2024-01-01 15:00:00+00:00", "profit_abs": -5},
                ]}

    def test_profit_factor_winrate_and_temporal_exposure(self):
        metrics = trade_metrics(self.metric_stat())
        self.assertEqual(metrics["profit_factor"], 2)
        self.assertEqual(metrics["winrate"], 0.5)
        self.assertEqual(metrics["exposure"], 0.25)

    def test_no_trades_has_no_invented_profit_factor_or_winrate(self):
        stat = self.metric_stat()
        stat["trades"] = []
        metrics = trade_metrics(stat)
        self.assertIsNone(metrics["profit_factor"])
        self.assertIsNone(metrics["winrate"])
        self.assertEqual(metrics["exposure"], 0)

    def test_future_or_overlapping_trade_is_refused(self):
        for kind in ("future", "overlap", "entry_at_end"):
            with self.subTest(kind=kind):
                stat = self.metric_stat()
                if kind == "future":
                    stat["trades"][0]["close_date"] = "2024-01-03 00:00:00+00:00"
                elif kind == "overlap":
                    stat["trades"][1]["open_date"] = "2024-01-01 03:00:00+00:00"
                else:
                    stat["trades"][1]["open_date"] = stat["trades"][1]["close_date"] = "2024-01-02 00:00:00+00:00"
                with self.assertRaises(ValueError):
                    trade_metrics(stat)


if __name__ == "__main__":
    unittest.main()
