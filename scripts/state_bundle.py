"""Quiesced four-database snapshots and non-overwriting recovery. No trading calls."""
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

from paper_health import readonly, utc
from paper_monitor import Journal, digest
from paper_profiles import profile_for
from paper_risk import RiskPolicy

ROOT = Path(__file__).resolve().parents[1]


def paths(root, exchange):
    p = profile_for(exchange)
    return {'trades.sqlite': root/'user_data'/p.database,
            'risk.sqlite': root/'user_data'/p.state_folder/'risk.sqlite',
            'telemetry.sqlite': root/'user_data'/p.state_folder/'telemetry.sqlite',
            'observation.sqlite': root/'user_data/observation'/exchange/'journal.sqlite'}


@contextmanager
def writer_locks(root, exchange):
    p = profile_for(exchange)
    with ExitStack() as stack:
        for folder, name in ((root/'user_data'/p.state_folder, 'engine.lock'),
                             (root/'user_data/observation'/exchange, 'observer.lock')):
            folder.mkdir(parents=True, exist_ok=True)
            handle = stack.enter_context(open(folder/name, 'a'))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def window(path, reference_root=ROOT):
    with closing(readonly(path)) as db:
        meta = json.loads(db.execute('SELECT body FROM metadata WHERE id=1').fetchone()[0])
        last = db.execute('SELECT utc FROM samples ORDER BY id DESC LIMIT 1').fetchone()
    if meta['protocol_sha256'] != digest(meta['protocol']):
        raise ValueError('Observation protocol digest mismatch')
    if (utc(meta['target_end_utc'])-utc(meta['start_utc'])).total_seconds() != 7*86400:
        raise ValueError('Observation T0/T1 changed')
    for name, expected in meta['protocol']['file_hashes'].items():
        path_ = reference_root/name
        if Path(name).is_absolute() or '..' in Path(name).parts or path_.is_symlink():
            raise ValueError('Unsafe frozen source path')
        if not path_.is_file() or sha(path_) != expected:
            raise ValueError('Frozen source mismatch; do not create a replacement window')
    journal = Journal.__new__(Journal)  # Verify without CREATE, chmod or writes to the source.
    journal.path = Path(path); journal.meta = meta; journal.verify()
    if not last: raise ValueError('No prospective samples to migrate')
    return {'start_utc':meta['start_utc'], 'target_end_utc':meta['target_end_utc'],
            'protocol_sha256':meta['protocol_sha256'], 'last_sample_utc':last[0],
            'exchange':meta['protocol']['exchange']}


