"""Baixa klines reais Binance Vision, verificando os SHA-256 oficiais."""

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request
import zipfile

import ccxt
import pandas as pd

from safety import DOWNLOAD_RANGE

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h"
SOURCE = "Binance Vision official monthly spot klines; BTCUSDT; 1h"
METADATA_URL = "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT"


def parse_market_response(raw):
    info = json.loads(raw)
    symbols = info.get("symbols", [])
    if (len(symbols) != 1 or symbols[0].get("symbol") != "BTCUSDT"
            or symbols[0].get("baseAsset") != "BTC" or symbols[0].get("quoteAsset") != "USDT"
            or symbols[0].get("status") != "TRADING" or symbols[0].get("isSpotTradingAllowed") is not True):
        raise ValueError("Metadados não correspondem a Binance BTC/USDT spot ativo")
    # Mesma inicialização de CCXT.fetch_markets; não consulta dados de margem.
    exchange = ccxt.binance({"options": {"crossMarginPairsData": [], "isolatedMarginPairsData": []}})
    market = exchange.parse_market(symbols[0])
    if any(market["precision"].get(key) is None for key in ("amount", "price")):
        raise ValueError("Metadados não contêm precisões reais de preço e quantidade")
    return market


def load_market_snapshot(path):
    snapshot = json.loads(path.read_text())
    raw = snapshot["raw_response"].encode("utf-8")
    if snapshot["source_url"] != METADATA_URL or hashlib.sha256(raw).hexdigest() != snapshot["raw_sha256"]:
        raise ValueError("Snapshot de metadados inválido ou alterado")
    if snapshot["ccxt_version"] != ccxt.__version__:
        raise ValueError("Versão CCXT diverge da aquisição de metadados")
    return parse_market_response(raw), snapshot


def get_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "TradeBot-AI-research/0.1"})
    # urllib respeita proxy e SSL_CERT_FILE sem desligar TLS.
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise ValueError(f"Resposta inesperada: HTTP {response.status}")
        return response.read()


def verify_checksum(content, checksum_text, filename):
    fields = checksum_text.strip().split()
    if len(fields) != 2 or not re.fullmatch(r"[a-fA-F0-9]{64}", fields[0]):
        raise ValueError("Formato de checksum oficial inválido")
    if fields[1].lstrip("*") != filename:
        raise ValueError("Checksum pertence a outro arquivo")
    actual = hashlib.sha256(content).hexdigest()
    if actual != fields[0].lower():
        raise ValueError(f"SHA-256 divergente: {filename}")
    return actual


def parse_archive(content, month):
    filename = f"BTCUSDT-1h-{month}.csv"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if archive.namelist() != [filename]:
            raise ValueError("Conteúdo inesperado no ZIP; nenhum arquivo é extraído")
        with archive.open(filename) as stream:
            raw = pd.read_csv(stream, header=None)
    if raw.shape[1] != 12 or raw.empty:
        raise ValueError("Klines devem ter 12 colunas e pelo menos um candle")
    # Mudança oficial da Binance: spot >= janeiro/2025 usa microsegundos.
    unit = "us" if month >= "2025-01" else "ms"
    raw[0] = pd.to_numeric(raw[0], errors="raise")
    raw[6] = pd.to_numeric(raw[6], errors="raise")
    dates = pd.to_datetime(raw[0], unit=unit, utc=True)
    closes = pd.to_datetime(raw[6], unit=unit, utc=True)
    start = pd.Timestamp(f"{month}-01", tz="UTC")
    end = start + pd.offsets.MonthBegin(1)
    expected = pd.date_range(start, end, freq="1h", inclusive="left")
    if not pd.DatetimeIndex(dates).equals(expected):
        raise ValueError(f"Cobertura mensal inválida: {month}")
    epsilon = pd.Timedelta(microseconds=1) if unit == "us" else pd.Timedelta(milliseconds=1)
    if not (closes == dates + pd.Timedelta(hours=1) - epsilon).all():
        raise ValueError("Close times não correspondem a candles de 1h")
    frame = pd.DataFrame({"date": dates})
    for index, name in enumerate(("open", "high", "low", "close", "volume"), start=1):
        frame[name] = pd.to_numeric(raw[index], errors="raise").astype("float64")
    return frame


def main():
    start, end = DOWNLOAD_RANGE.split("-")
    months = pd.date_range(pd.to_datetime(start, format="%Y%m%d"),
                           pd.to_datetime(end, format="%Y%m%d"), freq="MS", inclusive="left")
    archives = ROOT / "user_data/data/binance/archives"
    archives.mkdir(parents=True, exist_ok=True)
    frames, records = [], []
    for date in months:
        month = date.strftime("%Y-%m")
        name = f"BTCUSDT-1h-{month}.zip"
        url = f"{BASE}/{name}"
        checksum = get_bytes(url + ".CHECKSUM").decode("ascii")
        path = archives / name
        content = path.read_bytes() if path.exists() else get_bytes(url)
        digest = verify_checksum(content, checksum, name)
        frame = parse_archive(content, month)
        if not path.exists():
            path.write_bytes(content)
        (archives / (name + ".CHECKSUM")).write_text(checksum)
        frames.append(frame)
        records.append({"url": url, "checksum_url": url + ".CHECKSUM",
                        "sha256": digest, "candles": len(frame),
                        "timestamp_unit": "us" if month >= "2025-01" else "ms"})
        print(f"{month}: {len(frame)} candles; SHA-256 verificado {digest}", flush=True)
    data = pd.concat(frames, ignore_index=True)
    start_ts = pd.to_datetime(start, format="%Y%m%d", utc=True)
    end_ts = pd.to_datetime(end, format="%Y%m%d", utc=True)
    data = data[(data["date"] >= start_ts) & (data["date"] < end_ts)].reset_index(drop=True)
    path = ROOT / "user_data/data/binance/BTC_USDT-1h.feather"
    # Exige integridade de todos os candles antes de substituir o dataset.
    from validate_data import validate_candles
    validate_candles(data)
    raw_metadata = get_bytes(METADATA_URL)
    parse_market_response(raw_metadata)
    snapshot = {"source_url": METADATA_URL, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "ccxt_version": ccxt.__version__, "raw_response": raw_metadata.decode("utf-8"),
                "raw_sha256": hashlib.sha256(raw_metadata).hexdigest()}
    snapshot_path = path.parent / "market_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    temporary = path.with_suffix(".tmp.feather")
    data.to_feather(temporary)
    temporary.replace(path)
    provenance = {"source": SOURCE, "exchange": "binance", "pair": "BTC/USDT",
                  "timeframe": "1h", "downloaded_at": datetime.now(timezone.utc).isoformat(),
                  "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "candles": len(data), "archives": records,
                  "market_snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                  "metadata_source": METADATA_URL}
    (path.parent / "archive_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Dataset real criado: {len(data)} candles; {path}", flush=True)


if __name__ == "__main__":
    main()
