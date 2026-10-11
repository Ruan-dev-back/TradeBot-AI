"""The only supported paper startup; accepts no arbitrary trade CLI arguments."""

from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import sys

from paper_risk import require_current_window, validate_paper_config
from audit_guard import require_locked_holdout, verify_baseline

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.argv[1:]:
        raise ValueError('Paper entrypoint does not accept CLI overrides')
    config = json.loads((ROOT / 'user_data/config.paper.json').read_text())
    verify_baseline()
    require_locked_holdout()
    validate_paper_config(config, os.environ)
    now = datetime.now(timezone.utc)
    require_current_window(now - timedelta(days=31), now, now)
    # CCXT async uses aiohttp_trust_env; no proxy values are copied or logged.
    # Runtime config is local and ignored; never printed or committed.
    if Path('/freqtrade/host-ca.pem').is_file():
        for field in ('ccxt_config', 'ccxt_async_config'):
            config['exchange'][field]['cafile'] = '/freqtrade/host-ca.pem'
    folder = ROOT / 'user_data/paper'
    folder.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(folder / 'engine.lock', os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_inheritable(lock_fd, True)  # Hold the single-writer lock through exec/restarts.
    path = folder / 'runtime.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(config, output)
    os.execvp('freqtrade', ['freqtrade', 'trade', '--config', str(path),
                          '--strategy', 'MultiAssetPaperStrategy', '--dry-run'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(f'Paper startup blocked: {error}', file=sys.stderr)
        raise SystemExit(2)
