"""Fixed research hypotheses, exclusively Binance BTC/USDT backtests on 2024."""

from pathlib import Path
import sys

import talib.abstract as ta
from technical import qtpylib
from freqtrade.enums import RunMode
from freqtrade.strategy import IStrategy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_guard import DEVELOPMENT_START, DEVELOPMENT_END
from paper_risk import RiskPolicy


class DevelopmentBase(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '1h'
    startup_candle_count = 200
    can_short = False
    stoploss = -0.05
    minimal_roi = {}
    position_adjustment_enable = False
    order_types = {'entry': 'market', 'exit': 'market', 'stoploss': 'market', 'stoploss_on_exchange': False}

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        if self.config.get('runmode') != RunMode.BACKTEST or leverage != 1 or side != 'long':
            return 0.0
        equity = self.wallets.get_total_stake_amount() / self.config['tradable_balance_ratio']
        return RiskPolicy(fee=0.001).stake(equity, self.wallets.get_free('USDT'), min_stake, max_stake)

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        if (self.config.get('runmode') != RunMode.BACKTEST or self.config.get('dry_run') is not True
                or self.config.get('trading_mode') != 'spot' or pair != 'BTC/USDT'
                or self.config.get('exchange', {}).get('name') != 'binance' or side != 'long'
                or current_time.tzinfo is None or not DEVELOPMENT_START <= current_time < DEVELOPMENT_END):
            return False
        equity = self.wallets.get_total_stake_amount() / self.config['tradable_balance_ratio']
        return RiskPolicy(fee=0.001).allows_notional(amount * rate, equity,
                                                  self.wallets.get_free('USDT'), 5.0)

    def populate_indicators(self, dataframe, metadata):
        dataframe['sma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        dataframe['sma200'] = ta.SMA(dataframe, timeperiod=200)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['upper20'] = dataframe['high'].rolling(20).max().shift(1)
        dataframe['lower10'] = dataframe['low'].rolling(10).min().shift(1)
        bands = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['band_lower'] = bands['lowerband']
        dataframe['band_middle'] = bands['middleband']
        return dataframe


class TrendDevelopment(DevelopmentBase):
    def populate_entry_trend(self, dataframe, metadata):
        dataframe['enter_long'] = (qtpylib.crossed_above(dataframe['sma20'], dataframe['sma50']) &
                                   (dataframe['close'] > dataframe['sma200']) &
                                   dataframe['rsi'].between(50, 70, inclusive='left') &
                                   (dataframe['volume'] > 0)).astype(int)
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe['exit_long'] = (qtpylib.crossed_below(dataframe['sma20'], dataframe['sma50']) &
                                  (dataframe['volume'] > 0)).astype(int)
        return dataframe


class BreakoutDevelopment(DevelopmentBase):
    def populate_entry_trend(self, dataframe, metadata):
        dataframe['enter_long'] = (qtpylib.crossed_above(dataframe['close'], dataframe['upper20']) &
                                   (dataframe['close'] > dataframe['sma200']) &
                                   (dataframe['volume'] > 0)).astype(int)
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe['exit_long'] = ((dataframe['close'] < dataframe['lower10']) &
                                  (dataframe['volume'] > 0)).astype(int)
        return dataframe


class MeanReversionDevelopment(DevelopmentBase):
    def populate_entry_trend(self, dataframe, metadata):
        dataframe['enter_long'] = ((dataframe['close'] < dataframe['band_lower']) &
                                   (dataframe['rsi'] < 30) &
                                   ((dataframe['sma20'] / dataframe['sma50'] - 1).abs() < 0.01) &
                                   (dataframe['volume'] > 0)).astype(int)
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe['exit_long'] = (((dataframe['close'] >= dataframe['band_middle']) | (dataframe['rsi'] >= 50)) &
                                  (dataframe['volume'] > 0)).astype(int)
        return dataframe
