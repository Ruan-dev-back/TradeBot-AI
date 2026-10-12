"""Read-only functional status check; no control API, orders or private connections."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from paper_profiles import profile_for

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT, now=None, exchange='kraken'):
    now = now or datetime.now(timezone.utc)
    profile = profile_for(exchange)
    snapshot = json.loads((root / 'user_data' / profile.state_folder / 'status.json').read_text())
    if snapshot.get('dry_run') is not True or snapshot.get('exchange') != exchange:
        raise ValueError('Invalid paper identity')
    age = (now - datetime.fromisoformat(snapshot['observed_at'])).total_seconds()
    if not 0 <= age <= 30 or snapshot.get('risk_ready') is not True:
        raise ValueError('Paper risk loop not ready or stale')
    if set(snapshot['pairs']) != {'BTC/USDT', 'ETH/USDT', 'SOL/USDT'}:
        raise ValueError('Unexpected market universe')
    if any(p['status'] != 'ok' or p['checked_candles'] < 200 for p in snapshot['pairs'].values()):
        raise ValueError('Paper candles not ready')
    if snapshot.get('schema_version',1) not in (1,2):
        raise ValueError('Unknown paper status schema')
    if snapshot.get('schema_version')==2:
        for pair in snapshot['pairs'].values():
            quote=pair.get('public_book',{})
            if quote.get('status')!='ok' or not 0 <= (now-datetime.fromisoformat(quote['observed_at'])).total_seconds() <= 30:
                raise ValueError('Public price snapshot unavailable or stale')
    db_path = root / 'user_data' / profile.database
    with closing(sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        snapshot['native_trades'] = db.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
        snapshot['native_orders'] = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    snapshot['checked_at'] = now.isoformat()
    snapshot['status'] = 'running_with_public_data'
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--exchange', choices=['kraken', 'okx'], default='kraken')
    args = parser.parse_args()
    try:
        report = check(exchange=args.exchange)
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
