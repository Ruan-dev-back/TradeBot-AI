"""Strict current-schema validation, independent of the operator PID."""
from contextlib import closing
from datetime import datetime, timedelta
import json
import sqlite3

from paper_profiles import profile_for
from paper_risk import RiskPolicy, finite_positive


def utc(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError('non_utc_timestamp')
    return result


def age(value, now, limit):
    if not 0 <= (now - utc(value)).total_seconds() <= limit:
        raise ValueError('stale_or_future_timestamp')


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)


def validate_current(snapshot, root, now):
    age(snapshot['risk']['observed_at'], now, 30)
    age(snapshot['wallet']['observed_at'], now, 30)
    if not finite_positive(snapshot['wallet']['equity_usdt'], snapshot['wallet']['free_usdt']):
        raise ValueError('invalid_wallet')
    for pair in snapshot['pairs'].values():
        opened = utc(pair['last_closed_utc'])
        first = utc(pair['first_utc'])
        if (opened < datetime.fromisoformat('2026-07-01T00:00:00+00:00')
                or first < datetime.fromisoformat('2026-07-01T00:00:00+00:00')
                or opened.minute or opened.second or opened.microsecond
                or first.minute or first.second or first.microsecond
                or (opened-first).total_seconds()!=(pair['checked_candles']-1)*3600
                or pair['timeframe'] != '1h'
                or not 3600 <= (now-opened).total_seconds() <= 7500):
            raise ValueError('invalid_or_stale_candle')
        quote = pair['public_book']
        if not finite_positive(quote['bid'], quote['ask']) or quote['bid'] > quote['ask']:
            raise ValueError('invalid_public_quote')
        age(quote['observed_at'], now, 30)
    profile = profile_for(snapshot['exchange'])
    for path in (root/'user_data'/profile.database,
                 root/'user_data'/profile.state_folder/'risk.sqlite',
                 root/'user_data'/profile.state_folder/'telemetry.sqlite'):
        with closing(readonly(path)) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('sqlite_integrity_failure')
            if path.name == 'risk.sqlite':
                saved = json.loads(db.execute('SELECT body FROM risk WHERE id=1').fetchone()[0])
                if saved['policy_sha256'] != RiskPolicy().fingerprint:
                    raise ValueError('risk_policy_mismatch')
                age(saved['observed_at'], now, 30)
                # The writer can advance between file/DB reads; never require an
                # impossible atomic snapshot across independent stores.
                if (saved['peak'] < snapshot['risk']['peak']
                        or (snapshot['risk']['halted'] and not saved['halted'])
                        or not set(snapshot['risk']['closed_ids']).issubset(saved['closed_ids'])):
                    raise ValueError('risk_snapshot_not_reconciled')
