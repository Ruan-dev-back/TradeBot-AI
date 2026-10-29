"""Integration checks against the pinned Freqtrade runtime (skip on bare host)."""
from copy import deepcopy
from datetime import datetime, timezone
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'user_data/strategies'))

try:
    import freqtrade  # noqa: F401
    HAS_FREQTRADE = True
except ImportError:
    HAS_FREQTRADE = False


@unittest.skipUnless(HAS_FREQTRADE, 'Freqtrade is available in the pinned Docker runtime only')
class AgentTraderFreqtradeTests(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        from AgentTraderV1 import AgentTraderV1
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.strategy_cls = AgentTraderV1
        self.config = json.loads((ROOT / 'user_data/config.agenttrader-v1.json').read_text())
        self.config['user_data_dir'] = self.temp.name
        self.strategy = AgentTraderV1(self.config)
        self.strategy.bot_start()
        self.strategy.wallets = Mock()
        self.strategy.dp = Mock()
        self.pd = pd

    def test_strategy_callback_rejects_entry_when_risk_state_is_not_ready(self):
        self.assertEqual(self.strategy.custom_stake_amount(
            'BTC/USDT', self.pd.Timestamp.now(tz='UTC').to_pydatetime(), 100,
            10, 1, 100, 1, 'test', 'long'), 0.0)
        self.assertFalse(self.strategy.confirm_trade_entry(
            'BTC/USDT', 'limit', .1, 100, 'GTC',
            self.pd.Timestamp.now(tz='UTC').to_pydatetime(), 'test', 'long'))

    def test_unfilled_reserved_order_does_not_create_fake_position_loss(self):
        from freqtrade.persistence import Trade
        now = self.pd.Timestamp.now(tz='UTC').to_pydatetime()
        pending = Mock(nr_of_successful_entries=0, stake_amount=10)
        self.strategy.wallets.get_free.return_value = 0
        self.strategy.dp.get_analyzed_dataframe.return_value = (self.pd.DataFrame(), now)
        with patch.object(Trade, 'get_trades_proxy', side_effect=lambda is_open:
                          [] if not is_open else [pending]):
            self.strategy.bot_loop_start(now)
        self.assertEqual(self.strategy.journal.state()['equity'], 100.)
        self.strategy.dp.orderbook.assert_not_called()

    def test_exit_callback_requires_current_public_spot_book_and_precision(self):
        now = datetime.now(timezone.utc)
        self.strategy.dp.market.return_value = {
            'symbol': 'BTC/USDT', 'active': True, 'spot': True, 'contract': False,
            'taker': .001, 'precision': {'amount': .0001, 'price': .01},
            'limits': {'amount': {'min': .0001, 'max': 10},
                       'cost': {'min': 1, 'max': 1000}}}
        self.strategy.dp.orderbook.return_value = {
            'timestamp': int(now.timestamp()*1000), 'bids': [[100, 1]], 'asks': [[100.01, 1]]}
        trade = Mock()
        self.assertTrue(self.strategy.confirm_trade_exit(
            'BTC/USDT', trade, 'market', .1, 100, 'GTC', 'roi', now))

        self.strategy.dp.orderbook.return_value['timestamp'] = int((now.timestamp()-31)*1000)
        self.assertFalse(self.strategy.confirm_trade_exit(
            'BTC/USDT', trade, 'market', .1, 100, 'GTC', 'stop_loss', now))

        self.strategy.dp.orderbook.return_value['timestamp'] = int(now.timestamp()*1000)
        # Amount precision passes, but the native exit quote is not aligned to the market tick.
        self.assertFalse(self.strategy.confirm_trade_exit(
            'BTC/USDT', trade, 'market', .1, 100.001, 'GTC', 'stop_loss', now))

    def test_informative_merge_never_uses_unclosed_hourly_candle(self):
        # A 12:00 hourly candle is unavailable at 12:50 and becomes available at 12:55,
        # whose 5m close is 13:00.
        pd = self.pd
        base5 = pd.date_range('2026-10-29T00:00:00Z', periods=300, freq='5min')
        base1 = pd.date_range('2026-10-28T00:00:00Z', periods=40, freq='1h')
        frame = pd.DataFrame({'date': base5, 'open': 100., 'high': 101., 'low': 99.,
                              'close': [100 + i * .01 for i in range(len(base5))], 'volume': 10.})
        hourly = pd.DataFrame({'date': base1, 'open': 100., 'high': 101., 'low': 99.,
                               'close': [100 + i * .1 for i in range(len(base1))], 'volume': 10.})
        self.strategy.dp.get_pair_dataframe.return_value = hourly.copy()
        merged = self.strategy.populate_indicators(frame.copy(), {'pair': 'BTC/USDT'})
        # Merged informative value changes only after the corresponding hour closes.
        cutoff = pd.Timestamp('2026-10-29T12:50:00Z')
        before = merged.loc[merged['date'] <= cutoff, 'close_1h']
        mutated = hourly.copy()
        mutated.loc[mutated['date'] == pd.Timestamp('2026-10-29T12:00:00Z'), 'close'] *= 2
        self.strategy.dp.get_pair_dataframe.return_value = mutated
        merged_future_changed = self.strategy.populate_indicators(frame.copy(), {'pair': 'BTC/USDT'})
        before_changed = merged_future_changed.loc[merged_future_changed['date'] <= cutoff, 'close_1h']
        pd.testing.assert_series_equal(before.reset_index(drop=True), before_changed.reset_index(drop=True))
        at_close = pd.Timestamp('2026-10-29T12:55:00Z')
        value_before = merged.loc[merged['date'] == at_close, 'close_1h'].iloc[0]
        value_after = merged_future_changed.loc[merged_future_changed['date'] == at_close, 'close_1h'].iloc[0]
        self.assertNotEqual(value_before, value_after)


if __name__ == '__main__':
    unittest.main()
