"""Reproduce the fixed 15-run offline development suite; never download data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json

from development_framework import ROOT, CANDIDATES, FOLDS, experiment_plan, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = experiment_plan()
    lock = json.loads((ROOT / 'docs/research2024-extension-lock.json').read_text())
    for name, expected in lock['files'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen pre-experiment protocol changed')
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    parent = ROOT / 'user_data/research/development-experiments'
    pending = parent / ('pending-' + stamp)
    pending.mkdir(parents=True)
    # Incomplete runs remain pending and are never chosen by the analyzer.
    for fold in FOLDS:
        for candidate in CANDIDATES:
            directory = pending / fold / candidate
            directory.mkdir(parents=True)
            print(f'Fixed development run: {fold}/{candidate}', flush=True)
            run(candidate, fold, directory)
    complete = parent / ('complete-' + stamp)
    pending.rename(complete)
    print(json.dumps({'completed_runs': 15, 'directory': str(complete)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
