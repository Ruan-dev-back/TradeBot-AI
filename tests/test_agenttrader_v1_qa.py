"""Adversarial safety tests for AgentTrader V1 using synthetic public market data."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from agenttrader_v1 import Journal, PAIRS, Policy, validate_config, validate_market
from agenttrader_v1_compare import signals, simulate, validate_exit_book


class AgentTraderPolicyTests(unittest.TestCase):
    def test_stake_never_exceeds_cap_after_assumed_entry_costs(self):
        policy = Policy()
        for cash in (100, 50, 10, 5, 1):
            with self.subTest(cash=cash):
                stake = policy.stake(cash)
                self.assertLessEqual(stake, 10)
                self.assertLessEqual(stake * (1 + policy.fee) * (1 + policy.slippage), min(10, cash) + 1e-10)
        for cash in (0, -1, float('nan'), float('inf'), True):
            self.assertEqual(policy.stake(cash), 0)

    def test_fixed_risk_policy_rejects_relaxation(self):
        for field, value in (('cap', 10.01), ('risk', .51), ('stop', .019),
                             ('take_profit', .041), ('daily_loss', 2.01),
                             ('drawdown', .051), ('fee', .0009), ('slippage', .0004)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                Policy(**{field: value})

    def test_pnl_includes_fee_and_slippage_both_sides(self):
        p = Policy()
        flat = p.pnl(10, 100, 100)
        self.assertLess(flat, 0)
        self.assertAlmostEqual(flat, 10 * ((100 * .9995 * .999) / (100 * 1.0005) - 1.001))
        self.assertLessEqual(-p.pnl(10, 100, 98), .50)
        self.assertGreater(p.pnl(10, 100, 104), 0)


class AgentTraderMarketTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        self.market = {'symbol': 'BTC/USDT', 'active': True, 'spot': True,
                       'contract': False, 'taker': .001,
                       'limits': {'amount': {'min': .00001}, 'price': {'min': None, 'max': None},
                                  'cost': {'min': 1, 'max': 100}},
                       'precision': {'amount': .00001, 'price': .01}}
        self.book = {'timestamp': int(self.now.timestamp() * 1000),
                     'bids': [[99.99, 1]], 'asks': [[100, 1]]}

    def accept(self, market=None, book=None, rate=100, amount=.0998):
        return validate_market(market or self.market, book or self.book, rate, amount, self.now)

    def test_valid_order_has_cash_and_loss_within_limits(self):
        result = self.accept()
        self.assertLessEqual(result['notional'], 10)
        self.assertLessEqual(result['cash'], 10)
        self.assertLessEqual(result['planned_loss'], .50)
        self.assertEqual(result['fee_per_side_assumed'], .001)
        self.assertEqual(result['slippage_per_side_assumed'], .0005)

    def test_invalid_market_metadata_and_order_constraints_fail_closed(self):
        cases = []
        for pair in ('SOL/USDT', 'BTC/USD'):
            m = deepcopy(self.market); m['symbol'] = pair; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['spot'] = False; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['active'] = False; cases.append((m, self.book, 100, .0998))
        for field, value in [('taker', None), ('taker', .01), ('taker', True), ('taker', False)]:
            m = deepcopy(self.market); m[field] = value; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['limits']['amount']['min'] = None; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['precision']['price'] = None; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['limits']['cost']['min'] = 11; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['limits']['amount']['min'] = .1; cases.append((m, self.book, 100, .0998))
        m = deepcopy(self.market); m['precision']['amount'] = .0001; cases.append((m, self.book, 100, .099831))
        m = deepcopy(self.market); m['precision']['price'] = .03; cases.append((m, self.book, 100, .0998))
        for market, book, rate, amount in cases:
            with self.subTest(market=market), self.assertRaises(ValueError):
                self.accept(market, book, rate, amount)

    def test_book_timestamp_liquidity_spread_and_nan_fail_closed(self):
        for mutate in (
            lambda b: b.update(timestamp=None),
            lambda b: b.update(timestamp=float('nan')),
            lambda b: b.update(timestamp=int((self.now.timestamp() - 31) * 1000)),
            lambda b: b.update(asks=[[100.2, 1]]),
            lambda b: b.update(asks=[[100, .001]]),
            lambda b: b.update(bids=[[101, 1]]),
            lambda b: b.update(asks=[[float('nan'), 1]]),
        ):
            book = deepcopy(self.book); mutate(book)
            with self.subTest(book=book), self.assertRaises((ValueError, TypeError)):
                self.accept(book=book)

    def test_oversized_and_unaligned_orders_are_rejected_without_upscaling(self):
        for rate, amount in ((100, .1), (100, .10001), (100, .099831), (100, 1e-8)):
            with self.subTest(rate=rate, amount=amount), self.assertRaises(ValueError):
                self.accept(rate=rate, amount=amount)


class AgentTraderJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'journal.sqlite'
        self.now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)

    def test_records_and_exports_events_trades_equity_to_csv_and_json(self):
        journal = Journal(self.path)
        journal.record(self.now, 'signal', 'BTC/USDT', signal='enter')
        journal.observe(self.now, 99.5, [{'id': 'a', 'closed_at': self.now.isoformat(),
                                           'pnl': -.5, 'pair': 'BTC/USDT'}])
        out = Path(self.temp.name) / 'export'
        result = journal.export(out)
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(len(result['trades']), 1)
        self.assertEqual(len(result['equity']), 1)
        self.assertTrue((out / 'journal.json').is_file())
        self.assertTrue((out / 'events.csv').is_file())
        self.assertEqual(json.loads((out / 'journal.json').read_text())['trades'][0]['pnl'], -.5)

    def test_daily_loss_drawdown_and_peak_are_fail_closed_and_persist(self):
        journal = Journal(self.path)
        self.assertTrue(journal.observe(self.now, 100, []))
        losses = [{'id': 'a', 'closed_at': self.now.isoformat(), 'pnl': -1.01, 'pair': 'BTC/USDT'},
                  {'id': 'b', 'closed_at': self.now.isoformat(), 'pnl': -.99, 'pair': 'ETH/USDT'}]
        self.assertFalse(journal.observe(self.now + timedelta(seconds=1), 94.9, losses))
        restarted = Journal(self.path)
        self.assertAlmostEqual(restarted.state()['daily_pnl'], -5.1)
        self.assertTrue(restarted.state()['halted'])
        self.assertFalse(restarted.allowed(self.now + timedelta(days=1)))

    def test_daily_loss_includes_open_mark_to_market_equity(self):
        journal = Journal(self.path)
        self.assertTrue(journal.observe(self.now, 100, []))
        allowed = journal.observe(self.now + timedelta(seconds=1), 98, [])
        self.assertFalse(allowed, '2 USDT loss must halt even if the position has not closed')

    def test_daily_loss_pause_stays_latched_until_next_utc_day_and_survives_restart(self):
        journal = Journal(self.path)
        self.assertTrue(journal.observe(self.now, 100, []))
        self.assertFalse(journal.observe(self.now + timedelta(seconds=1), 98, []))
        self.assertFalse(journal.observe(self.now + timedelta(seconds=2), 100, []))
        restarted = Journal(self.path)
        self.assertFalse(restarted.allowed(self.now + timedelta(seconds=2)))
        tomorrow = self.now + timedelta(days=1)
        self.assertTrue(restarted.observe(tomorrow, 100, []))

    def test_closed_trade_ids_are_idempotent(self):
        journal = Journal(self.path)
        trade = {'id': 'same', 'closed_at': self.now.isoformat(), 'pnl': -1.1, 'pair': 'BTC/USDT'}
        journal.observe(self.now, 98.9, [trade])
        journal.observe(self.now + timedelta(seconds=1), 98.9, [trade])
        exported = journal.export(Path(self.temp.name) / 'exp')
        self.assertEqual(len(exported['trades']), 1)

    def test_naive_or_future_close_time_is_rejected(self):
        journal = Journal(self.path)
        for when in (self.now.replace(tzinfo=None).isoformat(), (self.now + timedelta(seconds=2)).isoformat()):
            trade = {'id': when, 'closed_at': when, 'pnl': 1., 'pair': 'BTC/USDT'}
            with self.subTest(when=when), self.assertRaises(ValueError):
                journal.observe(self.now, 100, [trade])


class AgentTraderConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'user_data/config.agenttrader-v1.json').read_text())

    def test_checked_in_config_passes_immutable_paper_contract(self):
        validate_config(self.config, {})

    def test_live_mode_credentials_and_environment_overrides_are_refused(self):
        for mutate in (
            lambda c: c.update(dry_run=False),
            lambda c: c.update(trading_mode='futures'),
            lambda c: c.update(dry_run_wallet=1000),
            lambda c: c['exchange'].update(key='synthetic'),
            lambda c: c['exchange'].update(secret='synthetic'),
            lambda c: c['exchange'].update(password='synthetic'),
            lambda c: c['exchange'].update(pair_whitelist=['BTC/USDT']),
        ):
            config = deepcopy(self.config); mutate(config)
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_config(config, {})
        with self.assertRaises(ValueError):
            validate_config(self.config, {'FREQTRADE__DRY_RUN': 'false'})

    def test_api_server_flags_cannot_enable_extra_surface(self):
        for key, value in (('enable_openapi', True), ('listen_port', 8082),
                           ('unreviewed_field', 'unexpected')):
            config = deepcopy(self.config)
            config['api_server'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(config, {})


class AgentTraderSimulationTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        self.candles = [[int((self.start + timedelta(minutes=5*i)).timestamp()*1000),
                         100, 104, 97, 100, 10] for i in range(5)]
        self.hourly = [[int((self.start + timedelta(hours=i)).timestamp()*1000),
                        100, 104, 97, 100, 10] for i in range(3)]
        self.market = {'symbol': 'BTC/USDT', 'active': True, 'spot': True,
                       'contract': False, 'taker': .001,
                       'limits': {'amount': {'min': .0001}, 'price': {'min': None, 'max': None},
                                  'cost': {'min': 1, 'max': 10}},
                       'precision': {'amount': .0001, 'price': .01}}
        self.books = {}
        for candle in self.candles:
            timestamp = candle[0]
            self.books[timestamp] = {'timestamp': timestamp, 'bids': [[100, 10]], 'asks': [[100, 10]]}
        stop_timestamp = self.candles[2][0]
        self.candles[2][1] = 97  # Checkpoint open gap triggers the stop; low alone is not a fill.
        self.books[stop_timestamp] = {'timestamp': stop_timestamp,
                                      'bids': [[97, 10]], 'asks': [[97, 10]]}
        self.decisions = [{'ready': True, 'entry': i == 0, 'exit': False,
                           'baseline_entry': i == 0, 'baseline_exit': False}
                          for i in range(len(self.candles))]

    def test_signal_calculation_is_invariant_to_appended_future_candles(self):
        base = int(self.start.timestamp()*1000)
        candles = [[base+300000*i, 100+i*.1, 101+i*.1, 99+i*.1, 100+i*.1, 10]
                   for i in range(600)]
        hourly = [[base+3600000*i, 100+i, 101+i, 99+i, 100+i, 10] for i in range(260)]
        prefix = signals(candles[:400], hourly[:35])
        extended = signals(candles[:600], hourly)
        self.assertEqual(prefix, extended[:400])

    def test_alternatives_fill_only_next_candle_and_apply_costed_protective_exit(self):
        with patch('agenttrader_v1_compare.signals', return_value=self.decisions):
            result = simulate(self.candles, self.hourly, self.market, self.books)
        for strategy in ('strategy', 'baseline_ema21_200'):
            trade = result[strategy]['trades'][0]
            self.assertEqual(trade['entry_utc'], datetime.fromtimestamp(self.candles[1][0]/1000, timezone.utc).isoformat())
            self.assertEqual(trade['reason'], 'stop_checkpoint')
            self.assertEqual(trade['exit'], 97)
            self.assertLessEqual(trade['stake'], 10)
            self.assertLess(trade['pnl'], 0)
        self.assertEqual(result['buy_and_hold']['trades'][0]['reason'], 'end_of_window')
        self.assertIsNone(result['buy_and_hold']['open_position'])

    def test_missing_executable_book_rejects_without_inventing_a_fill(self):
        del self.books[self.candles[1][0]]
        with patch('agenttrader_v1_compare.signals', return_value=self.decisions):
            result = simulate(self.candles, self.hourly, self.market, self.books)
        self.assertEqual(result['strategy']['trades'], [])
        self.assertEqual(len(result['strategy']['rejections']), 1)

    def test_open_candle_close_cannot_change_checkpoint_risk_or_trades(self):
        candles = deepcopy(self.candles)
        candles[2][1:5] = [100, 104, 99, 100]
        altered = deepcopy(candles)
        altered[2][4] = 50  # This close is future information at the row's open timestamp.
        decisions = deepcopy(self.decisions)
        with patch('agenttrader_v1_compare.signals', return_value=decisions):
            original = simulate(candles, self.hourly, self.market, self.books)
            changed = simulate(altered, self.hourly, self.market, self.books)
        for strategy in original:
            self.assertEqual(original[strategy]['trades'], changed[strategy]['trades'])
            self.assertEqual(original[strategy]['rejections'], changed[strategy]['rejections'])
            self.assertEqual(original[strategy]['halted'], changed[strategy]['halted'])

    def test_exit_validation_rejects_nan_price_and_depth(self):
        timestamp = int(self.start.timestamp()*1000)
        for book in (
            {'timestamp': timestamp, 'bids': [[float('nan'), 1]]},
            {'timestamp': timestamp, 'bids': [[100, float('nan')]]},
        ):
            with self.subTest(book=book), self.assertRaises(ValueError):
                validate_exit_book(book, .1, self.start)


if __name__ == '__main__':
    unittest.main()
