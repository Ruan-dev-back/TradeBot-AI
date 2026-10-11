"""Read-only functional status check; no control API, orders or private connections."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    snapshot = json.loads((root / 'user_data/paper/status.json').read_text())
    if snapshot.get('dry_run') is not True or snapshot.get('exchange') != 'kraken':
        raise ValueError('Invalid paper identity')
    age = (now - datetime.fromisoformat(snapshot['observed_at'])).total_seconds()
    if not 0 <= age <= 30 or snapshot.get('risk_ready') is not True:
        raise ValueError('Paper risk loop not ready or stale')
    if set(snapshot['pairs']) != {'BTC/USDT', 'ETH/USDT', 'SOL/USDT'}:
        raise ValueError('Unexpected market universe')
    if any(p['status'] != 'ok' or p['checked_candles'] < 200 for p in snapshot['pairs'].values()):
        raise ValueError('Paper candles not ready')
    db_path = root / 'user_data/tradesv3.paper.sqlite'
    with closing(sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        snapshot['native_trades'] = db.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
        snapshot['native_orders'] = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    snapshot['checked_at'] = now.isoformat()
    snapshot['status'] = 'running_with_public_data'
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        report = check()
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f'Paper status failed: {error}')
        return 2
    body = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body)
    print(body)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
