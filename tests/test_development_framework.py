"""Temporal isolation and causality for new hypotheses; no real holdout reads."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'research_strategies'))
from development_framework import CANDIDATES, FOLDS, experiment_plan
from DevelopmentCandidates import BreakoutDevelopment, MeanReversionDevelopment, TrendDevelopment
from freqtrade.enums import RunMode


class DevelopmentFrameworkTests(unittest.TestCase):
    def test_only_fixed_2024_folds_and_candidates_are_accepted(self):
        for fold in FOLDS:
            plan = experiment_plan('trend', fold)
            self.assertFalse(plan['holdout_prices_inspected'])
            self.assertEqual(plan['source'].split()[1], 'Binance')
        for fold in ('validation', 'holdout', '20250701-20260701'):
            with self.assertRaises(ValueError): experiment_plan('trend', fold)
        with self.assertRaises(ValueError): experiment_plan('ml', 'D1')

    def test_candidates_are_causal_and_breakout_uses_previous_high(self):
        n = 600
        close = 100 + np.cumsum(np.random.default_rng(9).normal(0, 1, n))
        frame = pd.DataFrame({'date': pd.date_range('2024-01-01', periods=n, freq='1h', tz='UTC'),
                              'open': close, 'close': close, 'high': close+1, 'low': close-1, 'volume': 10.})
        for cls in (TrendDevelopment, BreakoutDevelopment, MeanReversionDevelopment):
            strategy = cls({'runmode': RunMode.BACKTEST})
            def analyze(source):
                out = strategy.populate_indicators(source.copy(), {})
                out = strategy.populate_entry_trend(out, {})
                return strategy.populate_exit_trend(out, {})
            result = analyze(frame)
            for length in (250, 400, 500):
                pd.testing.assert_frame_equal(result.iloc[:length], analyze(frame.iloc[:length]))
            self.assertEqual(result['upper20'].iloc[30], frame['high'].iloc[10:30].max())

    def test_candidates_refuse_paper_live_and_observed_2025_entries(self):
        for mode in (RunMode.DRY_RUN, RunMode.LIVE, RunMode.BACKTEST):
            strategy = TrendDevelopment({'runmode': mode, 'dry_run': True, 'trading_mode': 'spot',
                                          'exchange': {'name': 'binance'}})
            for date in (datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 7, 1, tzinfo=timezone.utc)):
                self.assertFalse(strategy.confirm_trade_entry('BTC/USDT', 'market', .001, 100000,
                                  'GTC', date, 'test', 'long'))
            if mode != RunMode.BACKTEST:
                self.assertFalse(strategy.confirm_trade_entry('BTC/USDT', 'market', .001, 100000,
                                 'GTC', datetime(2024, 6, 1, tzinfo=timezone.utc), 'test', 'long'))
