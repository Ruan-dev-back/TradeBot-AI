"""Operational fixtures in temporary directories; never touch active trading databases."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'user_data/strategies'))
from paper_monitor import Journal, collect, digest, export_journal, observer_health, portfolio, summary
from paper_risk import RiskState
from paper_telemetry import Telemetry
from MultiAssetPaperStrategy import MultiAssetPaperStrategy
from freqtrade.persistence import Trade


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'user_data/paper-okx'
        self.folder.mkdir(parents=True)
        self.now=datetime(2026,10,12,16,15,tzinfo=timezone.utc)
        self.state=RiskState(self.folder/'risk.sqlite');self.state.observe(1000,self.now)
        self.telemetry=Telemetry(self.folder/'telemetry.sqlite')
        self.body={'schema_version':3,'observed_at':self.now.isoformat(),'exchange':'okx','dry_run':True,
            'risk_ready':True,'risk':deepcopy(self.state.data),'loop_failure':None,
            'wallet':{'observed_at':self.now.isoformat(),'equity_usdt':1000.,'free_usdt':1000.},
            'pairs':{pair:{'status':'ok','checked_candles':200,'first_utc':'2026-10-04T08:00:00+00:00',
                'last_closed_utc':'2026-10-12T15:00:00+00:00','timeframe':'1h','latest_enter_long':0,'latest_exit_long':0,
                'non_entry_reason':'no_entry_signal','decision':'no_trade',
                'public_book':{'status':'ok','observed_at':self.now.isoformat(),'bid':105.,'ask':105.01}}
                     for pair in ('BTC/USDT','ETH/USDT','SOL/USDT')}}
        self.path=self.root/'user_data/tradesv3.paper-okx.sqlite'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('''CREATE TABLE trades(id INTEGER PRIMARY KEY,exchange TEXT,pair TEXT,is_short INTEGER,
                leverage FLOAT,is_open INTEGER,amount FLOAT,open_trade_value FLOAT,stake_amount FLOAT,open_rate FLOAT,
                open_date TEXT,fee_open FLOAT,fee_close FLOAT,close_profit_abs FLOAT,realized_profit FLOAT)''')
            db.execute('''CREATE TABLE orders(id INTEGER PRIMARY KEY,order_id TEXT,ft_trade_id INTEGER,ft_pair TEXT,
                side TEXT,status TEXT,filled FLOAT,remaining FLOAT,average FLOAT,price FLOAT,order_date TEXT)''')
        self.process={'status':'running','started_at':'2026-10-12T16:00:00Z','container_id':'fixture'}
        self.protocol={'exchange':'okx','source_commit':'fixture','file_hashes':{'fixture':'frozen'}}
        self.save()

    def save(self):
        (self.folder/'status.json').write_text(json.dumps(self.body))

    def sample(self,now=None):
        return collect(self.root,'okx',now or self.now,self.process)

    def advance(self,seconds):
        self.now+=timedelta(seconds=seconds)
        self.state.observe(1000,self.now)
        self.body['observed_at']=self.now.isoformat();self.body['risk']=deepcopy(self.state.data)
        self.body['wallet']['observed_at']=self.now.isoformat()
        for pair in self.body['pairs'].values():pair['public_book']['observed_at']=self.now.isoformat()
        self.save()

    def journal(self):return Journal(self.root/'journal.sqlite',self.protocol,self.now)

    def test_snapshot_zero_operations_is_readonly_and_reason_is_visible(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        result=self.sample()
        self.assertTrue(result['healthy']);self.assertEqual(result['portfolio']['native_trades'],0)
        self.assertEqual(result['portfolio']['fees_usdt'],0)
        self.assertIn('no_entry_signal',summary(result))
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_native_profit_api_and_open_position_mark_are_fee_adjusted(self):
        trade=Trade(pair='BTC/USDT',exchange='okx',amount=.25,stake_amount=25,open_rate=100,
                    fee_open=.004,fee_close=.004,is_open=True,open_date=self.now,leverage=1,
                    is_short=False,open_trade_value=25.1)
        engine=SimpleNamespace(wallets=Mock(),dp=Mock())
        engine.wallets.get_free.return_value=975
        engine.dp.orderbook.return_value={'bids':[[105.,10]],'asks':[[105.01,10]]}
        with patch('MultiAssetPaperStrategy.Trade.get_trades_proxy',return_value=[trade]):
            equity,free=MultiAssetPaperStrategy._equity(engine)
        self.assertAlmostEqual(equity,1000+trade.calculate_profit(105).profit_abs)
        self.assertEqual(free,975)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("INSERT INTO trades VALUES(1,'okx','BTC/USDT',0,1,1,.25,25.1,25,100,?,.004,.004,NULL,0)",(self.now.isoformat(),))
            db.execute("INSERT INTO orders VALUES(1,'dry_run_buy_fixture',1,'BTC/USDT','buy','closed',.25,0,100,100,?)",(self.now.isoformat(),))
        values=portfolio(self.root,'okx',self.body,self.now)
        self.assertAlmostEqual(values['unrealized_pnl_usdt'],trade.calculate_profit(105).profit_abs)
        self.assertAlmostEqual(values['fees_usdt'],.1)
        self.body['pairs']['BTC/USDT']['public_book']['observed_at']=(self.now-timedelta(seconds=31)).isoformat()
        self.assertIsNone(portfolio(self.root,'okx',self.body,self.now)['unrealized_pnl_usdt'])

    def test_stale_candle_quote_wallet_and_invalid_quote_fail_even_with_running_process(self):
        original=deepcopy(self.body)
        mutations=[lambda: self.body['pairs']['BTC/USDT'].update(last_closed_utc='2026-10-12T12:00:00+00:00'),
                   lambda: self.body['pairs']['BTC/USDT']['public_book'].update(bid=106.),
                   lambda: self.body['pairs']['BTC/USDT']['public_book'].update(observed_at=(self.now-timedelta(seconds=31)).isoformat()),
                   lambda: self.body['wallet'].update(observed_at=(self.now-timedelta(seconds=31)).isoformat())]
        for mutate in mutations:
            self.body=deepcopy(original);mutate();self.save()
            self.assertFalse(self.sample()['healthy'])

    def test_disconnect_recovery_and_halt_are_distinct_durable_alerts(self):
        journal=self.journal();journal.append(self.sample())
        self.advance(30)
        self.body['risk_ready']=False;self.body['loop_failure']={'stage':'public_quotes','type':'NetworkError'};self.save()
        changes=journal.append(self.sample())
        self.assertIn('operator_loop_failure',{c['code'] for c in changes})
        self.advance(30);self.body['risk_ready']=True;self.body['loop_failure']=None;self.save()
        changes=journal.append(self.sample())
        self.assertIn({'utc':self.now.isoformat(),'code':'operator_loop_failure','transition':'recovered'},changes)
        self.state.observe(930,self.now);self.body['risk']=deepcopy(self.state.data);self.save()
        halted=self.sample()
        self.assertTrue(halted['healthy']);self.assertTrue(halted['entries_blocked'])
        self.assertIn('drawdown_halt',{a['code'] for a in halted['alerts']})

    def test_missing_or_corrupt_persistence_is_not_zero_profit(self):
        self.path.write_bytes(b'not sqlite')
        result=self.sample();self.assertFalse(result['healthy'])
        self.assertIsNone(result['portfolio'])
        self.assertIn('portfolio_or_telemetry_unavailable',{a['code'] for a in result['alerts']})

    def test_restart_keeps_window_alert_dedup_and_detects_unobserved_interval(self):
        journal=self.journal();journal.append(self.sample())
        start=journal.meta['start_utc']
        self.advance(30);journal.append(self.sample())
        restarted=self.journal();self.assertEqual(restarted.meta['start_utc'],start)
        self.advance(90);self.process['started_at']='2026-10-12T16:16:00Z'
        changes=restarted.append(self.sample())
        self.assertIn('monitor_gap',{c['code'] for c in changes})
        report=restarted.report(self.now)
        self.assertEqual(report['sampled_bracket_seconds'],30)
        self.assertFalse(report['seven_days_elapsed']);self.assertFalse(report['seven_day_observation_qualified'])
        self.advance(30);changes=restarted.append(self.sample())
        self.assertIn('monitor_gap',{c['code'] for c in changes if c['transition']=='recovered'})

    def test_observer_health_detects_hang_and_tampering(self):
        journal=self.journal();journal.append(self.sample())
        self.assertEqual(observer_health(journal.path,self.now)['status'],'healthy')
        with self.assertRaises(ValueError):observer_health(journal.path,self.now+timedelta(seconds=46))
        with closing(sqlite3.connect(journal.path)) as db,db:db.execute("UPDATE samples SET body='{}' WHERE id=1")
        with self.assertRaises(ValueError):journal.verify()

    def test_same_heartbeat_has_no_false_availability(self):
        journal=self.journal();journal.append(self.sample())
        sample=self.sample(self.now+timedelta(seconds=10))
        journal.append(sample)
        self.assertFalse(sample['healthy'])
        self.assertIn('engine_heartbeat_not_advancing',{a['code'] for a in sample['alerts']})

    def test_freeze_blocks_parameter_changes_and_documentation_only_head_is_allowed(self):
        self.journal()
        changed=deepcopy(self.protocol);changed['file_hashes']['fixture']='optimized'
        with self.assertRaises(ValueError):Journal(self.root/'journal.sqlite',changed,self.now)
        changed=deepcopy(self.protocol);changed['source_commit']='documentation-only'
        self.assertEqual(Journal(self.root/'journal.sqlite',changed,self.now).meta['protocol']['source_commit'],'fixture')

    def test_telemetry_dedup_excludes_pre_window_signals_and_never_creates_orders(self):
        self.telemetry.record(self.now-timedelta(seconds=1),'entry_attempt',outcome='rejected',reason='old')
        self.telemetry.record(self.now,'entry_attempt',outcome='rejected',reason='budget_or_minimum')
        journal=self.journal();journal.append(self.sample())
        self.advance(30);journal.append(self.sample())
        report=journal.report(self.now)
        self.assertEqual(report['recorded_telemetry_events'],1)
        self.assertEqual(report['latest']['portfolio']['native_orders'],0)
        self.assertEqual(report['orders_added_since_first_sample'],[])

    def test_seven_days_wall_clock_without_samples_is_not_qualified(self):
        journal=self.journal();journal.append(self.sample())
        report=journal.report(self.now+timedelta(days=7))
        self.assertTrue(report['seven_days_elapsed']);self.assertFalse(report['seven_day_observation_qualified'])

    def test_journal_storage_failure_does_not_claim_sample_was_saved(self):
        journal=self.journal()
        with patch('paper_monitor.sqlite3.connect',side_effect=sqlite3.OperationalError('fixture disk full')):
            with self.assertRaises(sqlite3.OperationalError):journal.append(self.sample())
        self.assertEqual(journal.report(self.now)['samples'],0)

    def test_online_journal_export_restores_chain_and_does_not_modify_source(self):
        journal=self.journal();journal.append(self.sample())
        before=hashlib.sha256(journal.path.read_bytes()).hexdigest()
        target=self.root/'exports/journal.sqlite'
        exported=export_journal(journal.path,target)
        self.assertEqual(hashlib.sha256(journal.path.read_bytes()).hexdigest(),before)
        self.assertEqual(exported['sha256'],hashlib.sha256(target.read_bytes()).hexdigest())
        restored=Journal(target,self.protocol,self.now)
        self.assertEqual(restored.report(self.now)['samples'],1)
        with self.assertRaises(ValueError):export_journal(journal.path,target)

    def test_samples_after_fixed_end_do_not_repair_failed_first_week(self):
        journal=self.journal();journal.append(self.sample())
        self.advance(7*86400+30)
        for _ in range(3):
            latest=self.sample();journal.append(latest);self.advance(30)
        report=journal.report(self.now)
        self.assertEqual(report['samples'],1)
        self.assertEqual(report['total_journal_samples'],4)
        self.assertEqual(report['elapsed_seconds'],7*86400)
        self.assertEqual(report['sampled_bracket_seconds'],0)
        self.assertFalse(report['seven_day_observation_qualified'])
