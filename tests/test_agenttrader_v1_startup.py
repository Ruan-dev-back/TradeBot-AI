"""Warmup contract and offline checks using the real TA-Lib/Freqtrade runtime."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'user_data/strategies'))
HAS_RUNTIME = all(importlib.util.find_spec(name) for name in ('freqtrade', 'talib', 'pandas'))


class StartupContractTests(unittest.TestCase):
    def test_warmup_fits_okx_budget_and_damps_ema200_seed(self):
        tree = ast.parse((ROOT / 'user_data/strategies/AgentTraderV1.py').read_text())
        strategy = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        count = next(ast.literal_eval(node.value) for node in strategy.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'startup_candle_count'
                             for t in node.targets))
        self.assertLessEqual(count+1, 300*5)
        # For EMA200, the SMA seed is at observation 200. Bound its remaining
        # weight after startup plus the evaluated candle to less than 0.005%.
        self.assertGreaterEqual(count, 200)
        self.assertLess((199/201)**(count+1-200), .00005)


@unittest.skipUnless(HAS_RUNTIME, 'Requires TA-Lib and Freqtrade (pinned Docker image)')
class StartupRuntimeTests(unittest.TestCase):
    def test_real_okx_validator_accepts_warmup_and_rejects_old_value(self):
        from AgentTraderV1 import AgentTraderV1
        from freqtrade.enums import CandleType
        from freqtrade.exchange import Exchange, Okx
        from freqtrade.exceptions import ConfigurationError
        exchange = SimpleNamespace(
            ohlcv_candle_limit=lambda timeframe, candle_type, since_ms:
                Okx.ohlcv_candle_limit(None, timeframe, candle_type, since_ms),
            _config={'candle_type_def': CandleType.SPOT},
            _ft_has={'ohlcv_has_history': True}, name='OKX')
        for timeframe in ('5m', '1h'):
            self.assertEqual(Exchange.validate_required_startup_candles(
                exchange, AgentTraderV1.startup_candle_count, timeframe), 4)
            with self.assertRaises(ConfigurationError):
                Exchange.validate_required_startup_candles(exchange, 2400, timeframe)

    def test_dataprovider_requests_same_count_per_timeframe(self):
        from AgentTraderV1 import AgentTraderV1
        from freqtrade.data.dataprovider import DataProvider
        count = AgentTraderV1.startup_candle_count
        provider = SimpleNamespace(_config={'startup_candle_count': count})
        strategy = AgentTraderV1({'exchange': {'pair_whitelist': ['BTC/USDT', 'ETH/USDT']}})
        self.assertEqual(strategy.informative_pairs(), [('BTC/USDT', '1h'), ('ETH/USDT', '1h')])
        for timeframe in ('5m', '1h'):
            self.assertEqual(DataProvider.get_required_startup(provider, timeframe), count)

    def test_native_recursive_analysis_and_multi_endpoint_stability(self):
        from agenttrader_v1_startup_analysis import analyze, TOLERANCE_PCT
        report = analyze()
        selected = report['sweep_max_errors'][str(report['startup_candle_count'])]
        for period in (9, 21, 200):
            self.assertLess(selected[f'ema{period}_relative_pct'], TOLERANCE_PCT)
        self.assertLess(selected['rsi_absolute_points'], .000001)
        for period in (9, 21, 200):
            self.assertIn(f'ema{period}_1h', report['native_recursive_selected_relative_pct'])

    def test_native_lookahead_prefix_is_identical(self):
        from agenttrader_v1_startup_analysis import OfflineRecursiveAnalysis
        import pandas as pd
        analysis = OfflineRecursiveAnalysis()
        analysis.fill_full_varholder()
        analysis.fill_partial_varholder_lookahead(
            analysis.full_varHolder.from_dt + pd.Timedelta(minutes=50))
        full = analysis.full_varHolder.indicators['BTC/USDT']
        partial = analysis.partial_varHolder_lookahead_array[0].indicators['BTC/USDT']
        pd.testing.assert_series_equal(full.loc[full.date == partial.iloc[-1].date].iloc[-1],
                                       partial.iloc[-1], check_names=False)

    def test_entry_and_exit_signals_are_stable_on_fixture_tail(self):
        from AgentTraderV1 import AgentTraderV1
        from agenttrader_v1_startup_analysis import OfflineRecursiveAnalysis
        import pandas as pd
        analysis = OfflineRecursiveAnalysis()
        analysis.fill_full_varholder()
        analysis.fill_partial_varholder(
            analysis.full_varHolder.to_dt-pd.Timedelta(minutes=5),
            AgentTraderV1.startup_candle_count)
        strategy = AgentTraderV1({})
        outputs = []
        for holder in (analysis.full_varHolder, analysis.partial_varHolder_array[0]):
            indicators = holder.indicators['BTC/USDT'].copy()
            entries = strategy.populate_entry_trend(indicators, {})
            signals = strategy.populate_exit_trend(entries, {})
            outputs.append(signals[['date', 'enter_long', 'exit_long']].tail(50).reset_index(drop=True))
        pd.testing.assert_frame_equal(*outputs)

    def test_insufficient_hourly_history_blocks_entry(self):
        import numpy as np
        import pandas as pd
        from AgentTraderV1 import AgentTraderV1
        from freqtrade.persistence import Trade
        from agenttrader_v1_startup_analysis import frame
        count = AgentTraderV1.startup_candle_count
        base_dates = pd.date_range('2026-10-01', periods=count+1, freq='5min', tz='UTC')
        hour_dates = pd.date_range(end=base_dates[-1].floor('1h'), periods=199, freq='1h')
        strategy = AgentTraderV1({'exchange': {'pair_whitelist': ['BTC/USDT']}})
        strategy.dp = Mock()
        strategy.dp.get_pair_dataframe.return_value = frame(hour_dates, np.arange(199)+100.)
        merged = strategy.populate_indicators(frame(base_dates, np.arange(count+1)+100.),
                                               {'pair': 'BTC/USDT'})
        self.assertTrue(np.isnan(merged.iloc[-1].ema200_1h))
        merged['enter_long'], merged['exit_long'] = 1, 0
        strategy.dp.get_analyzed_dataframe.return_value = (merged, None)
        strategy.ready = True
        strategy.journal = Mock()
        strategy.journal.allowed.return_value = True
        with patch('AgentTraderV1.validate_config'), patch.object(Trade, 'get_trades_proxy', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'Indicators not warmed up'):
                strategy._context('BTC/USDT', base_dates[-1] + pd.Timedelta(minutes=5))


if __name__ == '__main__':
    unittest.main()
