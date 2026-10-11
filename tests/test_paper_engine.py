"""Native dry-order/SQLite restart integration, offline synthetic book only."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from freqtrade.enums import RunMode, CandleType
from freqtrade.exchange import Kraken
from freqtrade.persistence import Order, Trade, init_db
from freqtrade.wallets import Wallets
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.commands import Arguments
from freqtrade.configuration import Configuration
from freqtrade.configuration.config_validation import validate_config_consistency
from freqtrade.resolvers import StrategyResolver
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


class NativePaperEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = json.loads((ROOT / 'user_data/config.paper.json').read_text())
        self.config['runmode'] = RunMode.DRY_RUN
        self.db_url = 'sqlite:///' + str(Path(self.temp.name) / 'native-paper.sqlite')
        init_db(self.db_url)
        self.addCleanup(self.cleanup_db)
        # Synthetic fixture exercises the installed engine, never historical/live performance.
        self.market = {'id': 'XBTUSDT', 'symbol': 'BTC/USDT', 'base': 'BTC', 'quote': 'USDT',
                       'baseId': 'XBT', 'quoteId': 'USDT', 'type': 'spot', 'spot': True,
                       'margin': False, 'swap': False, 'future': False, 'option': False,
                       'contract': False, 'active': True, 'maker': .004, 'taker': .004,
                       'precision': {'amount': .00001, 'price': .01},
                       'limits': {n: {'min': None, 'max': None} for n in ('amount', 'price', 'cost')},
                       'info': {}}
        self.book = {'bids': [[100000., 10.]], 'asks': [[100010., 10.]], 'timestamp': None}

    def cleanup_db(self):
        engine = Trade.session.get_bind()
        Trade.session.remove()
        engine.dispose()

    def exchange(self):
        with patch.object(Kraken, 'reload_markets', return_value=None):
            exchange = Kraken(self.config, validate=False, load_leverage_tiers=False)
        exchange._markets = {'BTC/USDT': self.market}
        exchange._api.set_markets([self.market])
        exchange._api_async.set_markets([self.market])
        exchange.fetch_l2_order_book = Mock(return_value=self.book)
        exchange._api.create_order = Mock(side_effect=AssertionError('Private order endpoint called'))
        self.addCleanup(exchange.close)
        return exchange

    def test_native_paper_configuration_and_strategy_load_without_network(self):
        argv = ['trade', '--config', str(ROOT / 'user_data/config.paper.json'),
                '--strategy', 'MultiAssetPaperStrategy', '--dry-run',
                '--user-data-dir', self.temp.name,
                '--logfile', str(Path(self.temp.name) / 'native-test.log'),
                '--strategy-path', str(ROOT / 'user_data/strategies')]
        config = Configuration(Arguments(argv).get_parsed_arg(), RunMode.DRY_RUN).get_config()
        strategy = StrategyResolver.load_strategy(config)
        validate_config_consistency(config)
        self.assertIs(config['dry_run'], True)
        self.assertEqual(strategy.order_types['entry'], 'limit')
        self.assertFalse(config.get('api_server', {}).get('enabled', False))

    def test_native_fill_fee_trade_and_wallet_persist_across_fresh_exchange(self):
        exchange = self.exchange()
        order = exchange.create_order(pair='BTC/USDT', ordertype='limit', side='buy',
                                      amount=.00025, rate=100010., leverage=1)
        self.assertTrue(order['id'].startswith('dry_run_buy_'))
        self.assertEqual(order['status'], 'closed')
        self.assertAlmostEqual(order['fee']['cost'], order['cost'] * .004)
        exchange._api.create_order.assert_not_called()
        trade = Trade(pair='BTC/USDT', exchange='kraken', open_rate=order['average'],
                      stake_amount=order['cost'], amount=order['filled'],
                      fee_open=.004, fee_close=.004, open_date=datetime.now(timezone.utc),
                      is_open=True, strategy='MultiAssetPaperStrategy', timeframe=60)
        trade.orders = [Order.parse_from_ccxt_object(order, 'BTC/USDT', 'buy')]
        Trade.session.add(trade)
        Trade.commit()
        identifier = trade.id
        # Remove identity map; reload persisted trade and recover the dry order from SQLite.
        Trade.session.remove()
        fresh = self.exchange()
        recovered = fresh.fetch_dry_run_order(order['id'])
        self.assertEqual(recovered['filled'], order['filled'])
        self.assertEqual(recovered['status'], 'closed')
        restored = Trade.get_trades_proxy(is_open=True)
        self.assertEqual([t.id for t in restored], [identifier])
        wallets = Wallets(self.config, fresh)
        self.assertAlmostEqual(wallets.get_free('USDT'), 1000-order['cost'])
        fresh._api.create_order.assert_not_called()

    def test_native_pending_limit_is_recovered_then_fills_after_restart(self):
        exchange = self.exchange()
        order = exchange.create_order(pair='BTC/USDT', ordertype='limit', side='buy',
                                      amount=.00025, rate=99000., leverage=1)
        self.assertEqual(order['status'], 'open')
        trade = Trade(pair='BTC/USDT', exchange='kraken', open_rate=99000.,
                      stake_amount=24.75, amount=0., fee_open=.004, fee_close=.004,
                      open_date=datetime.now(timezone.utc), is_open=True,
                      strategy='MultiAssetPaperStrategy', timeframe=60)
        trade.orders = [Order.parse_from_ccxt_object(order, 'BTC/USDT', 'buy')]
        Trade.session.add(trade)
        Trade.commit()
        Trade.session.remove()
        fresh = self.exchange()
        self.assertEqual(fresh.fetch_dry_run_order(order['id'])['status'], 'open')
        fresh.fetch_l2_order_book.return_value = {'bids': [[98900., 10]], 'asks': [[99000., 10]]}
        filled = fresh.fetch_dry_run_order(order['id'])
        self.assertEqual(filled['status'], 'closed')
        self.assertEqual(filled['filled'], .00025)
        fresh._api.create_order.assert_not_called()

    def test_native_bot_consumes_signal_and_simulates_order_in_isolated_database(self):
        # Full native create_trade/get_entry_signal/execute_entry path. Fixtures never
        # enter user_data/tradesv3.paper.sqlite or the live paper process.
        argv = ['trade', '--config', str(ROOT / 'user_data/config.paper.json'),
                '--strategy', 'MultiAssetPaperStrategy', '--dry-run',
                '--user-data-dir', self.temp.name,
                '--logfile', str(Path(self.temp.name) / 'native-test.log'),
                '--strategy-path', str(ROOT / 'user_data/strategies')]
        config = Configuration(Arguments(argv).get_parsed_arg(), RunMode.DRY_RUN).get_config()
        config['user_data_dir'] = Path(self.temp.name)
        config['datadir'] = Path(self.temp.name) / 'data'
        config['strategy_path'] = str(ROOT / 'user_data/strategies')
        exchange = self.exchange()
        self.market['limits']['amount']['min'] = .00005
        self.market['limits']['cost']['min'] = .5
        exchange.validate_config = Mock()
        # Keep native pair-list validation while providing synthetic metadata for all pairs.
        markets = {}
        from copy import deepcopy
        for pair in config['exchange']['pair_whitelist']:
            market = deepcopy(self.market)
            market.update(symbol=pair, id=pair.replace('/', ''), base=pair.split('/')[0])
            markets[pair] = market
        exchange._markets = markets
        exchange._api.set_markets(list(markets.values()))
        exchange._api_async.set_markets(list(markets.values()))
        with patch('freqtrade.freqtradebot.ExchangeResolver.load_exchange', return_value=exchange), \
             patch('freqtrade.freqtradebot.init_db'):  # Database already initialized in the temporary directory.
            bot = FreqtradeBot(config)
        self.addCleanup(bot.cleanup)
        now = datetime.now(timezone.utc)
        last = pd.Timestamp(now).floor('1h') - pd.Timedelta(hours=1)
        frame = pd.DataFrame({'date': pd.date_range(end=last, periods=200, freq='1h'),
                              'open': 100000., 'high': 100020., 'low': 99980.,
                              'close': 100000., 'volume': 10.,
                              'sma_fast': 99990., 'sma_slow': 100000., 'rsi': 60.})
        for pair in markets:
            quiet = bot.strategy.populate_entry_trend(frame.copy(), {'pair': pair})
            quiet = bot.strategy.populate_exit_trend(quiet, {'pair': pair})
            bot.dataprovider._set_cached_df(pair, '1h', quiet, CandleType.SPOT)
        bot.strategy.bot_loop_start(now)
        self.assertTrue(bot.strategy.risk_ready)
        self.assertEqual(bot.enter_positions(1), 0)  # No signal means no invented trade.
        frame.loc[199, 'sma_fast'] = 100010.
        signal = bot.strategy.populate_entry_trend(frame.copy(), {'pair': 'BTC/USDT'})
        signal = bot.strategy.populate_exit_trend(signal, {'pair': 'BTC/USDT'})
        self.assertEqual(signal['enter_long'].iloc[-1], 1)
        bot.dataprovider._set_cached_df('BTC/USDT', '1h', signal, CandleType.SPOT)
        bot.strategy.bot_loop_start(datetime.now(timezone.utc))
        self.assertEqual(bot.enter_positions(1), 1)
        trades = Trade.get_trades_proxy(is_open=True)
        self.assertEqual(len(trades), 1)
        self.assertTrue(trades[0].orders[0].order_id.startswith('dry_run_buy_'))
        self.assertEqual(trades[0].orders[0].status, 'closed')
        self.assertLessEqual(trades[0].stake_amount, 25)
        self.assertEqual(bot.enter_positions(1), 0)  # One-position limit.
        exchange._api.create_order.assert_not_called()
