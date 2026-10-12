"""Read-only portfolio view and durable prospective observation; never sends orders."""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from audit_guard import verify_baseline, require_locked_holdout
from paper_health import readonly, utc
from paper_profiles import profile_for
from paper_status import check

ROOT = Path(__file__).resolve().parents[1]
INTERVAL = 30
MAX_INTERVAL = 45


def encoded(body):
    return json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(body):
    return hashlib.sha256(encoded(body).encode()).hexdigest()


def process_status(root, exchange):
    profile = profile_for(exchange)
    try:
        result = subprocess.run(['docker', 'compose', '-f', str(root/profile.compose_file),
                                 'ps', '--format', 'json', profile.service],
                                capture_output=True, text=True, timeout=5, check=True)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if len(rows) != 1 or rows[0]['State'] != 'running':
            return {'status': 'not_running'}
        identifier = rows[0]['ID']
        if not identifier or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('Invalid container identity')
        fields = subprocess.check_output(['docker', 'inspect', '--format',
              '{{.State.StartedAt}}|{{.RestartCount}}', identifier], text=True, timeout=5).strip().split('|')
        return {'status': 'running', 'container_id': identifier, 'started_at': fields[0],
                'restart_count': int(fields[1]), 'docker_health': rows[0].get('Health')}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return {'status': 'unverified', 'error_type': type(error).__name__}