def inspect_state(files, exchange, reference_root=ROOT):
    for path in files.values():
        if path.is_symlink() or not path.is_file(): raise ValueError('All four regular database files are required')
        with closing(readonly(path)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity failure')
    with closing(readonly(files['risk.sqlite'])) as db:
        risk = json.loads(db.execute('SELECT body FROM risk WHERE id=1').fetchone()[0])
    if risk['policy_sha256'] != RiskPolicy().fingerprint:
        raise ValueError('Risk policy mismatch')
    utc(risk['observed_at'])
    with closing(readonly(files['trades.sqlite'])) as db:
        # Validate actual native order identity; never substitute a fixture with live records.
        for identifier, in db.execute('SELECT order_id FROM orders'):
            if not isinstance(identifier, str) or not identifier.startswith('dry_run_'):
                raise ValueError('Non-dry order in native database')
        for venue, leverage, short in db.execute('SELECT exchange,leverage,is_short FROM trades'):
            if venue != exchange or leverage != 1 or short:
                raise ValueError('Unexpected exchange/leverage/side')
        counts = {'trades':db.execute('SELECT COUNT(*) FROM trades').fetchone()[0],
                  'orders':db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
                  'open_positions':db.execute('SELECT COUNT(*) FROM trades WHERE is_open=1').fetchone()[0]}
        closed={row[0] for row in db.execute('SELECT id FROM trades WHERE is_open=0')}
        if not set(risk['closed_ids']).issubset(closed):
            raise ValueError('Risk processed IDs do not reconcile with native closed trades')
    with closing(readonly(files['telemetry.sqlite'])) as db:
        events = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        native_events={row[0] for row in db.execute('SELECT id FROM events')}
    with closing(readonly(files['observation.sqlite'])) as db:
        observed_events={row[0] for row in db.execute('SELECT id FROM telemetry_events')}
    if not observed_events.issubset(native_events):
        raise ValueError('Observation/telemetry IDs do not reconcile')
    result = window(files['observation.sqlite'], reference_root)
    if result['exchange'] != exchange: raise ValueError('Observation exchange mismatch')
    return {'window':result, 'native_counts':counts, 'telemetry_events':events,
            'risk':risk, 'live_health_verified':False}


def create_backup(root, exchange, reference_root=ROOT, include_code=True):
    with writer_locks(root, exchange):
        source = paths(root, exchange)
        inspect_state(source, exchange, reference_root)
        commit = None
        if include_code:
            if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():
                raise ValueError('Commit reviewed source before portable backup')
            branch = subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()
            if branch != 'feat/realtime-paper-trading': raise ValueError('Unexpected source branch')
            commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        parent = root/'user_data/research/state-bundles'/exchange
        parent.mkdir(parents=True,exist_ok=True)
        pending = parent/('pending-'+stamp); pending.mkdir(mode=0o700)
        try:
            files = {}
            for name, source_path in source.items():
                target = pending/name
                with closing(readonly(source_path)) as read, closing(sqlite3.connect(target)) as write:
                    read.backup(write)
                target.chmod(0o600); files[name] = sha(target)
            state = inspect_state({name:pending/name for name in source},exchange,reference_root)
            if include_code:
                subprocess.run(['git','bundle','create',str(pending/'source.bundle'),
                                'refs/heads/feat/realtime-paper-trading'],cwd=root,check=True,capture_output=True)
                files['source.bundle'] = sha(pending/'source.bundle')
            body = {'schema':1,'exchange':exchange,'captured_utc':datetime.now(timezone.utc).isoformat(),
                    'both_writers_quiesced':True,'files':files,'source_commit':commit,'state':state,
                    'no_status_or_runtime_config_restored':True}
            (pending/'manifest.json').write_text(json.dumps(body,indent=2)+'\n')
            complete = parent/('complete-'+stamp); pending.rename(complete)
            return complete
        except Exception:
            # Pending is intentionally retained as incomplete evidence, never selected as backup.
            raise


def verify_bundle(folder, exchange, reference_root=ROOT):
    folder = Path(folder)
    if folder.is_symlink():raise ValueError('Symlink bundle refused')
    body = json.loads((folder/'manifest.json').read_text())
    required = set(paths(reference_root,exchange))
    if (body.get('schema') != 1 or body['exchange'] != exchange
            or body.get('both_writers_quiesced') is not True
            or set(body['files']) not in (required, required|{'source.bundle'})):
        raise ValueError('Invalid or mixed backup set')
    for name, expected in body['files'].items():
        path = folder/name
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError('Backup checksum mismatch')
    actual = inspect_state({name:folder/name for name in required},exchange,reference_root)
    if actual != body['state']:raise ValueError('Backup state/temporal metadata mismatch')
    if 'source.bundle' in body['files']:
        heads = subprocess.check_output(['git','bundle','list-heads',str(folder/'source.bundle')],text=True).splitlines()
        if heads != [body['source_commit']+' refs/heads/feat/realtime-paper-trading']:
            raise ValueError('Code archive commit mismatch')
    return body


def restore_bundle(folder, target_root, exchange, reference_root=ROOT):
    folder, target_root = Path(folder), Path(target_root)
    body = verify_bundle(folder,exchange,reference_root)
    targets = paths(target_root,exchange)
    for path in targets.values():
        if path.exists() or path.is_symlink() or list(path.parent.glob(path.name+'-*')):
            raise ValueError('Recovery never overwrites existing state; use a fresh checkout/staging directory')
    with writer_locks(target_root,exchange):
        created = []
        try:
            for name,target in targets.items():
                target.parent.mkdir(parents=True,exist_ok=True)
                # Exclusive creation: races or unexpected old files fail safely.
                with open(folder/name,'rb') as read, open(target,'xb') as write:
                    created.append(target); shutil.copyfileobj(read,write)
                target.chmod(0o600)
            actual = inspect_state(targets,exchange,reference_root)
            if actual != body['state']:raise ValueError('Restored state differs from snapshot')
            receipt = {'restored_utc':datetime.now(timezone.utc).isoformat(),'exchange':exchange,
                       'backup_manifest_sha256':sha(folder/'manifest.json'),'source_commit':body['source_commit'],
                       'preserved_window':body['state']['window'],'live_health_pending':True,
                       'next_observer_sample_must_record_gap_or_restart':True}
            path = target_root/'user_data/observation'/exchange/'recovery.json'
            path.write_text(json.dumps(receipt,indent=2)+'\n')
            return receipt
        except Exception:
            for path in created: path.unlink(missing_ok=True)  # Only files created by this attempt.
            raise
