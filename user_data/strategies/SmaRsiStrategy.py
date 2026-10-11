"""Baseline causal de pesquisa; sem promessa de retorno financeiro."""

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy


class SmaRsiStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    startup_candle_count = 200
    process_only_new_candles = True
    minimal_roi = {}
    stoploss = -0.05
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = False
    order_types = {
        "entry": "market", "exit": "market", "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma_fast"] = ta.SMA(dataframe, timeperiod=20)
        dataframe["sma_slow"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
        signal = (
            qtpylib.crossed_above(dataframe["sma_fast"], dataframe["sma_slow"])
            & (dataframe["rsi"] >= 50) & (dataframe["rsi"] < 70)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[signal, ["enter_long", "enter_tag"]] = (1, "sma_cross_rsi")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""
        signal = (
            qtpylib.crossed_below(dataframe["sma_fast"], dataframe["sma_slow"])
            | (dataframe["rsi"] >= 75)
        ) & (dataframe["volume"] > 0)
        dataframe.loc[signal, ["exit_long", "exit_tag"]] = (1, "sma_down_or_rsi_75")
        return dataframe

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        # Defesa adicional caso seja carregada fora da entrada Compose.
        return (
            self.config.get("dry_run") is True
            and self.config.get("trading_mode") == "spot"
            and pair == "BTC/USDT" and side == "long"
        )
