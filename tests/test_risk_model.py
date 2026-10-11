from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from risk_model import Costs, fixed_quantity_costs, net_position_return, notionals, quantile, replay


def trade(ratio=1.1, timestamp=1):
    # Apenas fixture aritmético; nunca usado no relatório financeiro.
    return {"open_timestamp": timestamp,
            "orders": [{"amount": 1, "safe_price": 100, "ft_is_entry": True},
                       {"amount": 1, "safe_price": 100 * ratio, "ft_is_entry": False}]}


class RiskModelTests(unittest.TestCase):
    def test_fees_are_charged_on_both_sides_once(self):
        self.assertAlmostEqual(net_position_return(1.1, Costs("base")), 1.1 * .999 / 1.001 - 1)
        self.assertAlmostEqual(fixed_quantity_costs([trade()], Costs("base")), 9.79)

    def test_spread_is_full_and_slippage_is_per_side(self):
        costs = Costs("case", spread_bps=10, slippage_bps_per_side=10, extra_fee_bps_per_side=5)
        self.assertAlmostEqual(costs.execution, .0015)
        self.assertAlmostEqual(costs.fee, .0015)
        self.assertAlmostEqual(net_position_return(1.1, costs), 1.1 * .9985**2 / 1.0015**2 - 1)

    def test_higher_costs_reduce_results_without_double_counting_base_fee(self):
        trades = [trade(1.1), trade(.95, 2)]
        base = replay(trades, .1, Costs("base"))
        stressed = replay(trades, .1, Costs("stress", spread_bps=20, slippage_bps_per_side=20, extra_fee_bps_per_side=10))
        self.assertLess(stressed["net_return"], base["net_return"])
        self.assertEqual(stressed["trades_retained"], 2)

    def test_replay_compounds_current_equity_and_measures_close_drawdown(self):
        result = replay([trade(1.1), trade(.9, 2)], .5, Costs("zero", base_fee_bps_per_side=0))
        self.assertAlmostEqual(result["final_equity"], 1000 * 1.05 * .95)
        self.assertAlmostEqual(result["max_drawdown_closed_trades"], .05)
        self.assertTrue(result["hypothetical_not_independent_validation"])

    def test_smaller_exposure_reduces_loss_without_claiming_profit(self):
        a = replay([trade(.95)], .05, Costs("base"))
        b = replay([trade(.95)], .20, Costs("base"))
        self.assertLess(a["net_return"], 0)
        self.assertGreater(a["net_return"], b["net_return"])
        self.assertLess(a["max_drawdown_closed_trades"], b["max_drawdown_closed_trades"])

    def test_invalid_costs_capital_and_exposure_are_refused(self):
        for value in (-1, math.inf, math.nan, 20000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Costs("bad", spread_bps=value)
        for value in (0, -1, 1.01, math.nan):
            with self.subTest(fraction=value), self.assertRaises(ValueError):
                replay([trade()], value, Costs("base"))
        with self.assertRaises(ValueError):
            replay([trade()], .1, Costs("base"), initial=0)

    def test_missing_partial_and_different_quantity_fills_are_refused(self):
        for kind in ("missing", "partial", "different"):
            t = deepcopy(trade())
            if kind == "missing":
                t["orders"].pop()
            elif kind == "partial":
                t["orders"].append(deepcopy(t["orders"][-1]))
            else:
                t["orders"][-1]["amount"] = .5
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                notionals(t)

    def test_quantile_uses_linear_interpolation_and_small_samples(self):
        self.assertEqual(quantile([0, 10], .25), 2.5)
        self.assertEqual(quantile([3], .9), 3)
        with self.assertRaises(ValueError):
            quantile([], .5)


if __name__ == "__main__":
    unittest.main()
