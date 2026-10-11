from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy


class SmaRsiStrategy(IStrategy):
    """Baseline educational strategy; profitability is not assumed."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    minimal_roi = {"0": 0.04, "120": 0.02, "360": 0.0}
    stoploss = -0.03
    startup_candle_count = 60
    process_only_new_candles = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma_fast"] = ta.SMA(dataframe, timeperiod=20)
        dataframe["sma_slow"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["sma_fast"] > dataframe["sma_slow"])
            & (dataframe["sma_fast"].shift(1) <= dataframe["sma_slow"].shift(1))
            & (dataframe["rsi"] > 45)
            & (dataframe["rsi"] < 70)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["sma_fast"] < dataframe["sma_slow"])
            & (dataframe["sma_fast"].shift(1) >= dataframe["sma_slow"].shift(1))
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        return dataframe
