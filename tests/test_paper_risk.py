"""Risk controls and callback failure paths; synthetic fixtures are not research data."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'user_data/strategies'))
from paper_risk import RiskPolicy, RiskState, require_current_window, validate_paper_config
from MultiAssetPaperStrategy import MultiAssetPaperStrategy
from SmaRsiStrategy import SmaRsiStrategy


class PaperRiskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 10, 11, 19, 15, tzinfo=timezone.utc)
        self.policy = RiskPolicy()

    def state(self):
        return RiskState(Path(self.temp.name) / 'risk.sqlite', self.policy)

    def test_cost_aware_cap_and_projected_loss_on_different_wallets(self):
        for equity in (100, 500, 1000, 2000):
            stake = self.policy.stake(equity, equity, 5, equity)
            cash = stake * (1 + self.policy.entry_fee) * (1 + self.policy.execution_cost)
            self.assertLessEqual(cash, equity * .10 + 1e-9)
            self.assertLessEqual(cash * self.policy.loss_fraction, equity * .005 + 1e-9)
            self.assertTrue(self.policy.allows_notional(stake, equity, equity, 5))
            self.assertFalse(self.policy.allows_notional(stake * 1.1, equity, equity, 5))

    def test_minimum_never_increases_position_and_invalid_values_block(self):
        self.assertEqual(self.policy.stake(1000, 1000, 100, 900), 0)
        for value in (0, -1, float('nan'), float('inf')):
            self.assertEqual(self.policy.stake(value, 1000, 5, 1000), 0)
            self.assertFalse(self.policy.allows_notional(value, 1000, 1000, 5))
        with self.assertRaises(ValueError):
            RiskPolicy(position_cap=.20)

    def test_drawdown_peak_and_halt_survive_restart_and_recovery(self):
        state = self.state()
        state.observe(1100, self.now)
        self.assertFalse(state.observe(1034, self.now + timedelta(seconds=1)))
        restart = self.state()
        self.assertEqual(restart.data['peak'], 1100)
        self.assertTrue(restart.data['halted'])
        self.assertFalse(restart.observe(1200, self.now + timedelta(seconds=2)))

    def test_cooldown_and_closed_trade_deduplication_survive_restart(self):
        closes = [(i, self.now - timedelta(minutes=4-i), -1.0) for i in (1, 2, 3)]
        state = self.state()
        self.assertFalse(state.observe(997, self.now, closes))
        until = state.data['cooldown_until']
        restart = self.state()
        restart.observe(997, self.now + timedelta(hours=2), closes)
        self.assertEqual(restart.data['cooldown_until'], until)
        self.assertEqual(len(restart.data['closed_ids']), 3)
        self.assertTrue(restart.allowed(self.now + timedelta(hours=24)))

    def test_single_exit_cooldown_and_policy_change_refusal(self):
        state = self.state()
        self.assertFalse(state.observe(1001, self.now, [(1, self.now, 1)]))
        self.assertTrue(state.allowed(self.now + timedelta(hours=1)))
        with self.assertRaises(ValueError):
            RiskState(state.path, RiskPolicy(fee=.003))

    def test_warmup_cannot_acquire_reserved_dates_or_future_or_naive(self):
        require_current_window(self.now - timedelta(hours=200), self.now, self.now)
        for start, end in ((datetime(2026, 6, 30, tzinfo=timezone.utc), self.now),
                           (self.now - timedelta(hours=200), self.now + timedelta(hours=1)),
                           (self.now.replace(tzinfo=None), self.now)):
            with self.assertRaises(ValueError):
                require_current_window(start, end, self.now)


class PaperCallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 10, 11, 19, 15, tzinfo=timezone.utc)
        self.config = json.loads((ROOT / 'user_data/config.paper.json').read_text())
        self.config['user_data_dir'] = Path(self.temp.name)
        self.strategy = MultiAssetPaperStrategy(self.config)
        self.strategy.wallets = Mock()
        self.strategy.wallets.get_free.return_value = 1000
        dates = pd.date_range(end='2026-10-11T18:00:00Z', periods=200, freq='1h')
        self.frame = pd.DataFrame({'date': dates, 'open': 100., 'close': 100.,
                                   'high': 101., 'low': 99., 'volume': 10.,
                                   'sma_fast': 100., 'sma_slow': 100., 'rsi': 60.,
                                   'enter_long': 0, 'exit_long': 0})
        self.market = {'active': True, 'spot': True, 'taker': .004,
                       'limits': {'amount': {'min': .001}, 'cost': {'min': 5.}}}
        self.book = {'bids': [[100., 100.]], 'asks': [[100.01, 100.]], 'timestamp': None}
        self.strategy.dp = Mock()
        self.strategy.dp._exchange.amount_to_precision.side_effect = lambda pair, amount: amount
        self.strategy.dp.market.return_value = self.market
        self.strategy.dp.orderbook.return_value = self.book
        self.strategy.dp.get_analyzed_dataframe.return_value = (self.frame, self.now)
        patcher = patch('MultiAssetPaperStrategy.Trade.get_trades_proxy', return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.strategy.bot_start()
        self.strategy.bot_loop_start(self.now)

    def size(self, minimum=5):
        return self.strategy.custom_stake_amount('BTC/USDT', self.now, 100.01, 25,
                                                 minimum, 1000, 1, 'fixture', 'long')

    def confirm(self, notional=25, pair='BTC/USDT', order_type='limit'):
        return self.strategy.confirm_trade_entry(pair, order_type, notional/100.01,
                                                 100.01, 'GTC', self.now, 'fixture', 'long')

    def test_valid_simulation_and_native_min_stake_clamp_rejection(self):
        self.assertEqual(self.size(), 25)
        self.assertTrue(self.confirm())
        self.assertEqual(self.size(100), 0)
        self.assertFalse(self.confirm(100))
        self.assertFalse(self.confirm(pair='BTC/USD'))
        self.assertFalse(self.confirm(order_type='market'))

    def test_cost_and_liquidity_invalidations(self):
        for key in ('spread', 'depth', 'crossed', 'fee', 'minimum', 'stale_book'):
            with self.subTest(key=key):
                market, book = deepcopy(self.market), deepcopy(self.book)
                if key == 'spread': book['asks'][0][0] = 102
                if key == 'depth': book['asks'][0][1] = .0001
                if key == 'crossed': book['bids'][0][0] = 101
                if key == 'fee': market['taker'] = .01
                if key == 'minimum': market['limits']['cost']['min'] = None
                if key == 'stale_book': book['timestamp'] = (self.now.timestamp()-60)*1000
                self.strategy.dp.market.return_value = market
                self.strategy.dp.orderbook.return_value = book
                self.assertFalse(self.confirm())

    def test_gap_duplicate_future_stale_zero_volume_and_short_candles_block(self):
        for kind in ('gap', 'duplicate', 'future', 'stale', 'volume', 'short', 'nan'):
            with self.subTest(kind=kind):
                frame = self.frame.copy()
                if kind == 'gap': frame = frame.drop(index=50)
                if kind == 'duplicate': frame.loc[50, 'date'] = frame.loc[49, 'date']
                if kind == 'future': frame['date'] += pd.Timedelta(hours=2)
                if kind == 'stale': frame['date'] -= pd.Timedelta(hours=3)
                if kind == 'volume': frame.loc[199, 'volume'] = 0
                if kind == 'short': frame = frame.iloc[:20]
                if kind == 'nan': frame.loc[199, 'rsi'] = float('nan')
                self.strategy.dp.get_analyzed_dataframe.return_value = (frame, self.now)
                self.assertEqual(self.size(), 0)
                self.assertFalse(self.confirm())

    def test_risk_errors_never_fall_back_to_native_permissive_defaults(self):
        with patch.object(self.strategy, '_entry_context', side_effect=RuntimeError('fixture failure')):
            self.assertEqual(self.size(), 0)
            self.assertFalse(self.confirm())
        self.strategy.risk_ready = False
        self.assertFalse(self.confirm())

    def test_quantity_precision_cannot_push_order_below_minimum(self):
        self.strategy.dp._exchange.amount_to_precision.return_value = .001
        self.strategy.dp._exchange.amount_to_precision.side_effect = None
        self.assertFalse(self.confirm())  # Rounded cost 0.10 USDT is below the 5 USDT minimum.

    def test_book_after_callback_time_is_checked_against_receipt(self):
        self.book['timestamp']=(self.now.timestamp()+.1)*1000
        with patch('MultiAssetPaperStrategy.datetime',wraps=datetime) as clock:
            clock.now.return_value=self.now+timedelta(seconds=.2)
            self.assertTrue(self.confirm())
            self.book['timestamp']=(self.now.timestamp()+10)*1000
            self.assertFalse(self.confirm())

    def test_public_price_api_failure_blocks_entry_and_sizing(self):
        self.strategy.public_quotes.clear()
        self.strategy.dp.orderbook.side_effect=RuntimeError('synthetic API outage')
        self.strategy.bot_loop_start(self.now)
        self.assertFalse(self.strategy.risk_ready)
        self.assertEqual(self.size(),0)
        self.assertFalse(self.confirm())

    def test_attempt_persistence_failure_blocks_then_recovers_without_erasing_risk(self):
        before = deepcopy(self.strategy.risk_state.data)
        with patch.object(self.strategy.telemetry, 'record', side_effect=OSError('fixture disk full')):
            self.assertFalse(self.confirm())
            self.assertFalse(self.strategy.risk_ready)
            self.assertEqual(self.size(), 0)
        self.strategy.bot_loop_start(self.now)
        self.assertTrue(self.strategy.risk_ready)
        self.assertEqual(before['peak'], self.strategy.risk_state.data['peak'])
        self.assertTrue(self.confirm())

    def test_api_recovery_records_error_and_recovery_without_replaying_signal(self):
        self.strategy.public_quotes.clear()
        self.strategy.dp.orderbook.side_effect = RuntimeError('fixture disconnect')
        self.strategy.bot_loop_start(self.now)
        self.assertFalse(self.strategy.risk_ready)
        self.strategy.dp.orderbook.side_effect = None
        self.strategy.bot_loop_start(self.now)
        self.assertTrue(self.strategy.risk_ready)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.strategy.telemetry.path)) as db:
            events = [json.loads(row[0]) for row in db.execute('SELECT body FROM events ORDER BY id')]
        self.assertEqual([e['kind'] for e in events], ['loop_error', 'loop_recovered'])
        body = json.loads((Path(self.temp.name)/'paper/status.json').read_text())
        self.assertEqual(body['pairs']['BTC/USDT']['latest_enter_long'], 0)
        self.assertEqual(body['pairs']['BTC/USDT']['non_entry_reason'], 'no_entry_signal')

    def test_halt_exits_and_restart_still_blocks_entries(self):
        self.strategy.risk_state.observe(930, self.now)
        self.assertFalse(self.confirm())
        self.assertEqual(self.strategy.custom_exit('BTC/USDT', None, self.now, 100, 0), 'paper_drawdown_halt')
        self.strategy.bot_start()
        self.strategy.bot_loop_start(self.now)
        self.assertFalse(self.confirm())

    def test_credentials_modes_and_environment_overrides_fail_closed(self):
        for field, value in (('dry_run', False), ('trading_mode', 'futures'), ('fee', 0),
                             ('max_open_trades', 2), ('force_entry_enable', True)):
            config = deepcopy(self.config)
            config[field] = value
            with self.assertRaises(ValueError): validate_paper_config(config)
        for key in ('key', 'secret', 'api_key', 'private_key'):
            config = deepcopy(self.config)
            config['exchange'][key] = 'unit-test-only'
            with self.assertRaises(ValueError): validate_paper_config(config)
        with self.assertRaises(ValueError):
            validate_paper_config(self.config, {'FREQTRADE__DRY_RUN': 'false'})
        config = deepcopy(self.config)
        config['exchange']['ccxt_config']['urls'] = {'api': 'unit-test-only'}
        with self.assertRaises(ValueError): validate_paper_config(config)

    def test_signal_copy_matches_frozen_baseline(self):
        frame = self.frame[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        baseline = SmaRsiStrategy(json.loads((ROOT / 'user_data/config.json').read_text()))
        def analyze(strategy):
            out = strategy.populate_indicators(frame.copy(), {})
            out = strategy.populate_entry_trend(out, {})
            return strategy.populate_exit_trend(out, {})
        pd.testing.assert_frame_equal(analyze(self.strategy), analyze(baseline))
