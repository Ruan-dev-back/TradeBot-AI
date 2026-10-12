"""Local heartbeat content only; no notification transport or service registration."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from external_health import payload


class ExternalHealthTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,12,18,tzinfo=timezone.utc)
        self.body={'healthy':True,'entries_blocked':False,'alerts':[],
            'snapshot':{'dry_run':True,'observed_at':self.now.isoformat(),'pairs':{},'risk':{'halted':False,'drawdown':0}}}

    def test_minimal_payload_excludes_wallet_prices_and_private_settings(self):
        with patch('external_health.collect',return_value=self.body),patch('external_health.observer_health',return_value={'status':'healthy'}):
            result=payload(now=self.now)
        self.assertTrue(result['engine_healthy']);self.assertTrue(result['dry_run'])
        self.assertNotIn('wallet',result);self.assertNotIn('positions',result)
        self.assertIn('local stdout',result['transport'])

    def test_missing_observer_is_reported_despite_healthy_engine(self):
        with patch('external_health.collect',return_value=self.body),patch('external_health.observer_health',side_effect=ValueError('stale')):
            self.assertEqual(payload(now=self.now)['observer']['status'],'failed')

    def test_halt_is_distinct_from_engine_liveness(self):
        self.body['entries_blocked']=True;self.body['snapshot']['risk']['halted']=True
        with patch('external_health.collect',return_value=self.body),patch('external_health.observer_health',return_value={'status':'failed'}):
            result=payload(now=self.now)
        self.assertTrue(result['engine_healthy']);self.assertTrue(result['drawdown_halted'])

    def test_invalid_identity_is_not_hardcoded_as_dry_run(self):
        self.body['snapshot']['dry_run']=False;self.body['healthy']=False
        with patch('external_health.collect',return_value=self.body),patch('external_health.observer_health',return_value={'status':'failed'}):
            result=payload(now=self.now)
        self.assertFalse(result['dry_run']);self.assertFalse(result['engine_healthy'])
