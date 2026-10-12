"""Cópia explícita da baseline para PAPER TRADING MULTIATIVOS; estratégia não lucrativa em testes anteriores."""

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib
from datetime import datetime, timedelta, timezone
import logging
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from paper_risk import RiskPolicy, RiskState, finite_positive, require_current_window, validate_paper_config
from paper_profiles import profile_for, minimum_notional
from validate_data import validate_candles
from freqtrade.persistence import Trade

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class MultiAssetPaperStrategy(IStrategy):
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
        "entry": "limit", "exit": "market", "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def bot_start(self, **kwargs):
        validate_paper_config(self.config)
        self.policy = RiskPolicy()
        profile = profile_for(self.config['exchange']['name'])
        self.risk_state = RiskState(Path(self.config["user_data_dir"]) / profile.state_folder / 'risk.sqlite',
                                    self.policy)
        self.risk_ready = False
        self.public_quotes = {}

    def _update_quotes(self, now):
        for pair in self.config['exchange']['pair_whitelist']:
            previous = self.public_quotes.get(pair)
            if previous and 0 <= (now-datetime.fromisoformat(previous['observed_at'])).total_seconds() < 20:
                continue
            started = time.monotonic()
            book = self.dp.orderbook(pair, 20)
            received = datetime.now(timezone.utc)
            bid, ask = book['bids'][0][0], book['asks'][0][0]
            if time.monotonic()-started > 3 or not finite_positive(bid,ask) or bid > ask:
                raise ValueError('Invalid or delayed public price snapshot')
            if book.get('timestamp') is not None and not -2 <= received.timestamp()-book['timestamp']/1000 <= 30:
                raise ValueError('Public price timestamp outside receipt-time tolerance')
            self.public_quotes[pair] = {'status':'ok','observed_at':now.isoformat(),
                'received_at':received.isoformat(),'bid':float(bid),'ask':float(ask),
                'spread_bps':float((ask-bid)/((ask+bid)/2)*10000)}

    def _equity(self):
        self.wallets.update()
        # Freqtrade free USDT excludes open stake; add marked net liquidation value.
        free = self.wallets.get_free("USDT")
        equity = free
        for trade in Trade.get_trades_proxy(is_open=True):
            book = self.dp.orderbook(trade.pair, 20)
            bid = book["bids"][0][0]
            if not finite_positive(bid):
                raise ValueError("Invalid mark price")
            equity += trade.stake_amount + trade.calc_profit(bid).profit_abs
        if not finite_positive(equity, free):
            raise ValueError("Invalid paper wallet")
        return equity, free

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if getattr(self, "risk_ready", False) and self.risk_state.data["halted"]:
            return "paper_drawdown_halt"
        return None

    def bot_loop_start(self, current_time, **kwargs):
        self.risk_ready = False
        try:
            validate_paper_config(self.config)
            equity, _ = self._equity()
            closed = [(t.id, t.close_date_utc, t.close_profit_abs)
                      for t in Trade.get_trades_proxy(is_open=False)]
            self.risk_state.observe(equity, current_time, closed)
            self._update_quotes(current_time)
            self.risk_ready = True
            if self.risk_state.data["warning"]:
                logger.warning("Paper drawdown warning: %.4f; entry halt=%s",
                               self.risk_state.data["drawdown"], self.risk_state.data["halted"])
            self._write_status(current_time)
        except Exception as error:
            self.risk_ready = False
            logger.warning("Paper risk observation failed; entries blocked: %s",
                           str(error) if isinstance(error, ValueError) else type(error).__name__)
            try:
                self._write_status(current_time)
            except Exception:
                pass  # A stale/unwritable snapshot also fails the external healthcheck.

    def _write_status(self, now):
        pairs = {}
        open_pairs = {trade.pair for trade in Trade.get_trades_proxy(is_open=True)}
        for pair in self.config['exchange']['pair_whitelist']:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if frame.empty:
                pairs[pair] = {'status': 'warming_up', 'candles': 0}
                continue
            sample = frame.tail(self.startup_candle_count)
            try:
                validate_candles(sample)
                require_current_window(sample['date'].iloc[0].to_pydatetime(), now, now)
                age = (now - sample['date'].iloc[-1]).total_seconds()
                valid = len(sample) >= 200 and 3600 <= age <= 7500
                enter, exit_ = int(sample['enter_long'].iloc[-1]), int(sample['exit_long'].iloc[-1])
                decision = ('exit_candidate' if pair in open_pairs and (exit_ or self.risk_state.data['halted'])
                            else 'hold' if pair in open_pairs
                            else 'entry_candidate' if self.risk_ready and valid and enter and not exit_ and not open_pairs and self.risk_state.allowed(now)
                            else 'no_trade')
                pairs[pair] = {'status': 'ok' if valid else 'invalid', 'candles': len(frame),
                               'checked_candles': len(sample), 'first_utc': str(sample['date'].iloc[0]),
                               'last_closed_utc': str(sample['date'].iloc[-1]), 'timeframe': self.timeframe,
                               'latest_enter_long': enter, 'latest_exit_long': exit_,
                               'latest_close_price': float(sample['close'].iloc[-1]),
                               'public_book':self.public_quotes.get(pair,{'status':'unavailable'}),
                               'candle_close_utc': (sample['date'].iloc[-1]+timedelta(hours=1)).isoformat(),
                               'decision': decision,
                               'decision_note': 'candidate still requires native order/sizing/confirmation; not an executed order',
                               'entry_signals_in_checked_window': int(sample['enter_long'].sum())}
            except ValueError:
                pairs[pair] = {'status': 'invalid', 'candles': len(frame)}
        body = {'observed_at': now.isoformat(), 'dry_run': self.config['dry_run'],
                'schema_version':2,
                'exchange': self.config['exchange']['name'], 'risk_ready': self.risk_ready, 'risk': self.risk_state.data,
                'pairs': pairs, 'holdout_prices_inspected': False}
        path = Path(self.config['user_data_dir']) / profile_for(self.config['exchange']['name']).state_folder / 'status.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(body, indent=2, allow_nan=False) + '\n')
        temp.replace(path)

    def _entry_context(self, pair, now, rate, amount=None):
        validate_paper_config(self.config)
        if (not getattr(self, "risk_ready", False) or not self.risk_state.allowed(now)
                or Trade.get_trades_proxy(is_open=True) or not finite_positive(rate)):
            raise ValueError("Risk state, price or position limit forbids entry")
        observed = self.risk_state.data.get("observed_at")
        if observed is None or not 0 <= (now - datetime.fromisoformat(observed)).total_seconds() <= 30:
            raise ValueError("Risk observation is stale")
        frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(frame) < self.startup_candle_count:
            raise ValueError("Insufficient warmup")
        sample = frame.tail(self.startup_candle_count)
        validate_candles(sample)
        require_current_window(sample["date"].iloc[0].to_pydatetime(), now, now)
        age = (now - sample["date"].iloc[-1]).total_seconds()
        if not 3600 <= age <= 7200 + 300 or sample["volume"].iloc[-1] <= 0:
            raise ValueError("Unclosed, stale or zero-volume candle")
        if not all(math.isfinite(sample[key].iloc[-1]) for key in ("sma_fast", "sma_slow", "rsi")):
            raise ValueError("Invalid indicators")
        market = self.dp.market(pair)
        if not market or market.get("active") is not True or not market.get("spot"):
            raise ValueError("Inactive or non-spot market")
        if market.get("taker") is None or market["taker"] > self.policy.fee:
            raise ValueError("Unknown or underestimated market fee")
        tick = time.monotonic()
        book = self.dp.orderbook(pair, 20)
        if time.monotonic() - tick > 3:
            raise ValueError("Book request too slow")
        bid, ask = book["bids"][0][0], book["asks"][0][0]
        if not finite_positive(bid, ask) or bid > ask:
            raise ValueError("Crossed or invalid order book")
        # The API response can be newer than callback current_time. Compare to receipt,
        # allowing 2s clock jitter while preserving the 30s stale limit.
        received = datetime.now(timezone.utc)
        if book.get("timestamp") is not None and not -2 <= received.timestamp() - book["timestamp"] / 1000 <= 30:
            raise ValueError("Stale order book")
        if (ask - bid) / ((ask + bid) / 2) > self.policy.spread or abs(rate / ask - 1) > self.policy.slippage:
            raise ValueError("Spread or price movement exceeds cost budget")
        minimum_amount = market.get("limits", {}).get("amount", {}).get("min")
        minimum_cost = minimum_notional(self.config['exchange']['name'], market, rate)
        if amount is not None:
            if not finite_positive(amount) or amount < minimum_amount:
                raise ValueError("Order is below minimum amount")
            remaining, cost = amount, 0.0
            for price, quantity, *_ in book["asks"]:
                if not finite_positive(price, quantity):
                    raise ValueError("Invalid book depth")
                filled = min(remaining, quantity)
                cost += filled * price
                remaining -= filled
                if remaining <= 1e-12:
                    break
            if remaining > 1e-12 or cost / amount > ask * (1 + self.policy.slippage):
                raise ValueError("Insufficient depth or excessive impact")
        equity, free = self._equity()
        return equity, free, minimum_cost

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            if leverage != 1 or side != "long":
                return 0.0
            equity, free, minimum = self._entry_context(pair, current_time, current_rate)
            return min(proposed_stake, self.policy.stake(equity, free,
                       max(minimum, min_stake or minimum), max_stake))
        except Exception as error:
            logger.info("Paper sizing denied %s: %s", pair,
                        str(error) if isinstance(error, ValueError) else type(error).__name__)
            return 0.0  # Avoid native exception fallback to proposed stake.

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
        try:
            if pair not in self.config["exchange"]["pair_whitelist"] or side != "long" or order_type != "limit":
                return False
            equity, free, minimum = self._entry_context(pair, current_time, rate, amount)
            # Recheck after Freqtrade's min-stake clamp; never accept an enlarged position.
            rounded = self.dp._exchange.amount_to_precision(pair, amount)
            minimum_amount = self.dp.market(pair)['limits']['amount']['min']
            return (finite_positive(rounded) and rounded >= minimum_amount
                    and self.policy.allows_notional(rounded * rate, equity, free, minimum))
        except Exception as error:
            logger.info("Paper entry denied %s: %s", pair,
                        str(error) if isinstance(error, ValueError) else type(error).__name__)
            return False  # Native callback default is permissive on unhandled exceptions.
