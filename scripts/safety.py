"""Validação sem dependências da configuração fixa de pesquisa."""

PERIODS = {
    "development": ("20240101", "20250101"),
    "validation": ("20250101", "20250701"),
}
DOWNLOAD_RANGE = "20231201-20250702"  # Candle real de fronteira para encerrar a validação exatamente em 01/07.


def validate_config(config, environ):
    expected = {
        "dry_run": True, "trading_mode": "spot", "margin_mode": "",
        "timeframe": "1h", "dry_run_wallet": 1000, "max_open_trades": 1,
        "stake_currency": "USDT", "stake_amount": "unlimited",
        "tradable_balance_ratio": 0.99, "fee": 0.001, "force_entry_enable": False,
    }
    for field, value in expected.items():
        actual = config.get(field)
        if type(actual) is not type(value) or actual != value:
            raise ValueError(f"Configuração de pesquisa inválida: {field}")
    if any(name.upper().startswith("FREQTRADE__") for name in environ):
        raise ValueError("Overrides FREQTRADE__* não são aceitos neste MVP")
    exchange = config.get("exchange", {})
    if exchange.get("name") != "binance" or exchange.get("pair_whitelist") != ["BTC/USDT"]:
        raise ValueError("Somente Binance BTC/USDT é permitido")
    for name in ("key", "api_key", "apiKey", "secret", "password", "uid", "walletAddress", "privateKey"):
        if exchange.get(name):
            raise ValueError("Credenciais não são permitidas")
    for name in ("ccxt_config", "ccxt_async_config"):
        ccxt_expected = {"enableRateLimit": True, "options": {"fetchMarkets": {"types": ["spot"]}}}
        if name == "ccxt_async_config":
            ccxt_expected["aiohttp_trust_env"] = True
            ccxt_expected["options"]["include_OS_certificates"] = True
        else:
            ccxt_expected["requests_trust_env"] = True
        if exchange.get(name) != ccxt_expected:
            raise ValueError("Overrides CCXT não são permitidos")
    if config.get("pairlists") != [{"method": "StaticPairList"}]:
        raise ValueError("Pairlist deve ser estática")
    if config.get("api_server", {}).get("enabled", False) is not False:
        raise ValueError("API deve permanecer desativada")
    if config.get("telegram", {}).get("enabled") is not False:
        raise ValueError("Telegram deve permanecer desativado")
    allowed = set(expected) | {
        "$schema", "bot_name", "cancel_open_orders_on_exit", "unfilledtimeout",
        "entry_pricing", "exit_pricing", "exchange", "pairlists", "telegram", "api_server",
    }
    if set(config) - allowed:
        raise ValueError("Campos adicionais de configuração não são aceitos")
