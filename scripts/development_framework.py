"""Frozen candidate plan and bounded native backtests on development 2024 only."""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from audit_guard import require_locked_holdout, verify_baseline
from paper_risk import RiskPolicy

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {'baseline': 'SmaRsiStrategy', 'trend': 'TrendDevelopment',
              'breakout': 'BreakoutDevelopment', 'mean_reversion': 'MeanReversionDevelopment',
              'breakout_volume': 'BreakoutVolumeDevelopment'}
FOLDS = {'D1': ('20240101', '20240401', '20240701'),
         'D2': ('20240101', '20240701', '20241001'),
         'D3': ('20240101', '20241001', '20250101')}


def experiment_plan(candidate=None, fold=None):
    verify_baseline()
    require_locked_holdout()
    if candidate is not None and candidate not in CANDIDATES:
        raise ValueError('Unknown development candidate')
    if fold is not None and fold not in FOLDS:
        raise ValueError('Unknown development fold; validation and holdout are forbidden')
    risk = RiskPolicy(fee=0.001)  # Historical Binance costs, distinct from Kraken paper.
    files = ['research_strategies/DevelopmentCandidates.py', 'scripts/development_framework.py',
             'scripts/paper_risk.py', 'docs/experiment-plan.md', 'docs/development-framework.md']
    return {'created_at': datetime.now(timezone.utc).isoformat(),
            'source': 'published Binance BTC/USDT spot 1h acquisition; no exchange mixing',
            'candidates': CANDIDATES, 'folds': FOLDS,
            'candidate': candidate, 'fold': fold,
            'candidate_code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
            'baseline_files': verify_baseline()['files'], 'risk_policy': asdict(risk),
            'evaluation_rules': {'selection_only': '2024 development folds, no independent validation claim',
                                 'state': 'each candidate/fold starts with 1000 USDT, no transferred positions',
                                 'warmup': 'past only, at least 200 hours before each evaluation',
                                 'fold_boundary': 'data ends at 23:00 UTC preceding exclusive end; final hourly close one hour earlier',
                                 'baseline_stake': 'original frozen strategy/config behavior; candidates fixed risk sizing',
                                 'costs': 'native 10 bps/side; execution/extra fees require separate sensitivity',
                                 'risk_state': 'native backtests do not model paper persisted drawdown/cooldown',
                                 'promotion': 'none; criteria in docs/experiment-plan.md; cost and marked-equity replay still required'},
            'holdout_prices_inspected': False}


def run(candidate, fold, directory):
    from audit_bias import read_development_only
    from download_archive import load_market_snapshot
    from offline_backtest import OfflineResearchBinance
    from freqtrade.commands import Arguments
    from freqtrade.commands.optimize_commands import setup_optimize_configuration
    from freqtrade.enums import RunMode
    from freqtrade.optimize.backtesting import Backtesting
    from freqtrade.util import get_progress_tracker
    import os
    from safety import validate_config

    plan = experiment_plan(candidate, fold)
    source = ROOT / 'user_data/data/binance/BTC_USDT-1h.feather'
    manifest = json.loads((ROOT / 'docs/evidence/data_manifest.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Source archive lineage changed')
    frame = read_development_only(source)
    _, begin, end = FOLDS[fold]
    start_utc = datetime.strptime(begin, '%Y%m%d').replace(tzinfo=timezone.utc)
    end_utc = datetime.strptime(end, '%Y%m%d').replace(tzinfo=timezone.utc)
    frame = frame.loc[(frame['date'] >= start_utc - timedelta(hours=400)) &
                      (frame['date'] < end_utc)].reset_index(drop=True)
    datadir = directory / 'data'
    datadir.mkdir(parents=True)
    frame.to_feather(datadir / 'BTC_USDT-1h.feather')
    source_config = json.loads((ROOT / 'user_data/config.json').read_text())
    validate_config(source_config, os.environ)
    args = ['backtesting', '--config', str(ROOT / 'user_data/config.json'),
            '--strategy', CANDIDATES[candidate], '--timerange', begin + '-' + end,
            '--datadir', str(datadir), '--fee', '0.001', '--cache', 'none',
            '--export', 'trades', '--backtest-directory', str(directory / 'exports')]
    if candidate != 'baseline':
        args += ['--strategy-path', str(ROOT / 'research_strategies')]
    config = setup_optimize_configuration(Arguments(args).get_parsed_arg(), RunMode.BACKTEST)
    config['pairs'] = ['BTC/USDT']
    market, _ = load_market_snapshot(ROOT / 'docs/evidence/market_snapshot.json')
    exchange = OfflineResearchBinance(config, market)
    (directory / 'protocol.json').write_text(json.dumps(plan, indent=2) + '\n')
    try:
        with get_progress_tracker():
            backtest = Backtesting(config, exchange=exchange)
            backtest.start()
    finally:
        exchange.close()
        Backtesting.cleanup()
    verify_baseline()
    require_locked_holdout()
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', choices=CANDIDATES)
    parser.add_argument('--fold', choices=FOLDS)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute and (not args.candidate or not args.fold):
        parser.error('Execution requires one fixed candidate and one fixed development fold')
    plan = experiment_plan(args.candidate, args.fold)
    directory = ROOT / 'user_data/research/development-experiments' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    (directory / 'protocol.json').write_text(json.dumps(plan, indent=2) + '\n')
    if args.execute:
        run(args.candidate, args.fold, directory)
    print(json.dumps({'protocol': str(directory / 'protocol.json'), 'executed': args.execute}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
