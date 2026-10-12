"""Append-only operational events, separate from native trades and risk databases."""
from contextlib import closing
from datetime import timedelta
import json
import math
from pathlib import Path
import sqlite3


class Telemetry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS events '
                       '(id INTEGER PRIMARY KEY, utc TEXT NOT NULL, body TEXT NOT NULL)')
        self.path.chmod(0o600)

    def record(self, now, kind, **fields):
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError('Telemetry timestamps must be UTC')
        body = {'kind': kind, **fields}
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute('INSERT INTO events(utc,body) VALUES(?,?)',
                       (now.isoformat(), json.dumps(body, allow_nan=False, sort_keys=True)))


def safe_number(value):
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None
