"""Quiesced local paper snapshots. Refuses backup while the operator holds its lock."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from paper_profiles import profile_for

ROOT=Path(__file__).resolve().parents[1]


def backup(exchange, root=ROOT):
    profile=profile_for(exchange)
    folder=root/'user_data'/profile.state_folder
    fd=os.open(folder/'engine.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sources={'native.sqlite':root/'user_data'/profile.database,
                 'risk.sqlite':folder/'risk.sqlite'}
        for source in sources.values():
            if not source.is_file():raise ValueError('Both paper databases must already exist')
        out=root/'user_data/research/backups'/exchange/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        out.mkdir(parents=True,mode=0o700)
        hashes={}
        for name,source in sources.items():
            target=out/name
            with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as read, \
                 closing(sqlite3.connect(target)) as write:
                read.backup(write)
                if write.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise ValueError('SQLite snapshot integrity check failed')
            target.chmod(0o600)
            hashes[name]=hashlib.sha256(target.read_bytes()).hexdigest()
        manifest={'exchange':exchange,'created_at':datetime.now(timezone.utc).isoformat(),
                  'quiesced_engine_lock':True,'files':hashes,
                  'native_restore_name':profile.database,'risk_restore_folder':profile.state_folder}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        return out
    finally:
        os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exchange',choices=['kraken','okx'],required=True)
    args=parser.parse_args()
    try:print(backup(args.exchange))
    except (ValueError,OSError,sqlite3.Error) as error:
        print(f'Backup refused; stop the selected paper service first: {type(error).__name__}: {error}')
        return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