def portfolio(root, exchange, snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    profile = profile_for(exchange)
    with closing(readonly(root/'user_data'/profile.database)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')  # Trades/orders use one read snapshot, no mutations.
        trades = [dict(row) for row in db.execute('SELECT * FROM trades ORDER BY id')]
        orders = [dict(row) for row in db.execute('SELECT * FROM orders ORDER BY id')]
    realized = 0.0
    unrealized = 0.0
    fees = 0.0
    positions = []
    for trade in trades:
        if trade['exchange'] != exchange or trade['is_short'] or trade['leverage'] != 1:
            raise ValueError('Unexpected native paper position identity')
        if trade['is_open']:
            pair = snapshot['pairs'][trade['pair']]
            book = pair.get('public_book', {})
            amount = trade['amount']
            if amount:
                # Spot long, no adjustments: equivalent to native fee-adjusted liquidation.
                mark = book.get('bid')
                value = trade['open_trade_value']
                fresh = book.get('observed_at') and 0<=(now-utc(book['observed_at'])).total_seconds()<=30
                if mark is None or value is None or not snapshot.get('risk_ready') or not fresh:
                    unrealized = None
                elif unrealized is not None:
                    unrealized += amount*mark*(1-trade['fee_close'])-value
            if realized is not None:
                realized += trade['realized_profit'] or 0.0
            positions.append({k: trade[k] for k in ('id','pair','amount','stake_amount','open_rate','open_date')})
        elif trade['close_profit_abs'] is None:
            realized = None
        elif realized is not None:
            realized += trade['close_profit_abs']
    fills = []
    by_id = {trade['id']: trade for trade in trades}
    for order in orders:
        if not order['order_id'].startswith('dry_run_'):
            raise ValueError('Unexpected non-dry-run order identity')
        filled = order['filled'] or 0.0
        rate = order['average'] or order['price']
        if filled:
            if rate is None:
                fees = None
            elif fees is not None:
                trade = by_id[order['ft_trade_id']]
                fees += filled*rate*trade['fee_open' if order['side']=='buy' else 'fee_close']
        fills.append({k:order[k] for k in ('id','order_id','ft_trade_id','ft_pair','side','status','filled','remaining','average','price','order_date')})
    wallet = snapshot.get('wallet')
    values = (realized, unrealized, fees)
    if any(v is not None and not math.isfinite(v) for v in values):
        raise ValueError('Invalid portfolio values')
    return {'native_trades': len(trades), 'native_orders':len(orders), 'positions': positions,
            'orders': fills, 'realized_pnl_usdt':realized, 'unrealized_pnl_usdt':unrealized,
            'fees_usdt':fees, 'fee_method':'reconstructed from filled notional and native dry fee; not account invoices',
            'wallet':wallet, 'pnl_note':'native closed PnL; open liquidation estimate at public bid, not promised fill'}


def collect(root=ROOT, exchange='okx', now=None, process=None, telemetry_after=None):
    now = now or datetime.now(timezone.utc)
    profile = profile_for(exchange)
    result = {'checked_at':now.isoformat(),'exchange':exchange,'healthy':False,'alerts':[],
              'process':process if process is not None else process_status(root,exchange),
              'snapshot':None,'portfolio':None,'telemetry':[],'private_api_used':False}
    try:
        snapshot = json.loads((root/'user_data'/profile.state_folder/'status.json').read_text())
        result['snapshot'] = snapshot
        check(root,now,exchange)
        if snapshot.get('schema_version') != 3:
            raise ValueError('current_observation_schema_required')
        result['healthy'] = True
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        result['alerts'].append({'code':'engine_data_or_persistence_failure','severity':'critical',
                                 'error_type':type(error).__name__})
    snapshot = result['snapshot'] or {}
    if result['process']['status'] != 'running':
        result['healthy'] = False
        result['alerts'].append({'code':'process_not_verified_running','severity':'critical'})
    if result['process'].get('docker_health') == 'unhealthy':
        result['healthy'] = False
        result['alerts'].append({'code':'docker_health_failure','severity':'critical'})
    risk = snapshot.get('risk',{})
    if risk.get('halted'):
        result['alerts'].append({'code':'drawdown_halt','severity':'critical'})
    elif risk.get('warning'):
        result['alerts'].append({'code':'drawdown_warning','severity':'warning'})
    failure = snapshot.get('loop_failure')
    if failure:
        result['alerts'].append({'code':'operator_loop_failure','severity':'critical',**failure})
    try:
        result['portfolio'] = portfolio(root,exchange,snapshot,now)
        with closing(readonly(root/'user_data'/profile.state_folder/'telemetry.sqlite')) as db:
            cursor = (db.execute('SELECT id,utc,body FROM events ORDER BY id DESC LIMIT 100')
                      if telemetry_after is None else
                      db.execute('SELECT id,utc,body FROM events WHERE id>? ORDER BY id',(telemetry_after,)))
            result['telemetry'] = [{'id':i,'utc':stamp,**json.loads(body)}
                                   for i,stamp,body in cursor]
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        result['healthy'] = False
        result['alerts'].append({'code':'portfolio_or_telemetry_unavailable','severity':'critical',
                                 'error_type':type(error).__name__})
    result['entries_blocked'] = not result['healthy'] or bool(risk.get('halted'))
    result['api_health'] = 'recent_public_quotes' if result['healthy'] else 'not_verified'
    return result


def manifest(exchange):
    verify_baseline(); require_locked_holdout()
    profile = profile_for(exchange)
    files = ('docs/prospective-protocol.md', 'scripts/paper_monitor.py', 'scripts/paper_health.py',
             'scripts/paper_telemetry.py','scripts/paper_risk.py','scripts/paper_status.py',
             'user_data/strategies/MultiAssetPaperStrategy.py', 'user_data/strategies/OkxPaperStrategy.py',
             'user_data/'+profile.config_file, profile.compose_file)
    return {'exchange':exchange,'interval_seconds':INTERVAL,'maximum_bracket_seconds':MAX_INTERVAL,
            'duration_seconds':7*86400,'holdout_prices_inspected':False,
            'file_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}


class Journal:
    def __init__(self, path, protocol, now):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=2)) as db,db:
            db.executescript('''CREATE TABLE IF NOT EXISTS metadata(id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, utc TEXT NOT NULL, body TEXT NOT NULL,
                    previous TEXT NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS alerts(code TEXT PRIMARY KEY, active INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS alert_events(id INTEGER PRIMARY KEY, utc TEXT NOT NULL, code TEXT NOT NULL,
                    transition TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS telemetry_events(id INTEGER PRIMARY KEY, utc TEXT NOT NULL, body TEXT NOT NULL);''')
            row = db.execute('SELECT body FROM metadata WHERE id=1').fetchone()
            if row:
                self.meta=json.loads(row[0])
                # Documentation-only commits may advance HEAD; frozen content must match.
                original={k:v for k,v in self.meta['protocol'].items() if k!='source_commit'}
                current={k:v for k,v in protocol.items() if k!='source_commit'}
                if original != current:raise ValueError('frozen_observation_protocol_changed')
            else:
                if now.tzinfo is None or now.utcoffset()!=timedelta(0):raise ValueError('non_UTC_window')
                self.meta={'start_utc':now.isoformat(),'target_end_utc':(now+timedelta(days=7)).isoformat(),
                           'protocol':protocol,'protocol_sha256':digest(protocol)}
                db.execute('INSERT INTO metadata VALUES(1,?)',(encoded(self.meta),))
        self.path.chmod(0o600)
        self.verify()

    def verify(self):
        previous=digest(self.meta)
        with closing(readonly(self.path)) as db:
            for identifier,stamp,body,parent,hash_ in db.execute('SELECT * FROM samples ORDER BY id'):
                if parent!=previous or hash_!=digest({'utc':stamp,'body':json.loads(body),'previous':parent}):
                    raise ValueError('observation_chain_integrity_failure')
                previous=hash_

    def append(self, result):
        stamp=result['checked_at']; utc(stamp)
        changes=[]
        with closing(sqlite3.connect(self.path,timeout=2)) as db,db:
            last=db.execute('SELECT utc,body,sha256 FROM samples ORDER BY id DESC LIMIT 1').fetchone()
            parent=last[2] if last else digest(self.meta)
            if last:
                elapsed=(utc(stamp)-utc(last[0])).total_seconds()
                if elapsed<=0:raise ValueError('non_monotonic_observation')
                previous=json.loads(last[1])
                if elapsed>MAX_INTERVAL:
                    result['alerts'].append({'code':'monitor_gap','severity':'critical','seconds':elapsed})
                if result['process'].get('started_at')!=previous['process'].get('started_at'):
                    result['alerts'].append({'code':'engine_restart_observed','severity':'warning'})
                old=(previous.get('snapshot') or {}).get('observed_at')
                new=(result.get('snapshot') or {}).get('observed_at')
                if old and new and utc(new)<=utc(old):
                    result['healthy']=False
                    result['entries_blocked']=True
                    result['alerts'].append({'code':'engine_heartbeat_not_advancing','severity':'critical'})
                for pair,current_pair in (result.get('snapshot') or {}).get('pairs',{}).items():
                    previous_pair=(previous.get('snapshot') or {}).get('pairs',{}).get(pair,{})
                    before,after=previous_pair.get('last_closed_utc'),current_pair.get('last_closed_utc')
                    if before and after and (utc(after)-utc(before)).total_seconds()>3600:
                        result['alerts'].append({'code':'candles_not_observed_between_samples','severity':'warning','pair':pair})
            codes={a['code'] for a in result['alerts']}
            old_active={code for code, in db.execute('SELECT code FROM alerts WHERE active=1')}
            for code in sorted(codes-old_active):changes.append((code,'raised'))
            for code in sorted(old_active-codes):changes.append((code,'recovered'))
            for code,transition in changes:
                db.execute('INSERT OR REPLACE INTO alerts VALUES(?,?)',(code,int(transition=='raised')))
                db.execute('INSERT INTO alert_events(utc,code,transition) VALUES(?,?,?)',(stamp,code,transition))
            for event in result['telemetry']:
                if utc(event['utc'])>=utc(self.meta['start_utc']):
                    db.execute('INSERT OR IGNORE INTO telemetry_events VALUES(?,?,?)',
                               (event['id'],event['utc'],encoded(event)))
            db.execute('INSERT INTO samples(utc,body,previous,sha256) VALUES(?,?,?,?)',
                       (stamp,encoded(result),parent,digest({'utc':stamp,'body':result,'previous':parent})))
        return [{'utc':stamp,'code':code,'transition':transition} for code,transition in changes]

    def telemetry_cursor(self):
        with closing(readonly(self.path)) as db:
            return db.execute('SELECT COALESCE(MAX(id),0) FROM telemetry_events').fetchone()[0]

    def report(self, now):
        self.verify()
        with closing(readonly(self.path)) as db:
            rows=[json.loads(body) for body, in db.execute('SELECT body FROM samples ORDER BY id')]
            transitions=[{'utc':a,'code':b,'transition':c} for a,b,c in db.execute('SELECT utc,code,transition FROM alert_events ORDER BY id')]
            attempts=db.execute('SELECT COUNT(*) FROM telemetry_events').fetchone()[0]
        start=utc(self.meta['start_utc']);end=utc(self.meta['target_end_utc'])
        window_rows=[r for r in rows if start<=utc(r['checked_at'])<end]
        bracket=healthy=0.0;gaps=0
        for previous,current in zip(rows,rows[1:]):
            elapsed=(utc(current['checked_at'])-utc(previous['checked_at'])).total_seconds()
            credited=max(0,(min(utc(current['checked_at']),end,now)-max(utc(previous['checked_at']),start)).total_seconds())
            if not credited:continue
            same_process=current['process'].get('started_at')==previous['process'].get('started_at')
            if elapsed<=MAX_INTERVAL and same_process:
                bracket+=credited
                if previous['healthy'] and current['healthy']:healthy+=credited
            else:gaps+=1
        wall_elapsed=max(0,(now-start).total_seconds())
        elapsed=min(wall_elapsed,7*86400)
        boundary_fresh=bool(rows) and min(abs((utc(r['checked_at'])-end).total_seconds()) for r in rows)<=MAX_INTERVAL
        evaluation_rows=window_rows
        candles={};new_orders=[];pnl_delta=None
        if evaluation_rows:
            initial=(evaluation_rows[0].get('portfolio') or {})
            latest=(evaluation_rows[-1].get('portfolio') or {})
            initial_orders={o['order_id'] for o in initial.get('orders',[])}
            new_orders=[o for o in latest.get('orders',[]) if o['order_id'] not in initial_orders]
            initial_pnl,latest_pnl=initial.get('realized_pnl_usdt'),latest.get('realized_pnl_usdt')
            if initial_pnl is not None and latest_pnl is not None:pnl_delta=latest_pnl-initial_pnl
            for pair,initial_pair in (evaluation_rows[0].get('snapshot') or {}).get('pairs',{}).items():
                origin=initial_pair.get('last_closed_utc')
                observed={r['snapshot']['pairs'][pair].get('last_closed_utc') for r in evaluation_rows
                          if r.get('snapshot') and pair in r['snapshot'].get('pairs',{})}
                candles[pair]=sorted(value for value in observed if value and origin and utc(value)>utc(origin))
        return {'window':self.meta,'checked_at':now.isoformat(),'samples':len(window_rows),'total_journal_samples':len(rows),
                'elapsed_seconds':elapsed,'wall_elapsed_seconds':wall_elapsed,
                'sampled_bracket_seconds':bracket,'healthy_bracket_seconds':healthy,
                'sample_coverage_fraction':bracket/elapsed if elapsed else 0,
                'healthy_sample_fraction':sum(r['healthy'] for r in window_rows)/len(window_rows) if window_rows else None,
                'interval_gaps_or_restarts':gaps,'seven_days_elapsed':elapsed>=7*86400,
                'seven_day_observation_qualified':elapsed>=7*86400 and bracket/elapsed>=.99 and healthy/elapsed>=.99
                    and boundary_fresh and bool(window_rows) and window_rows[-1]['healthy'] and not window_rows[-1]['entries_blocked'],
                'alert_transitions':transitions,'recorded_telemetry_events':attempts,
                'latest':window_rows[-1] if window_rows else None,'latest_live_sample':rows[-1] if rows else None,
                'new_closed_candles_seen':candles,'orders_added_since_first_sample':new_orders,
                'realized_pnl_change_since_first_sample_usdt':pnl_delta,
                'pnl_boundary_note':'all native positions preserved; change may include exits of pre-window positions; not independent profitability validation',
                'limitation':'sampled brackets, not proof of continuous uptime; no profitability inference'}


def observer_health(path, now):
    with closing(readonly(path)) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('journal_corrupt')
        row=db.execute('SELECT utc,body,previous,sha256 FROM samples ORDER BY id DESC LIMIT 1').fetchone()
        if not row or not 0<=(now-utc(row[0])).total_seconds()<=MAX_INTERVAL:
            raise ValueError('observer_stale_or_missing')
        if row[3]!=digest({'utc':row[0],'body':json.loads(row[1]),'previous':row[2]}):
            raise ValueError('journal_last_record_corrupt')
        latest=json.loads(row[1])
        if not latest['healthy'] or latest['entries_blocked']:raise ValueError('operator_unhealthy_or_halted')
    return {'status':'healthy','last_sample_utc':row[0]}


def export_journal(path, target):
    target=Path(target)
    if target.exists():raise ValueError('export_target_already_exists')
    target.parent.mkdir(parents=True,exist_ok=True)
    with closing(readonly(path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
        if copy.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('export_integrity_failure')
    target.chmod(0o600)
    with closing(readonly(target)) as db:
        protocol=json.loads(db.execute('SELECT body FROM metadata WHERE id=1').fetchone()[0])['protocol']
    Journal(target,protocol,datetime.now(timezone.utc)).verify()
    return {'file':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'method':'SQLite online backup; chain verified; no writes to source'}


def summary(result):
    portfolio_=result.get('portfolio') or {}
    snapshot=result.get('snapshot') or {}
    lines=[f"{result['exchange']} | UTC {result['checked_at']} | healthy={result['healthy']} | API={result['api_health']}",
           f"Processo: {result['process']} | risco: {snapshot.get('risk')} | falha: {snapshot.get('loop_failure')}",
           f"Saldo/equity: {portfolio_.get('wallet')} | P&L realizado={portfolio_.get('realized_pnl_usdt')} / não realizado={portfolio_.get('unrealized_pnl_usdt')} USDT | taxas={portfolio_.get('fees_usdt')}"]
    for pair,data in snapshot.get('pairs',{}).items():
        book=data.get('public_book',{})
        lines.append(f"{pair}: candle={data.get('last_closed_utc')}, bid/ask={book.get('bid')}/{book.get('ask')} (UTC {book.get('observed_at')}), sinal={data.get('latest_enter_long')}/{data.get('latest_exit_long')}, decisão={data.get('decision')}, motivo={data.get('non_entry_reason')}")
    lines.extend([f"Posições: {portfolio_.get('positions')} | ordens fictícias: {portfolio_.get('orders')}",f"Alertas locais: {result['alerts']}"])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['snapshot','watch','report','health','export'])
    parser.add_argument('--exchange',choices=['okx','kraken'],default='okx')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    folder=ROOT/'user_data/observation'/args.exchange
    path=folder/'journal.sqlite'
    try:
        now=datetime.now(timezone.utc)
        if args.command=='health':
            print(encoded(observer_health(path,now)));return 0
        if args.command=='snapshot':
            result=collect(exchange=args.exchange,now=now)
            print(json.dumps(result,indent=2) if args.json else summary(result))
            return 0 if result['healthy'] and not result['entries_blocked'] else 2
        if args.command=='export':
            destination=ROOT/'user_data/research/observation-exports'/args.exchange/now.strftime('%Y%m%dT%H%M%S%fZ')/'journal.sqlite'
            print(json.dumps(export_journal(path,destination),indent=2));return 0
        protocol=manifest(args.exchange)
        if args.command=='report':
            if not path.is_file():raise ValueError('prospective_window_not_started')
            print(json.dumps(Journal(path,protocol,now).report(now),indent=2));return 0
        folder.mkdir(parents=True,exist_ok=True)
        with open(folder/'observer.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            journal=Journal(path,protocol,now)
            while True:
                started=time.monotonic()
                # Recheck frozen content while watching, not only after a restart.
                if {k:v for k,v in manifest(args.exchange).items() if k!='source_commit'} != {k:v for k,v in protocol.items() if k!='source_commit'}:
                    raise ValueError('frozen_observation_protocol_changed')
                result=collect(exchange=args.exchange,telemetry_after=journal.telemetry_cursor())
                alerts=journal.append(result)
                print(encoded({'utc':result['checked_at'],'healthy':result['healthy'],'alerts':alerts}),flush=True)
                for alert in alerts:print(encoded(alert),file=sys.stderr,flush=True)
                time.sleep(max(0,INTERVAL-(time.monotonic()-started)))
    except KeyboardInterrupt:
        return 0  # Resume keeps metadata/start/alerts; interruption appears as a gap.
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,subprocess.SubprocessError) as error:
        print(encoded({'severity':'critical','code':'observer_failure','error_type':type(error).__name__}),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
