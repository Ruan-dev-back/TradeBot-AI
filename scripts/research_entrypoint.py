"""Entrada Docker restrita a comandos de pesquisa; nunca chama `trade`."""

import argparse
import json
import os
from pathlib import Path
import sys

from safety import DOWNLOAD_RANGE, PERIODS, validate_config
from audit_guard import require_legacy_research_allowed

ROOT = Path(__file__).resolve().parents[1]


def build_command(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download-data", "download-archive", "list-data", "list-strategies", "test", "validate-data", "version", "audit-bias"):
        sub.add_parser(name)
    backtest = sub.add_parser("backtesting")
    backtest.add_argument("--period", choices=list(PERIODS), default="development")
    backtest.add_argument("--output-dir", type=Path)
    backtest.add_argument("--offline", action="store_true")
    args = parser.parse_args(["version"] if argv == ["--version"] else argv)
    base = ["freqtrade"]
    config = ["--config", str(ROOT / "user_data/config.json")]
    if args.command == "version":
        return base + ["--version"]
    if args.command == "test":
        return [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"]
    if args.command == "audit-bias":
        return [sys.executable, str(ROOT / "scripts/audit_bias.py")]
    if args.command == "validate-data":
        return [sys.executable, str(ROOT / "scripts/validate_data.py")]
    if args.command == "download-archive":
        return [sys.executable, str(ROOT / "scripts/download_archive.py")]
    if args.command == "download-data":
        return base + ["download-data"] + config + [
            "--pairs", "BTC/USDT", "--timeframes", "1h", "--trading-mode", "spot",
            "--timerange", DOWNLOAD_RANGE, "--data-format-ohlcv", "feather",
        ]
    if args.command == "list-data":
        return base + ["list-data"] + config + ["--show-timerange"]
    if args.command == "list-strategies":
        return base + ["list-strategies"] + config
    output_root = (ROOT / "user_data/backtest_results").resolve()
    output = (args.output_dir or output_root / args.period).resolve()
    if output != output_root and not output.is_relative_to(output_root):
        parser.error("Diretório de resultados deve estar em user_data/backtest_results")
    output.mkdir(parents=True, exist_ok=True)
    if args.offline:
        return [sys.executable, str(ROOT / "scripts/offline_backtest.py"),
                "--period", args.period, "--output-dir", str(output)]
    return base + ["backtesting"] + config + [
        "--strategy", "SmaRsiStrategy", "--timeframe", "1h",
        "--timerange", "-".join(PERIODS[args.period]),
        "--fee", "0.001", "--cache", "none", "--export", "trades",
        "--backtest-directory", str(output),
    ]


def main():
    try:
        config = json.loads((ROOT / "user_data/config.json").read_text())
        validate_config(config, os.environ)
        require_legacy_research_allowed(sys.argv[1:])
        command = build_command(sys.argv[1:])
    except (ValueError, OSError) as exc:
        print(f"Pesquisa bloqueada: {exc}", file=sys.stderr)
        return 2
    os.execvp(command[0], command)


if __name__ == "__main__":
    sys.exit(main())
