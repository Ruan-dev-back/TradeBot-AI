"""Synthetic stopped databases; never backs up or replaces the live operator."""
from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from backup_paper import backup
from paper_profiles import profile_for
from paper_risk import RiskState


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.profile=profile_for('okx')
        self.folder=self.root/'user_data'/self.profile.state_folder
        self.folder.mkdir(parents=True)
        self.state=RiskState(self.folder/'risk.sqlite')
        with closing(sqlite3.connect(self.root/'user_data'/self.profile.database)) as db,db:
            db.execute('CREATE TABLE trades(id INTEGER PRIMARY KEY, is_open BOOLEAN)')
            db.execute('INSERT INTO trades VALUES(1,1)')

    def test_snapshot_hashes_and_restored_state_and_position_are_preserved(self):
        out=backup('okx',self.root)
        manifest=json.loads((out/'manifest.json').read_text())
        for name,digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
        with closing(sqlite3.connect(out/'native.sqlite')) as db:
            self.assertEqual(db.execute('SELECT id,is_open FROM trades').fetchall(),[(1,1)])
        self.assertEqual(RiskState(out/'risk.sqlite').data,self.state.data)

    def test_active_engine_lock_refuses_snapshot(self):
        with open(self.folder/'engine.lock','w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):backup('okx',self.root)
        self.assertFalse((self.root/'user_data/research/backups').exists())
