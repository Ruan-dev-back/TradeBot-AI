"""Explicit paper identities; no automatic exchange migration or shared databases."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PaperProfile:
    exchange: str
    config_file: str
    strategy: str
    state_folder: str
    database: str
    compose_file: str
    service: str


PROFILES = {
    'kraken': PaperProfile('kraken', 'config.paper.json', 'MultiAssetPaperStrategy',
                           'paper', 'tradesv3.paper.sqlite', 'docker-compose.paper.yml', 'papertrade'),
    'okx': PaperProfile('okx', 'config.paper.okx.json', 'OkxPaperStrategy',
                        'paper-okx', 'tradesv3.paper-okx.sqlite', 'docker-compose.okx.yml', 'okxpaper'),
}


def profile_for(exchange):
    try:
        return PROFILES[exchange]
    except KeyError:
        raise ValueError('Only explicit Kraken/OKX spot paper profiles are supported') from None


def minimum_notional(exchange, market, rate):
    from paper_risk import finite_positive
    amount = market.get('limits', {}).get('amount', {}).get('min')
    cost = market.get('limits', {}).get('cost', {}).get('min')
    if not finite_positive(amount, rate):
        raise ValueError('Unknown exchange minimum amount')
    if finite_positive(cost):
        return max(cost, amount * rate)
    # OKX SPOT publishes minSz/lotSz/tickSz, not a generic USDT minimum notional.
    # Derive only from verified official instrument fields; never assume a zero minimum.
    info = market.get('info', {})
    try:
        size, lot, tick = (float(info[k]) for k in ('minSz', 'lotSz', 'tickSz'))
    except (KeyError, ValueError, TypeError):
        raise ValueError('No official OKX minimum-size provenance') from None
    if (exchange != 'okx' or info.get('instType') != 'SPOT' or info.get('state') != 'live'
            or not finite_positive(size, lot, tick) or size != amount
            or market.get('precision', {}).get('amount') != lot
            or market.get('precision', {}).get('price') != tick):
        raise ValueError('Unknown or inconsistent official exchange minimums')
    return size * rate
