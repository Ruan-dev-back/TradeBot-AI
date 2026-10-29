"""Exploratory common-window replay. Historical books are unavailable: no fills asserted."""
from datetime import datetime, timezone
import json
from pathlib import Path
from agenttrader_v1 import PAIRS, Policy, public_get, public_snapshot, validate_market, positive
from decimal import Decimal, ROUND_DOWN


def ema(values,period):
    result=[]; value=None
    for index,close in enumerate(values):
        if index<period-1: result.append(None); continue
        value=sum(values[:period])/period if value is None else value+(2/(period+1))*(close-value)
        result.append(value)
    return result


def rsi(values,period=14):
    result=[None]*len(values)
    if len(values)<=period: return result
    gains=sum(max(0,values[i]-values[i-1]) for i in range(1,period+1))/period
    losses=sum(max(0,values[i-1]-values[i]) for i in range(1,period+1))/period
    for i in range(period,len(values)):
        if i>period:
            delta=values[i]-values[i-1]
            gains=(gains*(period-1)+max(0,delta))/period
            losses=(losses*(period-1)+max(0,-delta))/period
        result[i]=100 if losses==0 and gains>0 else 0 if losses==0 else 100-100/(1+gains/losses)
    return result


def signals(candles,hourly):
    """Candles are ascending lists [timestamp_ms,open,high,low,close,volume]."""
    closes=[r[4] for r in candles]; hc=[r[4] for r in hourly]
    e9,e21,e200=(ema(closes,p) for p in (9,21,200))
    h9,h21,h200=(ema(hc,p) for p in (9,21,200))
    rs=rsi(closes); result=[]; hour=-1
    for i,row in enumerate(candles):
        close_time=row[0]+300000
        while hour+1<len(hourly) and hourly[hour+1][0]+3600000<=close_time: hour+=1
        ready=i>=200 and hour>=199 and rs[i] is not None
        entry=bool(ready and e9[i]>e21[i] and e9[i-1]<=e21[i-1] and closes[i]>e200[i]
                   and hc[hour]>h200[hour] and h9[hour]>h21[hour] and 50<=rs[i]<70 and row[5]>0)
        exit_=bool(ready and ((e9[i]<e21[i] and e9[i-1]>=e21[i-1]) or rs[i]>=75) and row[5]>0)
        baseline=bool(ready and e21[i]>e200[i] and e21[i-1]<=e200[i-1] and row[5]>0)
        baseline_exit=bool(ready and e21[i]<e200[i] and e21[i-1]>=e200[i-1])
        result.append({'ready':ready,'entry':entry,'exit':exit_,'baseline_entry':baseline,'baseline_exit':baseline_exit})
    return result


def fetch_candles(pair,bar,count):
    rows={}; after=''; now=datetime.now(timezone.utc).timestamp()*1000
    while len(rows)<count:
        path='/api/v5/market/history-candles?instId='+pair.replace('/','-')+'&bar='+bar+'&limit=100'+after
        batch=public_get(path)
        if not batch: break
        for row in batch:
            timestamp=int(row[0])
            if timestamp<1782864000000: raise ValueError('Reserved historical window forbidden')
            if str(row[-1])=='1' and timestamp<now:
                rows[timestamp]=[timestamp]+[float(x) for x in row[1:6]]
        oldest=min(int(r[0]) for r in batch)
        next_after='&after='+str(oldest)
        if next_after==after: break
        after=next_after
    result=[rows[k] for k in sorted(rows)][-count:]
    interval=300000 if bar=='5m' else 3600000
    if len(result)<count or any(b[0]-a[0]!=interval for a,b in zip(result,result[1:])):
        raise ValueError('Incomplete or gapped public candles')
    return result


def replay(candles,hourly,market,book):
    """No historical trades simulated without contemporaneous executable books.

    Returns comparable signal counts and price-only B&H diagnostic, plus a blocked
    execution status. This deliberately avoids manufacturing liquidity evidence.
    """
    sig=signals(candles,hourly)
    indexes=[i for i,s in enumerate(sig) if s['ready']]
    if len(indexes)<2: raise ValueError('Insufficient common warmed evaluation window')
    start,end=indexes[0],indexes[-1]
    price_return=candles[end][4]/candles[start][4]-1
    p=Policy(); rate=float(book['asks'][0][0]); step=Decimal(str(market['precision']['amount']))
    amount=float((Decimal(str(p.stake()/rate))/step).to_integral_value(rounding=ROUND_DOWN)*step)
    validation=validate_market(market,book,rate,amount)
    return {'status':'blocked_historical_execution_metadata',
            'reason':'Historical book/depth, spread and fee tier unavailable. Current preflight cannot validate historical fills.',
            'current_preflight':validation,
            'evaluation_start_utc':datetime.fromtimestamp(candles[start][0]/1000,timezone.utc).isoformat(),
            'evaluation_end_utc':datetime.fromtimestamp(candles[end][0]/1000,timezone.utc).isoformat(),
            'strategy':{'entry_signals':sum(s['entry'] for s in sig[start:end+1]),'trades':None,'net_pnl':None},
            'baseline_ema21_200':{'entry_signals':sum(s['baseline_entry'] for s in sig[start:end+1]),'trades':None,'net_pnl':None},
            'buy_and_hold':{'price_return_diagnostic':price_return,'trades':None,'net_pnl':None},
            'cost_assumptions':{'fee_per_side':p.fee,'slippage_per_side':p.slippage},
            'note':'Price return is not a simulated portfolio return. No ranking or profitability claim.'}


