"""Motor nativo Freqtrade com OHLCV real e metadados reais em cache, sem rede.

Filtros atuais da exchange; regras históricas de lote/tick não estão disponíveis.
Somente pesquisa, jamais um adaptador para trading/dry-run ao vivo.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from freqtrade.commands.optimize_commands import setup_optimize_configuration
from freqtrade.commands import Arguments
from freqtrade.enums import RunMode
from freqtrade.exchange.binance import Binance
from freqtrade.optimize.backtesting import Backtesting

from safety import PERIODS, validate_config
from audit_guard import require_legacy_research_allowed
from validate_data import inspect_data
from download_archive import load_market_snapshot

ROOT = Path(__file__).resolve().parents[1]
MODEL = {
    "name": "Freqtrade native Backtesting with offline Binance research adapter",
    "ohlcv": "real official Binance Vision BTCUSDT spot 1h archives",
    "pair": "BTC/USDT", "trading_mode": "spot", "leverage": 1,
    "metadata": "real current Binance public exchangeInfo snapshot parsed by pinned CCXT",
    "limitation": "Current exchange tick/lot/notional filters used; historical filters unavailable; no spread/slippage/market-impact model",
    "fee_per_side": 0.001,
}


class OfflineResearchBinance(Binance):
    def __init__(self, config, market):
        self._offline_initialized = False
        if (config.get("runmode") != RunMode.BACKTEST or config.get("dry_run") is not True
                or config.get("trading_mode") != "spot"):
            raise ValueError("Adaptador offline aceita somente BACKTEST dry_run spot")
        if config.get("fee") != 0.001:
            raise ValueError("A taxa de pesquisa deve ser explicitamente 0.001")
        exchange = config.get("exchange", {})
        if exchange.get("name") != "binance" or exchange.get("pair_whitelist") != ["BTC/USDT"]:
            raise ValueError("Origem e par devem ser Binance BTC/USDT")
        if any(exchange.get(key) for key in ("key", "secret", "api_key", "apiKey", "password")):
            raise ValueError("Nenhuma credencial é aceita")
        if market.get("symbol") != "BTC/USDT" or market.get("spot") is not True:
            raise ValueError("Snapshot deve corresponder a BTC/USDT spot")
        for field in ("price", "amount"):
            precision = market.get("precision", {}).get(field)
            if not isinstance(precision, (float, int)) or precision <= 0:
                raise ValueError("Filtros reais de precisão são obrigatórios")
        super().__init__(config, validate=False, load_leverage_tiers=False)
        self._offline_initialized = True
        self._markets = {"BTC/USDT": market}
        for api in (self._api, self._api_async):
            api.set_markets(self._markets)

    def reload_markets(self, *args, **kwargs):
        raise RuntimeError("Carregamento remoto de mercados proibido no adaptador offline")

    def close(self):
        # O destrutor do Freqtrade também chama close após uma construção recusada.
        if getattr(self, "_offline_initialized", False):
            super().close()

    def create_order(self, *args, **kwargs):
        raise RuntimeError("Ordens de exchange proibidas no adaptador offline")

    def get_fee(self, *args, **kwargs):
        raise RuntimeError("Consulta remota de taxas proibida; fee deve estar explícita")


def main():
    require_legacy_research_allowed(["backtesting"])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", choices=list(PERIODS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_config = json.loads((ROOT / "user_data/config.json").read_text())
    validate_config(source_config, os.environ)
    output = args.output_dir.resolve()
    allowed = (ROOT / "user_data/backtest_results").resolve()
    if output != allowed and not output.is_relative_to(allowed):
        parser.error("Resultados devem ficar em user_data/backtest_results")
    output.mkdir(parents=True, exist_ok=True)
    manifest = inspect_data(ROOT / "user_data/data/binance/BTC_USDT-1h.feather")
    if "provenance" not in manifest or not manifest["provenance"].get("archives"):
        raise ValueError("Backtest offline exige proveniência dos arquivos oficiais verificados")
    cli = ["backtesting", "--config", str(ROOT / "user_data/config.json"),
           "--strategy", "SmaRsiStrategy", "--timeframe", "1h",
           "--timerange", "-".join(PERIODS[args.period]), "--fee", "0.001",
           "--cache", "none", "--export", "trades", "--backtest-directory", str(output)]
    config = setup_optimize_configuration(Arguments(cli).get_parsed_arg(), RunMode.BACKTEST)
    config["backtest_notes"] = MODEL["limitation"]
    snapshot_path = ROOT / "user_data/data/binance/market_snapshot.json"
    snapshot_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    if snapshot_sha != manifest["provenance"].get("market_snapshot_sha256"):
        raise ValueError("Snapshot de mercados diverge da proveniência do dataset")
    market, snapshot = load_market_snapshot(snapshot_path)
    model = {**MODEL, "market_snapshot_sha256": snapshot_sha,
             "metadata_fetched_at": snapshot["fetched_at"],
             "price_precision": market["precision"]["price"], "amount_precision": market["precision"]["amount"],
             "limits": market["limits"]}
    (output / "research_model.json").write_text(json.dumps(model, indent=2) + "\n")
    (output / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("OFFLINE RESEARCH: OHLCV e metadados reais da Binance; execução sem rede.", flush=True)
    exchange = OfflineResearchBinance(config, market)
    try:
        backtesting = Backtesting(config, exchange=exchange)
        backtesting.start()
    finally:
        exchange.close()
        Backtesting.cleanup()


if __name__ == "__main__":
    main()
