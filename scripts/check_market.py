"""Public Kraken probes, with proxy denial distinguished from exchange responses."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
from paper_risk import require_current_window, validate_paper_config
ROOT = Path(__file__).resolve().parents[1]


def probe(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            body = response.read()
            payload = json.loads(body)
            return {'url': url, 'status': 'ok' if not payload.get('error') else 'exchange_error',
                    'http_status': response.status, 'bytes': len(body), 'api_errors': payload.get('error', [])}
    except urllib.error.HTTPError as error:
        return {'url': url, 'status': 'exchange_region_restriction' if error.code == 451 else 'http_error',
                'http_status': error.code, 'body_excerpt': error.read(600).decode(errors='replace')}
    except urllib.error.URLError as error:
        reason = str(error.reason)
        return {'url': url, 'status': 'proxy_connect_403' if 'Tunnel connection failed: 403' in reason else 'network_error',
                'error': reason}


def check():
    import ccxt
    import pandas as pd
    from validate_data import validate_candles
    config = json.loads((ROOT / 'user_data/config.paper.json').read_text())
    validate_paper_config(config)
    now = datetime.now(timezone.utc)
    require_current_window(now - timedelta(days=31), now, now)
    report = {'checked_at': now.isoformat(), 'exchange': 'kraken', 'private_api_used': False,
              'regional_limit': 'API availability does not establish account or jurisdiction eligibility',
              'holdout_prices_inspected': False,
              'probes': [probe('https://api.binance.com/api/v3/time'),
                         probe('https://api.kraken.com/0/public/Time'),
                         probe('https://api.kraken.com/0/public/AssetPairs')],
              'pairs': {pair: {'status': 'unverified'} for pair in config['exchange']['pair_whitelist']}}
    if any(item['status'] != 'ok' for item in report['probes'][1:]):
        report['status'] = 'blocked_public_connectivity'
        return report
    settings = {'enableRateLimit': True, 'timeout': 15000, 'requests_trust_env': True}
    if Path('/freqtrade/host-ca.pem').is_file():
        settings['cafile'] = '/freqtrade/host-ca.pem'
    exchange = ccxt.kraken(settings)
    try:
        markets = exchange.load_markets()
        for pair in config['exchange']['pair_whitelist']:
            market = markets.get(pair)
            if not market or market.get('active') is not True or not market.get('spot'):
                report['pairs'][pair] = {'status': 'unavailable'}
                continue
            candles = exchange.fetch_ohlcv(pair, timeframe='1h', limit=220)
            frame = pd.DataFrame(candles, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            frame['date'] = pd.to_datetime(frame['date'], unit='ms', utc=True)
            if frame.empty:
                raise ValueError('No public candles')
            require_current_window(frame['date'].iloc[0].to_pydatetime(), now, now)
            frame = frame.loc[frame['date'] + pd.Timedelta(hours=1) <= now].reset_index(drop=True)
            validate_candles(frame)
            if len(frame) < 200 or (now - frame['date'].iloc[-1]).total_seconds() > 7500:
                raise ValueError('Insufficient or stale closed candles')
            report['pairs'][pair] = {'status': 'ok', 'closed_candles': len(frame),
                                    'first_utc': str(frame['date'].iloc[0]), 'last_utc': str(frame['date'].iloc[-1]),
                                    'minimum_amount': market['limits']['amount']['min'],
                                    'minimum_cost': market['limits']['cost']['min'],
                                    'taker_fee_metadata': market.get('taker'), 'timeframe': '1h', 'gaps': 0, 'duplicates': 0}
        report['status'] = 'ok' if all(p['status'] == 'ok' for p in report['pairs'].values()) else 'unavailable_pairs'
    except Exception as error:
        report['status'] = 'market_check_failed'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        exchange.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = check()
    body = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body)
    print(body)
    return 0 if report['status'] == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
