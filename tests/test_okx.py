"""OKX software fixtures only; public/live outcomes are recorded separately."""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from paper_profiles import minimum_notional, profile_for
from paper_risk import RiskPolicy, RiskState, validate_paper_config
from check_okx import public_get
import test_paper_engine as _engine
from freqtrade.exchange import Okx


class NativeOkxEngineTests(_engine.NativePaperEngineTests):
    paper_exchange = 'okx'
    exchange_type = Okx


class OkxSafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'user_data/config.paper.okx.json').read_text())
        # Synthetic instrument metadata, never reported as observed OKX data.
        self.market = {'precision': {'amount': .00001, 'price': .1},
                       'limits': {'amount': {'min': .0001}, 'cost': {'min': None}},
                       'info': {'instType': 'SPOT', 'state': 'live', 'minSz': '.0001',
                                'lotSz': '.00001', 'tickSz': '.1'}}

    def test_distinct_configuration_database_and_same_fixed_risk_policy(self):
        validate_paper_config(self.config)
        self.assertNotEqual(profile_for('okx').database, profile_for('kraken').database)
        self.assertNotEqual(profile_for('okx').state_folder, profile_for('kraken').state_folder)
        self.assertEqual(self.config['fee'], RiskPolicy().fee)
        self.assertEqual(self.config['stake_amount'], 25)
        self.config['db_url'] = 'sqlite:////freqtrade/user_data/tradesv3.paper.sqlite'
        with self.assertRaises(ValueError): validate_paper_config(self.config)

    def test_credentials_demo_sandbox_options_and_wrong_strategy_are_rejected(self):
        for field, value in (('password', 'fixture-private'), ('demo_trading', True), ('sandbox', True)):
            config = deepcopy(self.config);config['exchange'][field] = value
            with self.assertRaises(ValueError): validate_paper_config(config)
        config = deepcopy(self.config);config['strategy'] = 'MultiAssetPaperStrategy'
        with self.assertRaises(ValueError): validate_paper_config(config)
        config = deepcopy(self.config);config['exchange']['ccxt_config']['options']['defaultType'] = 'swap'
        with self.assertRaises(ValueError): validate_paper_config(config)

    def test_minimum_cost_is_derived_from_verified_size_lot_tick_only(self):
        self.assertEqual(minimum_notional('okx', self.market, 100000), 10)
        for key, value in (('minSz', '.001'), ('state', 'suspend'), ('instType', 'SWAP'), ('lotSz', '.01')):
            market = deepcopy(self.market);market['info'][key] = value
            with self.assertRaises(ValueError): minimum_notional('okx', market, 100000)
        with self.assertRaises(ValueError): minimum_notional('kraken', self.market, 100000)

    def test_proxy_exchange_and_region_denials_are_distinguished(self):
        url = 'https://www.okx.com/api/v5/public/time'
        exceptions = [urllib.error.URLError('Tunnel connection failed: 403 Forbidden'),
                      urllib.error.HTTPError(url, 403, 'Forbidden', {}, io.BytesIO(b'error code: 1010')),
                      urllib.error.HTTPError(url, 451, 'Restricted', {}, io.BytesIO(b'region'))]
        for error, status in zip(exceptions, ('proxy_connect_403', 'provider_http_error', 'exchange_region_restriction')):
            with patch('check_okx.urllib.request.urlopen', side_effect=error):
                self.assertEqual(public_get('/api/v5/public/time')['status'], status)

    def test_public_checker_refuses_private_paths_before_network(self):
        with patch('check_okx.urllib.request.urlopen') as request:
            with self.assertRaises(ValueError): public_get('/api/v5/account/trade-fee')
            request.assert_not_called()
