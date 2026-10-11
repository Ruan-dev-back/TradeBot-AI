"""Diagnóstico público: distingue política do proxy de respostas da exchange."""

from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URLS = {
    "binance-api": "https://api.binance.com/api/v3/time",
    "binance-archive": "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip.CHECKSUM",
    "binance-public-data-api": "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT",
}


def classify(status=None, error="", body=""):
    error = error.lower()
    if "403" in error and ("tunnel" in error or "proxy" in error):
        return "proxy_denied_403"
    if status == 451 and "restricted location" in body.lower():
        return "exchange_location_restriction_451"
    if status == 403:
        return "destination_http_403_not_proven_proxy"
    if status is not None and 200 <= status < 300:
        return "reachable"
    if "certificate" in error or "ssl" in error:
        return "tls_error"
    if "timed out" in error or "timeout" in error:
        return "timeout"
    if "name resolution" in error or "name or service" in error:
        return "dns_error"
    return "other_http_or_network_error"


def probe(url):
    result = {"url": url, "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "TradeBot-AI-research/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            result.update(status=response.status, body=response.read(4096).decode(errors="replace"))
    except urllib.error.HTTPError as exc:
        result.update(status=exc.code, body=exc.read(4096).decode(errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["error"] = str(exc)
    result["classification"] = classify(result.get("status"), result.get("error", ""), result.get("body", ""))
    return result


def main():
    results = {name: probe(url) for name, url in URLS.items()}
    output = ROOT / "user_data/research/network-diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
