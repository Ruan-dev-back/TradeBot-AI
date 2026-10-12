"""Functional status must fail for stale/invalid data, even with a running PID."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import closing
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from paper_status import check


class PaperStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 10, 11, tzinfo=timezone.utc)
        self.folder = self.root / 'user_data/paper'
        self.folder.mkdir(parents=True)
        self.body = {'observed_at': self.now.isoformat(), 'dry_run': True, 'exchange': 'kraken',
                     'risk_ready': True, 'pairs': {pair: {'status': 'ok', 'checked_candles': 200}
                       for pair in ('BTC/USDT', 'ETH/USDT', 'SOL/USDT')}}
        with closing(sqlite3.connect(self.root / 'user_data/tradesv3.paper.sqlite')) as db, db:
            db.execute('CREATE TABLE trades (id INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY)')

    def save(self):
        (self.folder / 'status.json').write_text(json.dumps(self.body))

    def test_ready_snapshot_has_real_database_counts_without_invented_trades(self):
        self.save()
        status = check(self.root, self.now)
        self.assertEqual(status['native_trades'], 0)
        self.assertEqual(status['native_orders'], 0)

    def test_stale_future_snapshot_invalid_market_and_real_mode_fail(self):
        self.save()
        for now in (self.now + timedelta(seconds=31), self.now - timedelta(seconds=1)):
            with self.assertRaises(ValueError): check(self.root, now)
        for key, value in (('dry_run', False), ('risk_ready', False)):
            original = self.body[key]
            self.body[key] = value
            self.save()
            with self.assertRaises(ValueError): check(self.root, self.now)
            self.body[key] = original
        self.body['pairs']['SOL/USDT']['status'] = 'warming_up'
        self.save()
        with self.assertRaises(ValueError): check(self.root, self.now)

    def test_current_schema_requires_fresh_public_quotes(self):
        self.body['schema_version']=2
        for pair in self.body['pairs'].values():
            pair['public_book']={'status':'ok','observed_at':self.now.isoformat()}
        self.save()
        self.assertEqual(check(self.root,self.now)['status'],'running_with_public_data')
        self.body['pairs']['BTC/USDT']['public_book']['observed_at']=(self.now-timedelta(seconds=31)).isoformat()
        self.save()
        with self.assertRaises(ValueError):check(self.root,self.now)
