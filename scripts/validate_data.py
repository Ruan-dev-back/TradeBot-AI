"""Valida candles horários reais antes de permitir o backtest."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

from safety import PERIODS

ROOT = Path(__file__).resolve().parents[1]


def validate_candles(data):
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(data.columns) or data.empty:
        raise ValueError("OHLCV vazio ou incompleto")
    if not isinstance(data["date"].dtype, pd.DatetimeTZDtype) or str(data["date"].dt.tz) != "UTC":
        raise ValueError("Timestamps devem ser explicitamente UTC; datas ingênuas são recusadas")
    if not (data["date"].dt.floor("1h") == data["date"]).all():
        raise ValueError("Timestamps desalinhados ao timeframe 1h")
    if not data["date"].is_monotonic_increasing or data["date"].duplicated().any():
        raise ValueError("Timestamps duplicados ou fora de ordem")
    if data[list(required)].isna().any().any():
        raise ValueError("OHLCV contém valores ausentes")
    if not np.isfinite(data[["open", "high", "low", "close", "volume"]].to_numpy()).all():
        raise ValueError("OHLCV contém valores não finitos")
    if (data[["open", "high", "low", "close"]] <= 0).any().any() or (data["volume"] < 0).any():
        raise ValueError("Preço ou volume inválido")
    if ((data["high"] < data[["open", "close", "low"]].max(axis=1))
            | (data["low"] > data[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("OHLC inconsistente")
    if not data["date"].diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Cobertura horária incompleta: gaps ou timeframe incompatível")


def inspect_data(path):
    data = pd.read_feather(path)
    validate_candles(data)
    manifest = {
        "source": "Binance public spot OHLCV via Freqtrade download-data",
        "file": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "candles": len(data), "first": str(data["date"].iloc[0]),
        "last": str(data["date"].iloc[-1]), "periods": {},
        "exchange": "binance", "pair": "BTC/USDT", "timeframe": "1h",
    }
    provenance_path = path.parent / "archive_provenance.json"
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text())
        if provenance["file_sha256"] != manifest["sha256"]:
            raise ValueError("Dataset não corresponde à proveniência registrada")
        for name, expected in (("exchange", "binance"), ("pair", "BTC/USDT"), ("timeframe", "1h")):
            if provenance.get(name) != expected:
                raise ValueError("Origem/par/timeframe incompatível")
        manifest["source"] = provenance["source"]
        manifest["provenance"] = provenance
    for name, (start, end) in PERIODS.items():
        start_ts = pd.to_datetime(start, format="%Y%m%d", utc=True)
        end_ts = pd.to_datetime(end, format="%Y%m%d", utc=True)
        expected = pd.date_range(start_ts - pd.Timedelta(hours=200), end_ts, freq="1h", inclusive="left")
        subset = data[(data["date"] >= expected[0]) & (data["date"] < end_ts)]
        if len(subset) != len(expected) or not pd.DatetimeIndex(subset["date"]).equals(expected):
            raise ValueError(f"Cobertura horária incompleta em {name}, incluindo warm-up")
        active = subset[subset["date"] >= start_ts]
        if len(active) < 1000:
            raise ValueError(f"Amostra mínima de 1000 candles não satisfeita em {name}")
        manifest["periods"][name] = {
            "candles": len(active), "first": str(active["date"].iloc[0]),
            "last": str(active["date"].iloc[-1]),
            "first_open": float(active["open"].iloc[0]),
            "last_close": float(active["close"].iloc[-1]),
        }
    return manifest


def main():
    path = ROOT / "user_data/data/binance/BTC_USDT-1h.feather"
    manifest = inspect_data(path)
    output = ROOT / "user_data/research/data_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
