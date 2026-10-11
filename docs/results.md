# Relatório de pesquisa — TradeBot AI

Execução `20261011T175632005777Z`. Tempos e períodos deste relatório em UTC.

Dados públicos Binance spot, BTC/USDT, 1h; carteira fictícia independente de
1000 USDT em cada período. Estratégia SMA20/50 + RSI14, stop-loss de 5%.
Taxa assumida de 0,1% por lado; não é consulta à tarifa de uma conta real.

## Evidências de execução

| Etapa | Resultado | Código | Log |
|---|---|---:|---|
| docker-info | PASSOU | 0 | `user_data/research/20261011T175632005777Z/docker-info.log` |
| compose-config | PASSOU | 0 | `user_data/research/20261011T175632005777Z/compose-config.log` |
| version | PASSOU | 0 | `user_data/research/20261011T175632005777Z/version.log` |
| tests | PASSOU | 0 | `user_data/research/20261011T175632005777Z/tests.log` |
| strategies | PASSOU | 0 | `user_data/research/20261011T175632005777Z/strategies.log` |
| download | FALHOU | 2 | `user_data/research/20261011T175632005777Z/download.log` |
| archive-download | PASSOU | 0 | `user_data/research/20261011T175632005777Z/archive-download.log` |
| list-data | PASSOU | 0 | `user_data/research/20261011T175632005777Z/list-data.log` |
| validate-data | PASSOU | 0 | `user_data/research/20261011T175632005777Z/validate-data.log` |
| development | PASSOU | 0 | `user_data/research/20261011T175632005777Z/development.log` |
| validation | PASSOU | 0 | `user_data/research/20261011T175632005777Z/validation.log` |

Suíte desta execução: **41 testes**, resultado PASSOU.

## Resultados financeiros

| Métrica | Desenvolvimento | Validação |
|---|---:|---:|
| Período solicitado (fim exclusivo) | 20240101–20250101 | 20250101–20250701 |
| Situação | Backtest concluído | Backtest concluído |
| Período efetivo Freqtrade | 2024-01-01 00:00:00 – 2025-01-01 00:00:00 | 2025-01-01 00:00:00 – 2025-07-01 00:00:00 |
| Operações fechadas (inclui encerramento final) | 69 | 41 |
| Taxa assumida por lado | 0,1% | 0,1% |
| Lucro líquido (USDT) | -179.7782 | -122.1180 |
| Retorno líquido na carteira | -17.9778% | -12.2118% |
| Saldo final (USDT) | 820.2218 | 877.8820 |
| Taxas reconstruídas dos trades (USDT) | 111.9616 | 69.7307 |
| Drawdown máximo relativo da conta | 30.1170% | 22.1763% |
| Drawdown máximo absoluto (USDT) | 301.1696 | 228.2081 |
| Market change Freqtrade (close/close, bruto) | 122.2499% | 13.7455% |
| Buy-and-hold líquido da carteira (99% investido) | 119.6550% | 14.1306% |
| Buy-and-hold lucro líquido (USDT) | 1196.5496 | 141.3061 |
| Candles ativos validados | 8784 | 4344 |
| Profit factor líquido | 0.7655 | 0.7346 |
| Taxa de acerto | 37.6812% | 39.0244% |
| Exposição temporal | 22.3474% | 29.1667% |
| Drawdown máximo da carteira marcada a mercado | 33.6037% | 22.6319% |

## Integridade e método

- SHA-256 `user_data/config.json`: `8b34d550c3368f42bf7d638b043574887575e2576f40814c41480b81900ee904`.
- SHA-256 `user_data/strategies/SmaRsiStrategy.py`: `b37becb4d3b98242053eaa699c4b744f3f3228865125c0330655b29efea073e6`.
- SHA-256 `docker-compose.yml`: `839513c69111e9ad0dd8bd8f669ecc21939ed02c2102a8a01551499ac8914cdb`.
- SHA-256 `scripts/download_archive.py`: `56febd00950b122f92c003297b8091c0b4a4df1fc3f3a8d75043da8bcab0c515`.
- SHA-256 `scripts/offline_backtest.py`: `a6927658d0c3e58dd51fd06c29a9828a93bc5339cc211a6de9bcc3cc8dd5125d`.
- SHA-256 `docker-compose.offline.yml`: `9c535f9c7a0c155e2ea6615aa380ec000ea5e9b7e3cc1e564cc7f189b28c5a6a`.
- SHA-256 `docker-compose.cloud.yml`: `bcf13419d8532362c7f1f3af23edd3b3e1095370b7e634c866e96fffd8011baa`.
- OHLCV: `user_data/data/binance/BTC_USDT-1h.feather`; SHA-256 `7c5aab75eb55620dda2518351ab9a857f5500b42cb15bc16e6d0632c74265321`.
- Cobertura total: 2023-12-01 00:00:00+00:00 a 2025-07-01 23:00:00+00:00; 13896 candles.
- Origem única: Binance Vision official monthly spot klines; BTCUSDT; 1h; binance BTC/USDT 1h.
- Desenvolvimento: 2024; validação: primeiro semestre de 2025, sem sobreposição.
- 200 candles anteriores são apenas warm-up; cada backtest reinicia a carteira e posições.
- Parâmetros fixados antes dos testes; sem hyperopt ou seleção usando a validação.
- Taxas reconstruídas dos fills exportados: amount × safe_price × fee de cada lado; já incluídas no lucro líquido.
- Profit factor = lucros líquidos positivos / módulo dos negativos; taxa de acerto = trades positivos / total.
- Exposição temporal = duração total das posições / duração UTC do período; uma posição no máximo.
- Buy-and-hold: compra no primeiro open e venda no último close do período, taxa de
  0,1% nos dois lados, 99% do capital incluindo custo de compra e 1% em caixa.