def simulate(candles,hourly,market,books):
    """Replay verified snapshots keyed by next-candle open ms; fixtures must be labelled.

    All alternatives start with 100 USDT, use one <=10 cash position, and identical
    costs. Missing executable historical books reject trades, never create fills.
    This snapshot checkpoint replay samples stop/TP at book observation times;
    it does not pretend to reproduce unknown intrabar paths. Only closed-candle
    signals trigger next-open entries. B&H holds until the final checkpoint.
    """
    p=Policy(); decisions=signals(candles,hourly); result={}
    for strategy in ('strategy','buy_and_hold','baseline_ema21_200'):
        cash=100.; peak=100.; position=None; trades=[]; rejected=[]; curve=[]; halted=False; daily={}
        start_equity={}; bought=False; paused_days=set()
        for i in range(1,len(candles)):
            row=candles[i]; previous=decisions[i-1]
            now=datetime.fromtimestamp(row[0]/1000,timezone.utc); day=now.date().isoformat()
            start_equity.setdefault(day,cash if position is None else cash+position['stake'])
            if position is not None:
                exit_price=None; reason=None
                stop=position['entry']*(1-p.stop); take=position['entry']*(1+p.take_profit)
                if strategy!='buy_and_hold' and row[1]<=stop: exit_price=row[1]; reason='stop_checkpoint'
                elif strategy!='buy_and_hold' and row[1]>=take: exit_price=row[1]; reason='take_profit_checkpoint'
                elif strategy=='strategy' and previous['exit'] or strategy=='baseline_ema21_200' and previous['baseline_exit']:
                    exit_price=row[1]; reason='signal'
                elif i==len(candles)-1:
                    exit_price=row[1]; reason='end_of_window'
                if exit_price is not None:
                    try:
                        exit_price=validate_exit_book(books[row[0]],position['amount'],now)
                        pnl=p.pnl(position['stake'],position['entry'],exit_price)
                        cash+=position['stake']*(1+p.fee)+pnl
                        trade={**position,'exit':exit_price,'pnl':pnl,'exit_utc':now.isoformat(),'reason':reason}
                        trades.append(trade); daily[day]=daily.get(day,0)+min(0,pnl); position=None
                    except (KeyError,ValueError) as error:
                        rejected.append({'utc':now.isoformat(),'stage':'exit','reason':str(error)})
            equity=cash if position is None else cash+position['stake']*(1+p.fee)+p.pnl(position['stake'],position['entry'],row[1])
            peak=max(peak,equity); halted=halted or (peak-equity)/peak>=p.drawdown
            loss=max(-daily.get(day,0),start_equity[day]-equity)
            if loss>=p.daily_loss-1e-12:
                paused_days.add(day)
            signal=previous['ready'] and (previous['entry'] if strategy=='strategy' else previous['baseline_entry'] if strategy=='baseline_ema21_200' else not bought)
            if signal and position is None and not halted and day not in paused_days and loss<p.daily_loss and i<len(candles)-1:
                try:
                    book=books[row[0]]
                    rate=float(book['asks'][0][0]); step=Decimal(str(market['precision']['amount']))
                    amount=float((Decimal(str(p.stake(cash)/rate))/step).to_integral_value(rounding=ROUND_DOWN)*step)
                    detail=validate_market(market,book,rate,amount,now)
                    if loss+detail['planned_loss']>p.daily_loss: raise ValueError('Remaining daily loss budget')
                    stake=detail['notional']; cash-=stake*(1+p.fee)
                    position={'entry':rate,'stake':stake,'amount':amount,'entry_utc':now.isoformat()}; bought=True
                except (KeyError,ValueError) as error:
                    rejected.append({'utc':now.isoformat(),'reason':str(error)})
            equity=cash if position is None else cash+position['stake']*(1+p.fee)+p.pnl(position['stake'],position['entry'],row[1])
            curve.append({'utc':now.isoformat(),'equity':equity})
        result[strategy]={'trades':trades,'rejections':rejected,'equity':curve,
                          'net_pnl':curve[-1]['equity']-100.,'realized_pnl':sum(t['pnl'] for t in trades),
                          'open_position':position,'halted':halted,'model':'snapshot checkpoints; no intrabar path assumption'}
    return result


def validate_exit_book(book,amount,now):
    timestamp=book.get('timestamp')
    if timestamp is None or not -2<=now.timestamp()-float(timestamp)/1000<=30:
        raise ValueError('Missing/stale exit liquidity evidence')
    try:
        top=float(book['bids'][0][0]); remaining=amount; proceeds=0.
        if not positive(top,amount): raise ValueError('Invalid exit price/quantity')
        for price,quantity,*_ in book['bids']:
            price,quantity=float(price),float(quantity)
            if not positive(price,quantity): raise ValueError('Invalid exit depth')
            fill=min(remaining,quantity); proceeds+=fill*price; remaining-=fill
            if remaining<=1e-14: break
        if not positive(proceeds) or remaining>1e-14 or abs(proceeds/amount/top-1)>.0005:
            raise ValueError('Exit depth exceeds slippage budget')
        return proceeds/amount
    except (KeyError,IndexError,TypeError,ZeroDivisionError) as error:
        raise ValueError('Invalid exit book') from error


def compare_public(output):
    result={'created_at':datetime.now(timezone.utc).isoformat(),'source':'OKX public recent confirmed candles',
            'pairs':{},'status':'blocked'}
    folder=Path(output); folder.mkdir(parents=True,exist_ok=True)
    for pair in PAIRS:
        try:
            market,book=public_snapshot(pair)
            candles=fetch_candles(pair,'5m',600)
            hourly=fetch_candles(pair,'1H',260)
            # Refresh executable book after paginated candle download.
            market,book=public_snapshot(pair)
            result['pairs'][pair]=replay(candles,hourly,market,book)
        except Exception as error:
            result['pairs'][pair]={'status':'blocked','reason':str(error)}
    (folder/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
