"""Lookahead/recursive nativos offline e testes temporais adicionais somente em 2024."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from freqtrade.commands import Arguments
from freqtrade.commands.optimize_commands import setup_optimize_configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.analysis.lookahead import LookaheadAnalysis
from freqtrade.optimize.analysis.lookahead_helpers import LookaheadAnalysisSubFunctions
from freqtrade.optimize.analysis.recursive import RecursiveAnalysis
from freqtrade.optimize.analysis.recursive_helpers import RecursiveAnalysisSubFunctions
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.resolvers import StrategyResolver
from freqtrade.util import get_progress_tracker

from audit_guard import DEVELOPMENT_START, DEVELOPMENT_END, require_development_dates
from audit_guard import require_locked_holdout, verify_baseline
from download_archive import load_market_snapshot
from offline_backtest import OfflineResearchBinance
from safety import validate_config
from validate_data import validate_candles

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIRECTORY = ROOT / "user_data/research/audit-bias"
COLUMNS = ["sma_fast", "sma_slow", "rsi", "enter_long", "exit_long"]
RSI_TOLERANCE = 0.001  # Unidade de RSI, critério de engenharia fixado antes da auditoria.


def read_development_only(path):
    # O scanner filtra antes de entregar OHLCV ao pandas/motor de pesquisa.
    # Não usar pd.read_feather(source), que entregaria também o holdout ao pandas.
    dataset = ds.dataset(path, format="ipc")
    date_type = dataset.schema.field("date").type
    lower = pa.scalar(datetime(2023, 12, 1, tzinfo=timezone.utc), type=date_type)
    upper = pa.scalar(DEVELOPMENT_END, type=date_type)
    table = dataset.to_table(filter=(ds.field("date") >= lower) & (ds.field("date") < upper))
    frame = table.to_pandas()
    validate_candles(frame)
    if (frame["date"] >= DEVELOPMENT_END).any():
        raise ValueError("Filtro temporal do scanner falhou")
    require_development_dates(frame.loc[frame["date"] >= DEVELOPMENT_START, "date"])
    if len(frame.loc[frame["date"] >= DEVELOPMENT_START]) != 8784:
        raise ValueError("Cobertura de desenvolvimento deve conter as 8784 horas de 2024")
    return frame


def indicators(strategy, frame):
    result = strategy.populate_indicators(frame.copy(), {"pair": "BTC/USDT"})
    result = strategy.populate_entry_trend(result, {"pair": "BTC/USDT"})
    return strategy.populate_exit_trend(result, {"pair": "BTC/USDT"})


def prefix_differences(strategy, frame, cuts):
    full = indicators(strategy, frame)
    differences = {column: 0 for column in COLUMNS}
    for cut in sorted(set(cuts)):
        if not 1 <= cut <= len(frame):
            raise ValueError("Corte fora do dataset de desenvolvimento")
        prefix = indicators(strategy, frame.iloc[:cut])
        for column in COLUMNS:
            same = np.isclose(full[column].iloc[:cut], prefix[column], rtol=1e-12, atol=1e-9,
                              equal_nan=True)
            differences[column] += int((~same).sum())
    return {"prefixes": len(set(cuts)), "differences": differences}


def rolling_startup(strategy, frame, startup=200):
    full = indicators(strategy, frame)
    max_errors = dict.fromkeys(("sma_fast", "sma_slow", "rsi"), 0.0)
    flips = {"enter_long": 0, "exit_long": 0}
    missing = 0
    count = 0
    worst_rsi_at = None
    for index in range(len(frame)):
        if frame["date"].iloc[index] < DEVELOPMENT_START:
            continue
        part = indicators(strategy, frame.iloc[max(0, index - startup):index + 1].reset_index(drop=True))
        for column in max_errors:
            value, reference = part[column].iloc[-1], full[column].iloc[index]
            if not (math.isfinite(value) and math.isfinite(reference)):
                missing += 1
                continue
            error = abs(value - reference)
            if error > max_errors[column]:
                max_errors[column] = float(error)
                if column == "rsi":
                    worst_rsi_at = str(frame["date"].iloc[index])
        for column in flips:
            flips[column] += int(part[column].iloc[-1] != full[column].iloc[index])
        count += 1
    return {"startup": startup, "candles_checked": count, "max_absolute_errors": max_errors,
            "worst_rsi_at": worst_rsi_at, "signal_flips": flips, "missing_values": missing,
            "rsi_tolerance": RSI_TOLERANCE,
            "passed": missing == 0 and not any(flips.values()) and max_errors["rsi"] <= RSI_TOLERANCE}


def main():
    verify_baseline()
    require_locked_holdout()
    source_config = json.loads((ROOT / "user_data/config.json").read_text())
    validate_config(source_config, os.environ)
    source = ROOT / "user_data/data/binance/BTC_USDT-1h.feather"
    manifest = json.loads((ROOT / "docs/evidence/data_manifest.json").read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Dados locais divergem da aquisição publicada")
    frame = read_development_only(source)
    work = AUDIT_DIRECTORY / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    datadir = work / "data"
    datadir.mkdir(parents=True)
    dataset_path = datadir / "BTC_USDT-1h.feather"
    frame.to_feather(dataset_path)
    args = ["backtesting", "--config", str(ROOT / "user_data/config.json"),
            "--strategy", "SmaRsiStrategy", "--timeframe", "1h",
            "--timerange", "20240101-20250101", "--datadir", str(datadir),
            "--fee", "0.001", "--cache", "none", "--backtest-directory", str(work / "exports")]
    config = setup_optimize_configuration(Arguments(args).get_parsed_arg(), RunMode.BACKTEST)
    config["pairs"] = ["BTC/USDT"]
    config["minimum_trade_amount"] = 20
    config["targeted_trade_amount"] = 100
    config["startup_candle"] = [50, 100, 200, 400, 800]
    strategy_obj = next(obj for obj in StrategyResolver.search_all_objects(config, enum_failed=False)
                        if obj["name"] == "SmaRsiStrategy")
    snapshot_path = ROOT / "docs/evidence/market_snapshot.json"
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != manifest["provenance"]["market_snapshot_sha256"]:
        raise ValueError("Snapshot real diverge da proveniência publicada")
    market, _ = load_market_snapshot(snapshot_path)
    summary = {"created_at": datetime.now(timezone.utc).isoformat(), "freqtrade": "2026.9",
               "network": "none (docker-compose.audit.yml)", "period": "20240101-20250101",
               "source_filter": "2023-12-01 <= date < 2025-01-01; Arrow filter before pandas/native engine",
               "baseline_files": verify_baseline()["files"],
               "source_dataset_sha256": manifest["sha256"],
               "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "offline_adapter_sha256": hashlib.sha256((ROOT / "scripts/offline_backtest.py").read_bytes()).hexdigest(),
               "development_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
               "candles": len(frame), "first": str(frame["date"].iloc[0]), "last": str(frame["date"].iloc[-1]),
               "holdout_prices_inspected": False}
    for label, cls, helper in (("lookahead", LookaheadAnalysis, LookaheadAnalysisSubFunctions),
                               ("recursive", RecursiveAnalysis, RecursiveAnalysisSubFunctions)):
        print(f"INÍCIO: análise nativa {label}, somente 2024, rede desativada", flush=True)
        local = helper.calculate_config_overrides(deepcopy(config))
        analysis = cls(local, strategy_obj)
        analysis.exchange = OfflineResearchBinance(local, market)
        try:
            with get_progress_tracker() as progress:
                analysis.start(progress)
            if label == "lookahead":
                current = analysis.current_analysis
                summary[label] = {"total_signals": current.total_signals,
                                  "biased_entry_signals": current.false_entry_signals,
                                  "biased_exit_signals": current.false_exit_signals,
                                  "biased_indicators": current.false_indicators,
                                  "has_bias": current.has_bias,
                                  "failed_check": analysis.failed_bias_check,
                                  "diagnostic_overrides": {"dry_run_wallet": local["dry_run_wallet"],
                                      "stake_amount": local["stake_amount"], "max_open_trades": local["max_open_trades"]},
                                  "force_exit_skipped": True}
                helper.text_table_lookahead_analysis_instances(local, [analysis])
            else:
                summary[label] = {"startup_candles": analysis._startup_candle,
                                  "relative_differences_last_row": {
                                      key: {str(k): v if math.isfinite(v) else None for k, v in value.items()}
                                      for key, value in analysis.dict_recursive.items()},
                                  "scope": "native last-row comparison; additional rolling check below"}
                helper.text_table_recursive_analysis_instances([analysis])
        finally:
            analysis.exchange.close()
            Backtesting.cleanup()
        print(f"CONCLUÍDO: {label}", flush=True)
    strategy = StrategyResolver.load_strategy(deepcopy(config))
    source_trades = json.loads((ROOT / "docs/evidence/backtest-development.json").read_text())["freqtrade_summary"]["trades"]
    cuts = []
    for trade in source_trades:
        for field in ("open_date", "close_date"):
            date = pd.Timestamp(trade[field])
            if date < DEVELOPMENT_END:
                cuts.append(int((frame["date"] <= date).sum()))
    cuts += [int((frame["date"] < pd.Timestamp(f"2024-{month:02d}-01", tz="UTC")).sum())
             for month in range(2, 13)]
    summary["prefix_check"] = prefix_differences(strategy, frame, cuts)
    print("INÍCIO: recursive rolling com 200 candles em todas as 8784 horas de 2024", flush=True)
    summary["rolling_recursive"] = rolling_startup(strategy, frame)
    summary["passed"] = (not summary["lookahead"]["has_bias"] and not summary["lookahead"]["failed_check"]
                         and summary["lookahead"]["total_signals"] >= 20
                         and not any(summary["prefix_check"]["differences"].values())
                         and summary["rolling_recursive"]["passed"])
    output = AUDIT_DIRECTORY / "latest.json"
    verify_baseline()
    require_locked_holdout()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    (work / "summary.json").write_text(output.read_text())
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
