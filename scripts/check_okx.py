"""Official OKX public spot checks; no demo headers, account fees or private APIs."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

from paper_risk import require_current_window, validate_paper_config
from paper_profiles import minimum_notional

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ('BTC/USDT', 'ETH/USDT', 'SOL/USDT')
BASE = 'https://www.okx.com'


def public_get(path):
    allowed = {'/api/v5/public/time'} | {'/api/v5/public/instruments?instType=SPOT&instId=' +
                                         pair.replace('/', '-') for pair in PAIRS}
    if path not in allowed:
        raise ValueError('Only whitelisted public time/spot instrument requests are allowed')
    url = BASE + path
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'TradeBot-AI/0.1 public research',
                                                       'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            payload = json.loads(body)
            return {'url': url, 'http_status': response.status, 'status': 'ok' if payload.get('code') == '0' else 'exchange_api_error',
                    'body_sha256': hashlib.sha256(body).hexdigest(), 'payload': payload}
    except urllib.error.HTTPError as error:
        return {'url': url, 'status': 'exchange_region_restriction' if error.code == 451 else 'provider_http_error',
                'http_status': error.code, 'body_excerpt': error.read(600).decode(errors='replace')}
    except urllib.error.URLError as error:
        reason = str(error.reason)
        return {'url': url, 'status': 'proxy_connect_403' if 'Tunnel connection failed: 403' in reason else 'network_or_tls_error',
                'error': reason}


def check():
    import ccxt
    import pandas as pd
    from validate_data import validate_candles
    config = json.loads((ROOT / 'user_data/config.paper.okx.json').read_text())
    validate_paper_config(config)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=240)).replace(minute=0, second=0, microsecond=0)
    require_current_window(start, now, now)
    report = {'checked_at': now.isoformat(), 'exchange': 'okx', 'official_host': 'www.okx.com',
              'dry_run': True, 'private_api_used': False, 'holdout_prices_inspected': False,
              'account_region_eligibility_verified': False,
              'probes': [public_get('/api/v5/public/time')],
              'pairs': {pair: {'status': 'unverified'} for pair in PAIRS}}
    if report['probes'][0]['status'] != 'ok':
        report['status'] = 'blocked_public_connectivity'
        return report
    server = float(report['probes'][0]['payload']['data'][0]['ts']) / 1000
    report['server_clock_difference_seconds'] = abs(server - now.timestamp())
    if report['server_clock_difference_seconds'] > 30:
        report['status'] = 'invalid_clock'
        return report
    settings = dict(config['exchange']['ccxt_config'])
    if Path('/freqtrade/host-ca.pem').is_file():
        settings['cafile'] = '/freqtrade/host-ca.pem'
    exchange = ccxt.okx(settings)
    try:
        markets = exchange.load_markets()
        for pair in PAIRS:
            instrument = public_get('/api/v5/public/instruments?instType=SPOT&instId=' + pair.replace('/', '-'))
            report['probes'].append(instrument)
            market = markets.get(pair)
            if (instrument['status'] != 'ok' or not market or market.get('active') is not True
                    or not market.get('spot') or len(instrument['payload']['data']) != 1):
                report['pairs'][pair] = {'status': 'unavailable_or_unknown'}
                continue
            official = instrument['payload']['data'][0]
            if official.get('state') != 'live' or official.get('instType') != 'SPOT':
                raise ValueError('Non-live official spot instrument')
            for key in ('lotSz', 'tickSz', 'minSz'):
                if official[key] != market['info'][key]:
                    raise ValueError('Official instrument / CCXT metadata mismatch')
            ticker = exchange.fetch_ticker(pair)
            book = exchange.fetch_order_book(pair, limit=20)
            bid, ask = book['bids'][0][0], book['asks'][0][0]
            minimum = minimum_notional('okx', market, ask)
            rows = []
            cursor = int(start.timestamp() * 1000)
            for _ in range(4):
                page = exchange.fetch_ohlcv(pair, '1h', since=cursor, limit=100)
                if not page:
                    break
                rows.extend(page)
                next_cursor = page[-1][0] + 3600000
                if next_cursor <= cursor:
                    raise ValueError('OHLCV pagination did not advance')
                cursor = next_cursor
                if cursor >= now.timestamp() * 1000:
                    break
            frame = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            frame['date'] = pd.to_datetime(frame['date'], unit='ms', utc=True)
            frame = frame.loc[(frame['date'] >= start) & (frame['date'] + pd.Timedelta(hours=1) <= now)]
            validate_candles(frame)
            if len(frame) < 200 or (now-frame['date'].iloc[-1]).total_seconds() > 7500:
                raise ValueError('Insufficient or stale closed OKX candles')
            report['pairs'][pair] = {'status': 'ok', 'official_instrument': official,
              'precision': market['precision'], 'limits': market['limits'],
              'derived_minimum_notional_at_ask': minimum,
              'minimum_notional_source': 'official minSz times current ask if cost.min is not published',
              'bid': bid, 'ask': ask, 'spread_bps': (ask-bid)/((ask+bid)/2)*10000,
              'base_volume_24h': ticker.get('baseVolume'), 'quote_volume_24h': ticker.get('quoteVolume'),
              'ccxt_maker_assumption': market.get('maker'), 'ccxt_taker_assumption': market.get('taker'),
              'fees_source': 'CCXT static/public metadata; not authenticated account tariff',
              'closed_candles': len(frame), 'first_utc': str(frame['date'].iloc[0]),
              'last_utc': str(frame['date'].iloc[-1]), 'gaps': 0, 'duplicates': 0, 'timeframe': '1h'}
        report['status'] = 'ok' if all(p['status'] == 'ok' for p in report['pairs'].values()) else 'unavailable_pairs'
    except Exception as error:
        report['status'] = 'public_market_check_failed'
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
