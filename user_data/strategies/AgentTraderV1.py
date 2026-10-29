"""Fixed spot paper strategy. Closed 5m signals; only fully closed 1h information."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import logging
import math
import sys
import time

import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from agenttrader_v1 import Journal, Policy, validate_config, validate_market, positive
from agenttrader_v1_compare import validate_exit_book

logger=logging.getLogger(__name__)


class AgentTraderV1(IStrategy):
    INTERFACE_VERSION=3
    timeframe='5m'
    can_short=False
    # Per timeframe: DataProvider fetches 1h separately (not 200 * 12 base candles).
    # EMA200 seed error decays by (199/201)**1000 after 1200 observations.
    # 1199 warmup + current candle = 4 OKX spot calls of 300, below the 1499 cap.
    # Reproduce convergence checks: scripts/agenttrader_v1_startup_analysis.py.
    startup_candle_count=1199
    process_only_new_candles=True
    minimal_roi={'0':.04}
    stoploss=-.02
    trailing_stop=False
    use_exit_signal=True
    exit_profit_only=False
    position_adjustment_enable=False
    order_types={'entry':'limit','exit':'market','stoploss':'market','stoploss_on_exchange':False}
    order_time_in_force={'entry':'GTC','exit':'GTC'}

    def informative_pairs(self):
        return [(pair,'1h') for pair in self.config['exchange']['pair_whitelist']]

    def bot_start(self,**kwargs):
        validate_config(self.config)
        self.policy=Policy()
        self.journal=Journal(Path(self.config['user_data_dir'])/'agenttrader-v1/journal.sqlite')
        self.ready=False

    def bot_loop_start(self,current_time,**kwargs):
        self.ready=False
        try:
            validate_config(self.config)
            self.wallets.update()
            self.free=self.wallets.get_free('USDT')
            closed=[{'id':t.id,'pair':t.pair,'closed_at':t.close_date_utc.isoformat(),
                     'native_pnl':t.close_profit_abs,
                     'pnl':t.close_profit_abs-self.policy.slippage*(t.stake_amount+t.amount*t.close_rate),
                     'note':'native fees included; extra adverse slippage deducted from both sides'}
                    for t in Trade.get_trades_proxy(is_open=False)]
            # Native wallets reserve funds for unfilled orders. Account by PnL so
            # reservations never become fake drawdown or duplicate equity.
            equity=self.policy.initial+sum(t['pnl'] for t in closed)
            for trade in Trade.get_trades_proxy(is_open=True):
                if trade.nr_of_successful_entries<=0:
                    continue
                book=self.dp.orderbook(trade.pair,20)
                bid=validate_exit_book(book,trade.amount,datetime.now(timezone.utc))
                equity+=trade.calculate_profit(bid*(1-self.policy.slippage)).profit_abs-self.policy.slippage*trade.stake_amount
            self.journal.observe(current_time,equity,closed)
            for pair in self.config['exchange']['pair_whitelist']:
                frame,_=self.dp.get_analyzed_dataframe(pair,self.timeframe)
                if frame.empty: continue
                row=frame.iloc[-1]
                self.journal.record(current_time,'signal',pair,candle=str(row['date']),
                    entry=int(row.get('enter_long',0)),exit=int(row.get('exit_long',0)))
            self.ready=True
        except Exception as error:
            logger.warning('AgentTrader entries blocked: %s',type(error).__name__)
            try: self.journal.record(current_time,'rejection',reason=type(error).__name__)
            except Exception: pass

    def populate_indicators(self,dataframe,metadata):
        for period in (9,21,200):
            dataframe['ema'+str(period)]=ta.EMA(dataframe,timeperiod=period)
        dataframe['rsi']=ta.RSI(dataframe,timeperiod=14)
        hourly=self.dp.get_pair_dataframe(pair=metadata['pair'],timeframe='1h')
        for period in (9,21,200):
            hourly['ema'+str(period)]=ta.EMA(hourly,timeperiod=period)
        # Official helper shifts informative timestamps by 1h-5m before forward fill.
        return merge_informative_pair(dataframe,hourly,'5m','1h',ffill=True)

    def populate_entry_trend(self,dataframe,metadata):
        dataframe['enter_long']=0
        signal=((dataframe.ema9>dataframe.ema21)&(dataframe.ema9.shift(1)<=dataframe.ema21.shift(1))
                &(dataframe.close>dataframe.ema200)&(dataframe.close_1h>dataframe.ema200_1h)
                &(dataframe.ema9_1h>dataframe.ema21_1h)&(dataframe.rsi>=50)&(dataframe.rsi<70)
                &(dataframe.volume>0))
        dataframe.loc[signal,['enter_long','enter_tag']]=(1,'ema9_21_up_1h_rsi')
        return dataframe

    def populate_exit_trend(self,dataframe,metadata):
        dataframe['exit_long']=0
        signal=(((dataframe.ema9<dataframe.ema21)&(dataframe.ema9.shift(1)>=dataframe.ema21.shift(1)))
                |(dataframe.rsi>=75))&(dataframe.volume>0)
        dataframe.loc[signal,['exit_long','exit_tag']]=(1,'ema_down_or_rsi75')
        return dataframe

    def _context(self,pair,now):
        validate_config(self.config)
        if not getattr(self,'ready',False) or not self.journal.allowed(now) or Trade.get_trades_proxy(is_open=True):
            raise ValueError('Risk pause/position limit/stale observation')
        frame,_=self.dp.get_analyzed_dataframe(pair,self.timeframe)
        if len(frame)<201: raise ValueError('Insufficient warmup')
        row=frame.iloc[-1]
        age=(now-row['date']).total_seconds()
        if not 300<=age<=630 or row.volume<=0:
            raise ValueError('Unclosed/stale/zero volume candle')
        if any(not math.isfinite(float(row[k])) for k in ('ema9','ema21','ema200','rsi','ema200_1h','ema9_1h','ema21_1h')):
            raise ValueError('Indicators not warmed up')
        if int(row.get('enter_long',0))!=1 or int(row.get('exit_long',0))==1:
            raise ValueError('No valid entry signal')

    def custom_stake_amount(self,pair,current_time,current_rate,proposed_stake,min_stake,max_stake,leverage,entry_tag,side,**kwargs):
        try:
            self._context(pair,current_time)
            if leverage!=1 or side!='long': raise ValueError('Invalid side/leverage')
            stake=min(self.policy.stake(self.free),proposed_stake,max_stake)
            if stake<(min_stake or 0): raise ValueError('Minimum exceeds cap')
            return stake
        except Exception as error:
            try: self.journal.record(current_time,'rejection',pair,reason=str(error))
            except Exception: pass
            return 0.0

    def confirm_trade_entry(self,pair,order_type,amount,rate,time_in_force,current_time,entry_tag,side,**kwargs):
        try:
            self._context(pair,current_time)
            if side!='long' or order_type!='limit': raise ValueError('Invalid side/order type')
            started=time.monotonic()
            book=self.dp.orderbook(pair,20)
            if time.monotonic()-started>3: raise ValueError('Slow orderbook')
            details=validate_market(self.dp.market(pair),book,rate,amount,datetime.now(timezone.utc))
            if details['cash']>self.free: raise ValueError('Insufficient cash')
            if -self.journal.state()['daily_pnl']+details['planned_loss']>self.policy.daily_loss:
                raise ValueError('Planned loss exceeds remaining daily loss budget')
            self.journal.record(current_time,'entry_confirmed',pair,rate=rate,amount=amount,**details)
            return True
        except Exception as error:
            try: self.journal.record(current_time,'rejection',pair,reason=str(error))
            except Exception: pass
            return False

    def custom_exit(self,pair,trade,current_time,current_rate,current_profit,**kwargs):
        # Assumed extra slippage .05% per side must be in the persisted native PnL.
        # Native fees are .10%/side; custom_exit cannot alter native fills. We persist
        # separate cost-adjusted comparison PnL; native dry-run PnL is identified.
        if getattr(self,'ready',False) and (self.journal.state()['halted'] or self.journal.state().get('daily_halted',False) or self.journal.state()['daily_pnl']<=-2):
            return 'risk_pause_exit'
        return None

    def confirm_trade_exit(self,pair,trade,order_type,amount,rate,time_in_force,exit_reason,current_time,**kwargs):
        """Fail closed even for protective simulated fills; no unavailable-book fills."""
        try:
            validate_config(self.config)
            market=self.dp.market(pair)
            if (not market or market.get('active') is not True or market.get('spot') is not True
                    or market.get('contract') or pair not in self.config['exchange']['pair_whitelist']):
                raise ValueError('Inactive/non-spot exit market')
            fee=market.get('taker')
            if isinstance(fee,bool) or not isinstance(fee,(int,float)) or not math.isfinite(fee) or not 0<=fee<=self.policy.fee:
                raise ValueError('Exit fee metadata unavailable/underestimated')
            step=market.get('precision',{}).get('amount')
            tick=market.get('precision',{}).get('price')
            if (not positive(step,tick,amount,rate)
                    or Decimal(str(amount))%Decimal(str(step))!=0
                    or Decimal(str(rate))%Decimal(str(tick))!=0):
                raise ValueError('Invalid exit quantity/price precision')
            minimum=market.get('limits',{}).get('amount',{}).get('min')
            if not positive(minimum) or amount<minimum:
                raise ValueError('Exit below known exchange minimum')
            for field,value in (('amount',amount),('cost',amount*rate)):
                bounds=market.get('limits',{}).get(field,{})
                if bounds.get('min') is not None and value<bounds['min']:
                    raise ValueError('Exit below minimum '+field)
                if bounds.get('max') is not None and value>bounds['max']:
                    raise ValueError('Exit above maximum '+field)
            started=time.monotonic()
            book=self.dp.orderbook(pair,20)
            if time.monotonic()-started>3: raise ValueError('Slow exit book')
            executable=validate_exit_book(book,amount,datetime.now(timezone.utc))
            if abs(rate/executable-1)>self.policy.slippage:
                raise ValueError('Native exit price outside execution budget')
            self.journal.record(current_time,'exit_confirmed',pair,amount=amount,rate=rate,reason=exit_reason)
            return True
        except Exception as error:
            try: self.journal.record(current_time,'rejection',pair,stage='exit',reason=str(error))
            except Exception: pass
            return False
