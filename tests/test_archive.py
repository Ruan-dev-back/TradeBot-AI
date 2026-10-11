import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import tempfile
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from download_archive import parse_archive, verify_checksum, parse_market_response, load_market_snapshot, METADATA_URL, ccxt


class ArchiveTests(unittest.TestCase):
    # Arquivos sintéticos exclusivamente para testes do importador, não para backtesting.
    def monthly_zip(self, month, unit, missing=False):
        start = pd.Timestamp(f"{month}-01", tz="UTC")
        dates = pd.date_range(start, start + pd.offsets.MonthBegin(1), freq="1h", inclusive="left")
        multiplier = 1000000 if unit == "us" else 1000
        rows = []
        for date in dates:
            timestamp = int(date.timestamp()) * multiplier
            rows.append([timestamp, 100, 102, 99, 101, 3, timestamp + 3600 * multiplier - 1,
                         300, 2, 1, 100, 0])
        if missing:
            rows.pop(20)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(f"BTCUSDT-1h-{month}.csv", pd.DataFrame(rows).to_csv(index=False, header=False))
        return output.getvalue()

    def test_milliseconds_and_microseconds_are_both_utc_hourly(self):
        for month, unit in (("2024-12", "ms"), ("2025-01", "us")):
            with self.subTest(month=month):
                frame = parse_archive(self.monthly_zip(month, unit), month)
                self.assertEqual(str(frame["date"].dt.tz), "UTC")
                self.assertEqual(frame["date"].iloc[0], pd.Timestamp(f"{month}-01", tz="UTC"))
                self.assertEqual(len(frame), 31 * 24)

    def test_missing_candle_or_wrong_units_are_refused(self):
        with self.assertRaises(ValueError):
            parse_archive(self.monthly_zip("2025-01", "us", missing=True), "2025-01")
        with self.assertRaises(ValueError):
            parse_archive(self.monthly_zip("2025-01", "ms"), "2025-01")

    def test_checksum_verifies_content_and_filename(self):
        content = b"synthetic test only"
        digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(verify_checksum(content, digest + "  file.zip", "file.zip"), digest)
        for data, text in ((content + b"corrupted", digest + "  file.zip"),
                           (content, digest + "  another.zip"), (content, "bad-format")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verify_checksum(data, text, "file.zip")

    def metadata(self):
        return {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
                "baseAssetPrecision": 8, "quoteAssetPrecision": 8, "quotePrecision": 8, "isSpotTradingAllowed": True,
                "isMarginTradingAllowed": False, "orderTypes": ["MARKET"],
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "9000", "stepSize": "0.00001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": True},
                ]}]}

    def test_ccxt_parses_snapshot_and_refuses_another_pair(self):
        raw = self.metadata()
        market = parse_market_response(json.dumps(raw))
        self.assertEqual(market["precision"], {"amount": 0.00001, "price": 0.01, "base": 1e-8, "quote": 1e-8})
        self.assertEqual(market["limits"]["cost"]["min"], 5)
        raw["symbols"][0]["symbol"] = "ETHUSDT"
        with self.assertRaises(ValueError):
            parse_market_response(json.dumps(raw))

    def test_altered_market_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            raw = json.dumps(self.metadata())
            snapshot = {"raw_response": raw, "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                        "source_url": METADATA_URL, "ccxt_version": ccxt.__version__}
            path.write_text(json.dumps(snapshot))
            self.assertEqual(load_market_snapshot(path)[0]["symbol"], "BTC/USDT")
            snapshot["raw_response"] += " "
            path.write_text(json.dumps(snapshot))
            with self.assertRaisesRegex(ValueError, "Snapshot"):
                load_market_snapshot(path)
