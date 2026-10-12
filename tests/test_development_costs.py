"""Semantic cost/risk checks on synthetic fixtures, never economic validation."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'research_strategies'))
from analyze_development import benchmark, profit_metrics, replay_opportunities, rounded_quantity
from risk_model import COST_SCENARIOS
from DevelopmentCandidates import BreakoutVolumeDevelopment


class DevelopmentCostTests(unittest.TestCase):
    def frame(self, prices=(100,100,100,100,100,100)):
        return pd.DataFrame({'date':pd.date_range('2024-04-01',periods=len(prices),freq='1h',tz='UTC'),
                              'open':prices,'close':prices,'high':np.array(prices)+10,
                              'low':np.array(prices)-1,'volume':10.})

    def trade(self, frame, begin, end, exit_rate=103):
        return {'open_date':frame['date'].iloc[begin].isoformat(),
                'close_date':frame['date'].iloc[end].isoformat(),
                'open_rate':100.,'close_rate':float(exit_rate),'exit_reason':'fixture'}

    def test_both_side_costs_reduce_benchmark_and_risk_replay(self):
        frame=self.frame((100,100,101,102,103,103))
        trade=self.trade(frame,0,5)
        base=replay_opportunities([trade],frame,COST_SCENARIOS[0])
        adverse=replay_opportunities([trade],frame,COST_SCENARIOS[-1])
        self.assertGreater(base['net_pnl'],adverse['net_pnl'])
        self.assertGreater(benchmark(frame,COST_SCENARIOS[0])['net_pnl'],
                           benchmark(frame,COST_SCENARIOS[-1])['net_pnl'])
        self.assertGreater(adverse['fees'],0)
        self.assertLessEqual(adverse['max_entry_cash_fraction'],.10)
        self.assertLessEqual(adverse['max_nominal_risk_fraction'],.005)

    def test_cooldown_skips_boundary_reentry_and_accounting_conserves_cash(self):
        frame=self.frame()
        trades=[self.trade(frame,0,1),self.trade(frame,1,2),self.trade(frame,2,4)]
        result=replay_opportunities(trades,frame,COST_SCENARIOS[2])
        self.assertEqual(result['trades'],2)
        self.assertEqual(len(result['skipped']),1)
        self.assertAlmostEqual(result['net_pnl'],1000*result['net_return'])
        self.assertAlmostEqual(result['time_exposure_hourly'],3/5)

    def test_minimum_rounding_and_no_trade_metrics_do_not_invent_results(self):
        self.assertEqual(rounded_quantity(5.001,100,.01),.05)
        frame=self.frame()
        result=replay_opportunities([self.trade(frame,0,5)],frame,COST_SCENARIOS[2],minimum=500)
        self.assertEqual(result['trades'],0)
        self.assertEqual(result['net_pnl'],0)
        self.assertIsNone(result['profit_factor'])
        self.assertIsNone(result['winrate'])

    def test_gap_can_exceed_nominal_budget_and_drawdown_threshold(self):
        for remaining in (.95,.90,.80,.20):
            frame=self.frame((100,100*remaining,100*remaining))
            result=replay_opportunities([self.trade(frame,0,2,100*remaining)],frame,COST_SCENARIOS[2])
            self.assertLessEqual(result['max_nominal_risk_fraction'],.005)
            if remaining<=.90:self.assertGreater(-result['net_return'],.005)
            if remaining==.20:
                self.assertGreater(result['max_drawdown_hourly_liquidation'],.06)
                self.assertEqual(result['hypothetical_fills'][0]['reason'],'risk_drawdown_halt')

    def test_holdout_frame_is_rejected_before_replay(self):
        frame=self.frame();frame['date']+=pd.Timedelta(days=500)
        with self.assertRaises(ValueError):replay_opportunities([],frame,COST_SCENARIOS[2])

    def test_volume_confirmation_is_relative_and_causal(self):
        strategy=BreakoutVolumeDevelopment({})
        frame=self.frame(tuple([100]*25))
        frame['upper20']=100.;frame['sma200']=99.
        frame.loc[24,'close']=101;frame.loc[24,'volume']=14.99
        self.assertEqual(strategy.populate_entry_trend(frame.copy(),{})['enter_long'].iloc[-1],0)
        frame.loc[24,'volume']=15.
        self.assertEqual(strategy.populate_entry_trend(frame.copy(),{})['enter_long'].iloc[-1],1)
        frame.loc[24,'volume']=1000000.
        pd.testing.assert_series_equal(strategy.populate_entry_trend(frame.copy(),{})['enter_long'].iloc[:24],
                                       strategy.populate_entry_trend(frame.iloc[:24].copy(),{})['enter_long'])
