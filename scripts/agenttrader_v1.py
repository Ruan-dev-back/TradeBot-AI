"""AgentTrader V1: public OKX only, local Freqtrade dry run, fixed risk envelope."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import csv
import json
import math
import os
import secrets
from pathlib import Path
import sqlite3
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'user_data' / 'agenttrader-v1'
PAIRS = ('BTC/USDT', 'ETH/USDT')
CONFIG = ROOT / 'user_data/config.agenttrader-v1.json'


def positive(*values):
    return all(not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values)


@dataclass(frozen=True)
class Policy:
    initial: float = 100.0
    cap: float = 10.0
    risk: float = .50
    stop: float = .02
    take_profit: float = .04
    daily_loss: float = 2.0
    drawdown: float = .05
    fee: float = .001  # Provisional public tier assumption, per side; no private fee lookup.
    slippage: float = .0005  # Provisional adverse execution assumption, per side.

    def __post_init__(self):
        if self != Policy.__new_defaults__():
            raise ValueError('V1 policy is fixed; enlarged or changed policy forbidden')

    @classmethod
    def __new_defaults__(cls):
        value = object.__new__(cls)
        for name, field in cls.__dataclass_fields__.items():
            object.__setattr__(value, name, field.default)
        return value

    def stake(self, free_cash=100):
        if not positive(free_cash):
            return 0.0
        return min(self.cap, free_cash) / ((1 + self.fee) * (1 + self.slippage))

    def pnl(self, stake, entry, exit):
        if not positive(stake, entry, exit):
            raise ValueError('Invalid PnL inputs')
        return stake * ((exit * (1-self.slippage) * (1-self.fee)) /
                        (entry * (1+self.slippage)) - (1+self.fee))


def validate_config(config, environ=None):
    expected = {'dry_run': True, 'dry_run_wallet': 100, 'max_open_trades': 1,
                'stake_amount': 10, 'stake_currency': 'USDT', 'trading_mode': 'spot',
                'margin_mode': '', 'timeframe': '5m', 'fee': .001,
                'strategy': 'AgentTraderV1', 'force_entry_enable': False}
    for key, value in expected.items():
        if isinstance(config.get(key),bool) != isinstance(value,bool) or config.get(key) != value:
            raise ValueError('Invalid fixed V1 setting: ' + key)
    if any(k.upper().startswith('FREQTRADE__') for k in (environ or {})):
        raise ValueError('FREQTRADE overrides forbidden')
    ex = config.get('exchange', {})
    if ex.get('name') != 'okx' or ex.get('pair_whitelist') != list(PAIRS) or ex.get('pair_blacklist'):
        raise ValueError('Only OKX BTC/USDT ETH/USDT allowed')
    if set(ex) - {'name','key','secret','password','ccxt_config','ccxt_async_config','pair_whitelist','pair_blacklist','enable_ws'}:
        raise ValueError('Unknown exchange settings forbidden')
    if any(ex.get(k) for k in ('key','secret','password')):
        raise ValueError('Credentials forbidden')
    for name in ('ccxt_config','ccxt_async_config'):
        settings = ex.get(name, {})
        if set(settings) - {'enableRateLimit','timeout','requests_trust_env','aiohttp_trust_env','options'}:
            raise ValueError('CCXT endpoint/credential overrides forbidden')
        if settings.get('options') != {'defaultType':'spot','fetchMarkets':{'types':['spot']}}:
            raise ValueError('Only spot market options allowed')
    runmode = str(config.get('runmode', 'dry_run')).lower()
    if runmode not in ('dry_run','runmode.dry_run'):
        raise ValueError('Only native dry run allowed')
    if (config.get('stoploss', -.02) != -.02 or config.get('minimal_roi', {'0':.04}) != {'0':.04}
            or config.get('position_adjustment_enable', False) or config.get('trailing_stop', False)
            or config.get('order_types', {}).get('stoploss_on_exchange', False)):
        raise ValueError('Risk/real stop overrides forbidden')
    if config.get('db_url') != 'sqlite:////freqtrade/user_data/agenttrader-v1/trades.sqlite':
        raise ValueError('Dedicated V1 SQLite required')
    api = config.get('api_server', {})
    if api.get('listen_ip_address') != '0.0.0.0' or api.get('listen_port') != 8080:
        raise ValueError('Fixed container API binding required')
    if set(api)-{'enabled','listen_ip_address','listen_port','verbosity','enable_openapi','CORS_origins','username','password','jwt_secret_key','ws_token'}:
        raise ValueError('Unknown API override forbidden')
    if api.get('enabled') is not True or api.get('enable_openapi') is not False or api.get('CORS_origins') != []:
        raise ValueError('Fixed local API settings required')
    if config.get('telegram', {}).get('enabled') is not False:
        raise ValueError('Telegram forbidden')
    if config.get('pairlists') != [{'method':'StaticPairList'}]:
        raise ValueError('Only static pairs allowed')
    if config.get('can_short', False) or config.get('leverage', 1) != 1:
        raise ValueError('Short/leverage forbidden')


def validate_market(market, book, rate, amount, now=None):
    """Validate exact native rounded order. Never round up to exchange minima."""
    p = Policy()
    if not positive(rate, amount):
        raise ValueError('Invalid rate/amount')
    if (not market or market.get('active') is not True or market.get('spot') is not True
            or market.get('contract') or market.get('symbol') not in PAIRS):
        raise ValueError('Inactive/non-spot/unapproved market')
    fee = market.get('taker')
    if isinstance(fee,bool) or not isinstance(fee, (int,float)) or not math.isfinite(fee) or not 0 <= fee <= p.fee:
        raise ValueError('Missing or underestimated public fee metadata')
    limits, precision = market.get('limits', {}), market.get('precision', {})
    minimum = limits.get('amount', {}).get('min')
    tick, step = precision.get('price'), precision.get('amount')
    if not positive(minimum, tick, step) or amount < minimum:
        raise ValueError('Missing minimum/precision or below minimum')
    # OKX/CCXT uses tick-size precision, not decimal-place counts.
    if Decimal(str(amount)) % Decimal(str(step)) != 0 or Decimal(str(rate)) % Decimal(str(tick)) != 0:
        raise ValueError('Amount/price violates tick precision')
    notional = rate * amount
    for kind, value in (('amount',amount),('price',rate),('cost',notional)):
        bound = limits.get(kind,{})
        for direction, comparator in (('min',lambda a,b:a < b),('max',lambda a,b:a > b)):
            v = bound.get(direction)
            if v is not None and (not positive(v) or comparator(value,v)):
                raise ValueError('Exchange ' + kind + ' limit')
    now = now or datetime.now(timezone.utc)
    ts = book.get('timestamp')
    if ts is None or not -2 <= now.timestamp()-float(ts)/1000 <= 30:
        raise ValueError('Missing/stale public book timestamp')
    try:
        bid, ask = float(book['bids'][0][0]), float(book['asks'][0][0])
        if not positive(bid,ask) or bid > ask or (ask-bid)/bid > .001 or abs(rate/ask-1) > p.slippage:
            raise ValueError('Spread/rate movement exceeds budget')
        for side in ('asks','bids'):
            remaining, cost = amount, 0.0
            for price, quantity, *_ in book[side]:
                price,quantity = float(price),float(quantity)
                if not positive(price,quantity):
                    raise ValueError('Invalid depth')
                fill = min(remaining,quantity)
                cost += fill*price
                remaining -= fill
                if remaining <= 1e-14:
                    break
            top = ask if side == 'asks' else bid
            if remaining > 1e-14 or abs(cost/amount/top-1) > p.slippage:
                raise ValueError('Insufficient liquidity or excessive slippage')
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('Invalid order book') from error
    cash = notional*(1+p.fee)*(1+p.slippage)
    planned_loss = -p.pnl(notional,rate,rate*(1-p.stop))
    if cash > p.cap+1e-10 or planned_loss > p.risk+1e-10:
        raise ValueError('Fixed cash/exposure/risk cap exceeded')
    return {'notional':notional,'cash':cash,'planned_loss':planned_loss,
            'fee_per_side_assumed':p.fee,'slippage_per_side_assumed':p.slippage}


class Journal:
    def __init__(self,path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,utc TEXT,kind TEXT,pair TEXT,body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS trades(id TEXT PRIMARY KEY,closed_at TEXT,pair TEXT,pnl REAL,body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS equity(id INTEGER PRIMARY KEY,utc TEXT,value REAL,drawdown REAL,daily_pnl REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT)')
            db.execute('INSERT OR IGNORE INTO state VALUES(1,?)',(json.dumps({'peak':100.,'halted':False,'equity':100.,'daily_pnl':0.,'day':None}),))

    def record(self,now,kind,pair=None,**body):
        if now.tzinfo is None:
            raise ValueError('UTC time required')
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT INTO events(utc,kind,pair,body) VALUES(?,?,?,?)',
                       (now.isoformat(),kind,pair,json.dumps(body,allow_nan=False)))

    def state(self):
        with closing(sqlite3.connect(self.path)) as db:
            return json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])

    def observe(self,now,equity,closed):
        if not positive(equity) or now.tzinfo is None:
            raise ValueError('Invalid equity/time')
        day = now.astimezone(timezone.utc).date().isoformat()
        with closing(sqlite3.connect(self.path)) as db,db:
            state = json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            for trade in closed:
                when = datetime.fromisoformat(str(trade['closed_at']))
                pnl = trade['pnl']
                if when.tzinfo is None or when > now or not isinstance(pnl,(int,float)) or not math.isfinite(pnl):
                    raise ValueError('Invalid closed trade')
                db.execute('INSERT OR IGNORE INTO trades VALUES(?,?,?,?,?)',
                    (str(trade['id']),when.astimezone(timezone.utc).isoformat(),trade['pair'],pnl,json.dumps(trade,allow_nan=False)))
            # Gross losing trades count toward budget; wins never replenish daily loss allowance.
            losses = sum(min(0,row[0]) for row in db.execute('SELECT pnl FROM trades WHERE substr(closed_at,1,10)=?',(day,)))
            day_start=state.get('day_start_equity',100.) if state.get('day')==day else state['equity']
            daily_loss=max(-losses,day_start-equity)
            daily_halted=(state.get('day')==day and state.get('daily_halted',False)) or daily_loss>=2-1e-12
            peak = max(100.,state['peak'],equity)
            dd = (peak-equity)/peak
            state.update(peak=peak,equity=equity,drawdown=dd,daily_pnl=-daily_loss,day=day,day_start_equity=day_start,daily_halted=daily_halted,
                         halted=state['halted'] or dd >= .05-1e-12,observed_at=now.isoformat())
            db.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(state,allow_nan=False),))
            db.execute('INSERT INTO equity(utc,value,drawdown,daily_pnl) VALUES(?,?,?,?)',(now.isoformat(),equity,dd,-daily_loss))
        return self.allowed(now)

    def allowed(self,now):
        state = self.state()
        observed = state.get('observed_at')
        return bool(observed and now.tzinfo is not None and 0 <= (now-datetime.fromisoformat(observed)).total_seconds() <= 30
                    and not state['halted'] and not state.get('daily_halted',False) and state['day'] == now.astimezone(timezone.utc).date().isoformat()
                    and state['daily_pnl'] > -2)

    def export(self,folder):
        folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
        result={}
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory=sqlite3.Row
            for table in ('events','trades','equity','state'):
                rows=[dict(row) for row in db.execute('SELECT * FROM '+table)]
                result[table]=rows
                with (folder/(table+'.csv')).open('w',newline='',encoding='utf-8') as output:
                    writer=csv.DictWriter(output,fieldnames=rows[0].keys() if rows else [x[1] for x in db.execute('PRAGMA table_info('+table+')')])
                    writer.writeheader(); writer.writerows(rows)
        (folder/'journal.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        return result


def public_get(path):
    if not path.startswith(('/api/v5/public/instruments?instType=SPOT','/api/v5/market/books?','/api/v5/market/history-candles?')):
        raise ValueError('Public endpoint not allowed')
    request=urllib.request.Request('https://www.okx.com'+path,headers={'User-Agent':'AgentTrader-V1-public-paper'})
    with urllib.request.urlopen(request,timeout=15) as response:
        body=json.load(response)
    if body.get('code') != '0':
        raise ValueError('OKX public API error')
    return body['data']


def public_snapshot(pair):
    if pair not in PAIRS: raise ValueError('Unapproved pair')
    instrument=public_get('/api/v5/public/instruments?instType=SPOT&instId='+pair.replace('/','-'))[0]
    if (instrument.get('instId') != pair.replace('/','-') or instrument.get('instType') != 'SPOT'
            or instrument.get('quoteCcy') != 'USDT' or instrument.get('baseCcy') != pair.split('/')[0]):
        raise ValueError('Public instrument identity mismatch')
    book=public_get('/api/v5/market/books?instId='+pair.replace('/','-')+'&sz=20')[0]
    market={'symbol':pair,'active':instrument['state']=='live','spot':True,'contract':False,
            'taker':.001,'fee_note':'provisional 0.10% taker assumption; account tier unverified',
            'limits':{'amount':{'min':float(instrument['minSz']),
                       'max':float(instrument['maxLmtSz']) if instrument.get('maxLmtSz') else None}},
            'precision':{'amount':float(instrument['lotSz']),'price':float(instrument['tickSz'])}}
    book={'asks':book['asks'],'bids':book['bids'],'timestamp':int(book['ts'])}
    return market,book


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['preflight','export','compare','run'])
    parser.add_argument('--output',default=str(STATE/'exports'))
    args=parser.parse_args()
    config=json.loads(CONFIG.read_text(encoding='utf-8'))
    validate_config(config,os.environ)
    if args.command=='export':
        Journal(STATE/'journal.sqlite').export(args.output)
        export_native(STATE/'trades.sqlite',args.output)
    elif args.command=='preflight':
        from decimal import ROUND_DOWN
        result={}
        failed=False
        for pair in PAIRS:
            try:
                market,book=public_snapshot(pair)
                rate=float(book['asks'][0][0]); step=Decimal(str(market['precision']['amount']))
                amount=float((Decimal(str(Policy().stake()/rate))/step).to_integral_value(rounding=ROUND_DOWN)*step)
                result[pair]={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'validated','market':market,'validation':validate_market(market,book,rate,amount)}
            except Exception as error:
                failed=True
                result[pair]={'status':'blocked','reason':str(error)}
        STATE.mkdir(parents=True,exist_ok=True)
        (STATE/'preflight.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        Journal(STATE/'journal.sqlite').record(datetime.now(timezone.utc),'preflight',results=result)
        print(json.dumps(result,indent=2))
        if failed: raise ValueError('Public preflight blocked; see preflight.json')
    elif args.command=='compare':
        from agenttrader_v1_compare import compare_public
        print(json.dumps(compare_public(args.output),indent=2))
    else:
        if len(sys.argv)!=2: raise ValueError('Runtime accepts no extra arguments')
        import fcntl
        STATE.mkdir(parents=True,exist_ok=True)
        lock=os.open(STATE/'engine.lock',os.O_CREAT|os.O_RDWR,0o600)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); os.set_inheritable(lock,True)
        runtime=STATE/'runtime.json'
        if runtime.exists():
            previous=json.loads(runtime.read_text())
            auth={k:previous['api_server'][k] for k in ('username','password','jwt_secret_key','ws_token')}
        else:
            auth={'username':'agenttrader','password':secrets.token_urlsafe(24),
                  'jwt_secret_key':secrets.token_urlsafe(32),'ws_token':secrets.token_urlsafe(32)}
        config['api_server'].update(auth)
        fd=os.open(runtime,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as output: json.dump(config,output)
        os.execvp('freqtrade',['freqtrade','trade','--config',str(runtime),'--dry-run'])


def export_native(path,folder):
    """Export only operational columns from the native database, read-only."""
    path=Path(path)
    if not path.exists(): return {'status':'native_database_not_created'}
    allowed=('id','pair','is_open','stake_amount','amount','open_rate','close_rate',
             'close_profit_abs','open_date','close_date')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        present={row[1] for row in db.execute('PRAGMA table_info(trades)')}
        columns=[name for name in allowed if name in present]
        if not columns: raise ValueError('Native trades schema unavailable')
        rows=[dict(row) for row in db.execute('SELECT '+','.join(columns)+' FROM trades')]
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    (folder/'native_trades.json').write_text(json.dumps(rows,indent=2,allow_nan=False),encoding='utf-8')
    with (folder/'native_trades.csv').open('w',newline='',encoding='utf-8') as output:
        writer=csv.DictWriter(output,fieldnames=columns); writer.writeheader(); writer.writerows(rows)
    return {'status':'exported','trades':len(rows)}


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('AgentTrader blocked: '+str(error),file=sys.stderr)
        raise SystemExit(2)
