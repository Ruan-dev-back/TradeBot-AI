"""Public exchange connectivity check; never sends orders or reads account keys."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt

CONFIG = Path(__file__).resolve().parents[1] / "user_data/config.paper.json"


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    exchange_config = config["exchange"]
    assert config["dry_run"] is True
    assert not exchange_config.get("key") and not exchange_config.get("secret")
    assert config["trading_mode"] == "spot"
    exchange = getattr(ccxt, exchange_config["name"])({"enableRateLimit": True, "timeout": 15000})
    try:
        markets = exchange.load_markets()
        report = {"exchange": exchange.id, "utc": datetime.now(timezone.utc).isoformat(), "pairs": {}}
        for pair in exchange_config["pair_whitelist"]:
            info = markets.get(pair)
            if not info or not info.get("spot") or not info.get("active", True):
                report["pairs"][pair] = {"status": "unavailable"}
                continue
            candles = exchange.fetch_ohlcv(pair, timeframe="1h", limit=3)
            report["pairs"][pair] = {
                "status": "ok" if candles else "empty",
                "latest_candle_utc": datetime.fromtimestamp(candles[-1][0] / 1000, timezone.utc).isoformat() if candles else None,
                "minimum_amount": info.get("limits", {}).get("amount", {}).get("min"),
                "minimum_cost": info.get("limits", {}).get("cost", {}).get("min"),
            }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if all(v["status"] == "ok" for v in report["pairs"].values()) else 2
    finally:
        exchange.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ccxt.BaseError, ConnectionError, TimeoutError, OSError, ValueError) as error:
        print(f"Falha ao verificar dados públicos da corretora: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
