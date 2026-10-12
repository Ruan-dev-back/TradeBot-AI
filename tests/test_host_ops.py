"""Portable state and host guards on isolated fixtures, never active databases."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from paper_monitor import Journal, manifest
from paper_risk import RiskState
from paper_telemetry import Telemetry
from paper_host import compose, preflight, start, stop_observer
from render_host_units import render
from state_bundle import create_backup, inspect_state, paths, restore_bundle, sha, verify_bundle


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'source';self.root.mkdir()
        self.now=datetime(2026,10,12,18,tzinfo=timezone.utc)
        self.files=paths(self.root,'okx')
        for path in self.files.values():path.parent.mkdir(parents=True,exist_ok=True)
        state=RiskState(self.files['risk.sqlite']);state.observe(1100,self.now)
        state.observe(1000,self.now,[(1,self.now-timedelta(minutes=1),-1.)])
        self.risk=deepcopy(state.data)
        Telemetry(self.files['telemetry.sqlite']).record(self.now,'entry_attempt',outcome='rejected',reason='fixture')
        with closing(sqlite3.connect(self.files['trades.sqlite'])) as db,db:
            db.execute('CREATE TABLE trades(id INTEGER PRIMARY KEY,exchange TEXT,leverage FLOAT,is_short INTEGER,is_open INTEGER)')
            db.execute("INSERT INTO trades VALUES(1,'okx',1,0,0)")
            db.execute("INSERT INTO trades VALUES(2,'okx',1,0,1)")
            db.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY,order_id TEXT,status TEXT)')
            db.execute("INSERT INTO orders VALUES(1,'dry_run_buy_fixture','open')")
        with patch('paper_monitor.subprocess.check_output',return_value='fixture\n'):
            self.protocol=manifest('okx')
        self.journal=Journal(self.files['observation.sqlite'],self.protocol,self.now)
        self.journal.append({'checked_at':self.now.isoformat(),'healthy':True,'entries_blocked':True,
             'alerts':[],'process':{'started_at':'fixture-host-1'},'snapshot':{'observed_at':self.now.isoformat(),'pairs':{}},
             'portfolio':{'orders':[]},'telemetry':[]})

    def backup(self):return create_backup(self.root,'okx',include_code=False)

    def test_four_database_backup_preserves_risk_orders_positions_and_window(self):
        before={name:sha(path) for name,path in self.files.items()}
        folder=self.backup();body=verify_bundle(folder,'okx')
        self.assertEqual(set(body['files']),set(self.files))
        self.assertEqual(body['state']['risk'],self.risk)
        self.assertTrue(body['state']['risk']['halted'])
        self.assertEqual(body['state']['native_counts']['open_positions'],1)
        self.assertEqual(body['state']['window']['start_utc'],self.now.isoformat())
        self.assertEqual(before,{name:sha(path) for name,path in self.files.items()})

    def test_staged_restore_keeps_all_records_and_T0_T1_without_fresh_status(self):
        folder=self.backup();target=Path(self.temp.name)/'fresh'
        receipt=restore_bundle(folder,target,'okx')
        state=inspect_state(paths(target,'okx'),'okx')
        self.assertEqual(state['risk'],self.risk)
        self.assertEqual(receipt['preserved_window']['target_end_utc'],(self.now+timedelta(days=7)).isoformat())
        self.assertFalse((target/'user_data/paper-okx/status.json').exists())
        self.assertFalse((target/'user_data/paper-okx/runtime.json').exists())
        with closing(sqlite3.connect(paths(target,'okx')['trades.sqlite'])) as db:
            self.assertEqual(db.execute('SELECT status FROM orders').fetchone()[0],'open')

    def test_corruption_and_mixed_exchange_are_refused_before_restore(self):
        folder=self.backup()
        with self.assertRaises(ValueError):verify_bundle(folder,'kraken')
        (folder/'risk.sqlite').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):restore_bundle(folder,Path(self.temp.name)/'target','okx')

    def test_existing_state_is_never_overwritten(self):
        folder=self.backup();before=sha(self.files['trades.sqlite'])
        with self.assertRaises(ValueError):restore_bundle(folder,self.root,'okx')
        self.assertEqual(sha(self.files['trades.sqlite']),before)

    def test_each_writer_lock_prevents_quiesced_snapshot(self):
        for folder,name in ((self.root/'user_data/paper-okx','engine.lock'),
                            (self.root/'user_data/observation/okx','observer.lock')):
            with open(folder/name,'a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):self.backup()

    def test_missing_database_and_unreconciled_closed_ids_are_refused(self):
        with closing(sqlite3.connect(self.files['risk.sqlite'])) as db,db:
            data=deepcopy(self.risk);data['closed_ids']=[99]
            db.execute('UPDATE risk SET body=?',(json.dumps(data),))
        with self.assertRaises(ValueError):self.backup()
        self.files['telemetry.sqlite'].unlink()
        with self.assertRaises(ValueError):inspect_state(self.files,'okx')

    def test_window_and_frozen_content_change_are_not_permission_for_new_window(self):
        folder=self.backup()
        with closing(sqlite3.connect(folder/'observation.sqlite')) as db,db:
            meta=json.loads(db.execute('SELECT body FROM metadata').fetchone()[0])
            meta['target_end_utc']=(self.now+timedelta(days=8)).isoformat()
            db.execute('UPDATE metadata SET body=?',(json.dumps(meta),))
        with self.assertRaises(ValueError):verify_bundle(folder,'okx')

    def test_non_dry_order_is_rejected(self):
        with closing(sqlite3.connect(self.files['trades.sqlite'])) as db,db:
            db.execute("UPDATE orders SET order_id='private-order-fixture'")
        with self.assertRaises(ValueError):self.backup()

    def test_partial_copy_failure_rolls_back_only_new_files(self):
        folder=self.backup();target=Path(self.temp.name)/'target'
        with patch('state_bundle.shutil.copyfileobj',side_effect=OSError('fixture full disk')):
            with self.assertRaises(OSError):restore_bundle(folder,target,'okx')
        self.assertFalse(any(path.exists() for path in paths(target,'okx').values()))
        verify_bundle(folder,'okx')

    def test_symlink_payload_and_manifest_tampering_are_refused(self):
        folder=self.backup();payload=folder/'risk.sqlite'
        payload.unlink();payload.symlink_to(self.files['risk.sqlite'])
        with self.assertRaises(ValueError):verify_bundle(folder,'okx')

    def test_migration_gap_is_detected_on_next_original_observer_sample(self):
        folder=self.backup();target=Path(self.temp.name)/'target'
        restore_bundle(folder,target,'okx')
        journal=Journal(paths(target,'okx')['observation.sqlite'],self.protocol,self.now+timedelta(minutes=10))
        sample={'checked_at':(self.now+timedelta(minutes=10)).isoformat(),'healthy':True,'entries_blocked':False,
             'alerts':[],'process':{'started_at':'fixture-host-2'},'snapshot':{'observed_at':(self.now+timedelta(minutes=10)).isoformat(),'pairs':{}},
             'portfolio':{'orders':[]},'telemetry':[]}
        changes=journal.append(sample)
        self.assertIn('monitor_gap',{c['code'] for c in changes})
        self.assertIn('engine_restart_observed',{c['code'] for c in changes})
        self.assertEqual(journal.meta['start_utc'],self.now.isoformat())
        self.assertEqual(journal.report(self.now+timedelta(minutes=10))['sampled_bracket_seconds'],0)


class HostGuardTests(unittest.TestCase):
    def test_compose_profiles_are_explicit_no_order_overrides(self):
        command=compose(ROOT,'okx',True)
        self.assertIn(str(ROOT/'docker-compose.okx.cloud.yml'),command)
        self.assertNotIn('--remove-orphans',command)
        with self.assertRaises(ValueError):compose(ROOT,'arbitrary')

    def test_uid_mismatch_is_actionable_and_never_changes_permissions(self):
        def fake(command,*args,**kwargs):
            if command[:2]==['docker','info']:return 'x86_64' if command[-1]=='{{.Architecture}}' else 'linux'
            if command[:3]==['docker','compose','version']:return '2.40.0'
            if command[:2]==['docker','run']:return '{"uid":1000,"gid":1000}'
            return ''
        with patch('paper_host.static_checks'),patch('paper_host.image_for',return_value='pinned'), \
             patch('paper_host.execute',side_effect=fake),patch('paper_host.os.getuid',return_value=2000):
            with self.assertRaisesRegex(ValueError,'UID must match'):preflight(public=False)

    def test_start_refuses_missing_window_before_network_or_container_actions(self):
        with patch('paper_host.recovery',side_effect=ValueError('missing window')),patch('paper_host.preflight') as request:
            with self.assertRaises(ValueError):start()
            request.assert_not_called()

    def test_unmanaged_observer_is_never_killed(self):
        with tempfile.TemporaryDirectory() as name:
            with patch('paper_host.observer_locked',return_value=True),patch('paper_host.os.kill') as kill:
                with self.assertRaises(ValueError):stop_observer(Path(name),'okx')
                kill.assert_not_called()

    def test_unsupported_architecture_and_old_compose_fail_before_start(self):
        for architecture,version in (('aarch64','2.40.0'),('x86_64','2.10.0')):
            def fake(command,*args,**kwargs):
                if command[:2]==['docker','info']:return architecture if command[-1]=='{{.Architecture}}' else 'linux'
                if command[:3]==['docker','compose','version']:return version
                return ''
            with patch('paper_host.static_checks'),patch('paper_host.execute',side_effect=fake):
                with self.assertRaises(ValueError):preflight(public=False)

    def test_recycled_pid_is_not_signalled(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);folder=root/'user_data/host-ops/okx';folder.mkdir(parents=True)
            (folder/'observer.json').write_text('{"pid":123,"start_ticks":"old"}')
            with patch('paper_host.observer_locked',return_value=True),patch('paper_host.process_identity',return_value='new'), \
                 patch('paper_host.Path.read_bytes',return_value=b'python\0'+str(root/'scripts/paper_monitor.py').encode()+b'\0okx\0'), \
                 patch('paper_host.os.kill') as kill:
                with self.assertRaises(ValueError):stop_observer(root,'okx')
                kill.assert_not_called()

    def test_rendered_units_require_recovery_and_non_root_account(self):
        with tempfile.TemporaryDirectory() as name:
            out=render(Path(name)/'units','/opt/tradebot-ai','operator','operator')
            observer=(out/'tradebot-paper-observer.service').read_text()
            bot=(out/'tradebot-okx-paper.service').read_text()
            self.assertIn('User=operator',observer)
            self.assertIn('After=docker.service tradebot-okx-paper.service',observer)
            self.assertIn('verify-recovery',bot)
            self.assertIn('paper_host.py run-observer',observer)
            with self.assertRaises(ValueError):render(out,'/opt/tradebot-ai','operator','operator')

    def test_external_desktop_units_do_not_require_absent_docker_service(self):
        with tempfile.TemporaryDirectory() as name:
            out=render(Path(name)/'units','/home/operator/TradeBot-AI','operator','operator',True,docker_binary='/usr/bin/docker')
            bot=(out/'tradebot-okx-paper.service').read_text()
            self.assertNotIn('docker.service',bot)
            self.assertIn('ExecStartPre=/usr/bin/docker info',bot)
            self.assertNotIn('SupplementaryGroups=docker',bot)

    def test_unit_specifier_path_and_account_injection_are_refused(self):
        with tempfile.TemporaryDirectory() as name:
            for path,user in (('/opt/space path','operator'),('/opt/%n','operator'),('/opt/safe','root\nExecStart=bad')):
                with self.assertRaises(ValueError):render(Path(name)/'units',path,user,'operator')
