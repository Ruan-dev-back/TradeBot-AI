from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network_diagnostics import classify


class NetworkTests(unittest.TestCase):
    def test_proxy_403_is_distinct_from_exchange_451_and_direct_403(self):
        self.assertEqual(classify(error="Tunnel connection failed: 403 Forbidden"), "proxy_denied_403")
        self.assertEqual(classify(451, body="Service unavailable from a restricted location"), "exchange_location_restriction_451")
        self.assertEqual(classify(403), "destination_http_403_not_proven_proxy")

    def test_tls_dns_timeout_and_success_are_distinct(self):
        self.assertEqual(classify(error="CERTIFICATE_VERIFY_FAILED"), "tls_error")
        self.assertEqual(classify(error="Temporary failure in name resolution"), "dns_error")
        self.assertEqual(classify(error="timed out"), "timeout")
        self.assertEqual(classify(200), "reachable")