- Market change do Freqtrade usa primeiro/último close, sem taxas, e difere desse benchmark.
- Drawdown é o indicador da conta exportado pelo Freqtrade; não equivale necessariamente
  ao drawdown intrabar marcado a mercado. Custos de spread, slippage e impacto não modelados.
- Os testes causais por prefixos são evidência básica, não substituem a análise completa de lookahead.
- Backtest não estabelece lucratividade futura. Nenhuma ordem real foi enviada.

- Modo offline: snapshot real dos filtros atuais Binance/CCXT; filtros históricos não disponíveis.
- Motor nativo Freqtrade em contêiner com network_mode=none e taxa explícita; OHLCV real, sem acesso à exchange.

## Comandos desta execução

### docker-info

```sh
docker info --format '{{.ServerVersion}}'
```

### compose-config

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml config --quiet
```

### version

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --name tradebot-ai-20261011t175632005777z-version freqtrade --version
```

### tests

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml -f docker-compose.offline.yml run --rm --name tradebot-ai-20261011t175632005777z-tests freqtrade test
```

### strategies

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --name tradebot-ai-20261011t175632005777z-strategies freqtrade list-strategies
```

### download

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --name tradebot-ai-20261011t175632005777z-download freqtrade download-data
```

Erro observado:

```text
  File "/freqtrade/freqtrade/exchange/common.py", line 194, in wrapper
    return wrapper(*args, **kwargs)
  File "/freqtrade/freqtrade/exchange/common.py", line 194, in wrapper
    return wrapper(*args, **kwargs)
  File "/freqtrade/freqtrade/exchange/common.py", line 194, in wrapper
    return wrapper(*args, **kwargs)
  File "/freqtrade/freqtrade/exchange/common.py", line 182, in wrapper
    return f(*args, **kwargs)
  File "/freqtrade/freqtrade/exchange/exchange.py", line 747, in _load_async_markets
    markets = self.loop.run_until_complete(self._api_reload_markets(reload=reload))
  File "/usr/local/lib/python3.14/asyncio/base_events.py", line 720, in run_until_complete
    return future.result()
           ~~~~~~~~~~~~~^^
  File "/freqtrade/freqtrade/exchange/exchange.py", line 738, in _api_reload_markets
    raise TemporaryError(
        f"Error in reload_markets due to {e.__class__.__name__}. Message: {e}"
    ) from e
freqtrade.exceptions.TemporaryError: Error in reload_markets due to ExchangeNotAvailable. Message: binance GET https://api.binance.com/api/v3/exchangeInfo 451 Unknown {
  "code": 0,
  "msg": "Service unavailable from a restricted location according to 'b. Eligibility' in https://www.binance.com/en/terms. Please contact customer service if you believe you received this message in
error."
}
2026-10-11 17:57:16,518 - freqtrade - ERROR - Markets were not loaded.

```

### archive-download

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --name tradebot-ai-20261011t175632005777z-archive-download freqtrade download-archive
```

### list-data

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --name tradebot-ai-20261011t175632005777z-list-data freqtrade list-data
```

### validate-data

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --name tradebot-ai-20261011t175632005777z-validate-data freqtrade validate-data
```

### development

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml -f docker-compose.offline.yml run --rm --name tradebot-ai-20261011t175632005777z-development freqtrade backtesting --period development --output-dir /freqtrade/user_data/backtest_results/20261011T175632005777Z/development --offline
```

### validation

```sh
docker compose -f docker-compose.yml -f docker-compose.cloud.yml -f docker-compose.offline.yml run --rm --name tradebot-ai-20261011t175632005777z-validation freqtrade backtesting --period validation --output-dir /freqtrade/user_data/backtest_results/20261011T175632005777Z/validation --offline
```

## Próximo passo

Revisar o comportamento e os riscos no período de desenvolvimento. A validação já foi observada: qualquer ajuste posterior exige reservar um novo período não usado.
