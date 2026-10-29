"""Offline EMA convergence sweep and native Freqtrade recursive analysis.

Synthetic data only. No config, environment credentials, exchange or bot startup.
The native analysis algorithm uses an in-memory adapter instead of Backtesting,
because AgentTraderV1.bot_start deliberately accepts operational dry-run only.
"""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import talib
import freqtrade
from freqtrade.optimize.analysis.recursive import RecursiveAnalysis
from freqtrade.util import CustomProgress

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'user_data/strategies'))
from AgentTraderV1 import AgentTraderV1

CANDIDATES = (199, 399, 599, 799, 999, 1199, 1499)
TOLERANCE_PCT = .001


def prices(size):
    x = np.arange(size)
    return {
        'oscillating': 100 + 20*np.sin(x/137) + 10*np.cos(x/31),
        'trending': 100 + .03*x + 20*np.sin(x/43),
        'step_changes': np.where((x//300) % 2, 200., 100.),
    }


def convergence_sweep():
    """Compare 44 endpoints per series, all EMAs and RSI against long history.

EMA recurrence is independent of candle duration; this applies to each
timeframe's own observations, not resampled 5m candles.
"""
    result = {str(n): {} for n in CANDIDATES}
    for values in prices(12000).values():
        for name, function, period in (
            ('ema9', talib.EMA, 9), ('ema21', talib.EMA, 21),
            ('ema200', talib.EMA, 200), ('rsi', talib.RSI, 14),
        ):
            reference = function(values, timeperiod=period)
            for end in range(5000, 11000, 137):
                for count in CANDIDATES:
                    actual = function(values[end-count:end+1], timeperiod=period)[-1]
                    # Flat step fixtures have RSI=0; absolute RSI points avoid division by zero.
                    error = (abs(actual-reference[end]) if name == 'rsi' else
                             abs(actual/reference[end]-1)*100)
                    key = name + ('_absolute_points' if name == 'rsi' else '_relative_pct')
                    result[str(count)][key] = max(result[str(count)].get(key, 0), float(error))
    return result


def frame(dates, values):
    return pd.DataFrame({'date': dates, 'open': values, 'high': values+1,
                         'low': values-1, 'close': values, 'volume': 10.})


class OfflineRecursiveAnalysis(RecursiveAnalysis):
    """Native start/comparison/lookahead, with explicitly synthetic data loading.

    Vary BOTH timeframe histories independently, including the informative seed.
    Never calls bot_start or any exchange API. Not a market backtest.
    """
    def __init__(self):
        dates = pd.date_range('2026-01-01', periods=6000, freq='1h', tz='UTC')
        self.hourly = frame(dates, prices(len(dates))['oscillating'])
        dates5 = pd.date_range(dates[0], periods=len(dates)*12, freq='5min')
        self.base = frame(dates5, prices(len(dates5))['trending'])
        end = dates[-1] + pd.Timedelta(hours=1)
        start = end - pd.Timedelta(hours=1000)
        config = {'timerange': f'{int(start.timestamp())}-{int(end.timestamp())}',
                  'pairs': ['BTC/USDT'], 'startup_candle': list(CANDIDATES),
                  'startup_candle_count': AgentTraderV1.startup_candle_count}
        super().__init__(config, {'name': 'AgentTraderV1'})
        self.pair_to_used = 'BTC/USDT'

    def prepare_data(self, varholder, pairs_to_load):
        count = self.local_config['startup_candle_count']
        start, end = pd.Timestamp(varholder.from_dt), pd.Timestamp(varholder.to_dt)
        base = self.base.loc[(self.base.date >= start-pd.Timedelta(minutes=5*count))
                             & (self.base.date < end)].copy()
        hourly = self.hourly.loc[(self.hourly.date >= start.floor('1h')-pd.Timedelta(hours=count))
                                 & (self.hourly.date < end)].copy()
        strategy = AgentTraderV1({'exchange': {'pair_whitelist': pairs_to_load}})
        strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: hourly.copy())
        varholder.timeframe = '5m'
        varholder.indicators = {self.pair_to_used: strategy.populate_indicators(
            base.reset_index(drop=True), {'pair': self.pair_to_used})}


def analyze():
    sweep = convergence_sweep()
    native = OfflineRecursiveAnalysis()
    with CustomProgress(disable=True) as progress:
        native.start(progress)
    selected = AgentTraderV1.startup_candle_count
    # Native routine reports fractional differences; sweep reports percent.
    native_selected_pct = {
        name: abs(native.dict_recursive.get(name, {}).get(selected, 0))*100
        for name in native.full_varHolder.indicators[native.pair_to_used].columns
        if name.startswith('ema') or name == 'rsi'
    }
    report = {'data': 'deterministic synthetic; no market data or trading',
              'freqtrade': freqtrade.__version__, 'talib': talib.__version__,
              'numpy': np.__version__, 'pandas': pd.__version__,
              'startup_candle_count': selected, 'ema_tolerance_relative_pct': TOLERANCE_PCT,
              'sweep_max_errors': sweep, 'native_recursive_selected_relative_pct': native_selected_pct,
              'native_recursive_all_fractional_differences': native.dict_recursive}
    assert sweep[str(selected)]['ema200_relative_pct'] < TOLERANCE_PCT, report
    assert all(np.isfinite(v) and v < TOLERANCE_PCT for v in native_selected_pct.values()), report
    return report


if __name__ == '__main__':
    print(json.dumps(analyze(), indent=2, allow_nan=False))
