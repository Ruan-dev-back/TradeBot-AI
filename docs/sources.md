# Fontes oficiais consultadas

Consulta em 2026-10-11, antes de escolher os comandos e a configuração.
O site `www.freqtrade.io/en/stable/` retornou HTTP 403 neste ambiente. Foi usada
a documentação Markdown da branch **stable do repositório oficial**, obtida via
HTTPS com verificação TLS. Referência observada da branch:
`1f394eaebc2f46a83d26971388628707802f8602`.

| Tema | Documentação estável | Fonte oficial consultada |
|---|---|---|
| Docker Compose | https://www.freqtrade.io/en/stable/docker_quickstart/ | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/docker_quickstart.md |
| Compose original | — | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docker-compose.yml |
| Configuração | https://www.freqtrade.io/en/stable/configuration/ | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/configuration.md |
| Download público | https://www.freqtrade.io/en/stable/data-download/ | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/data-download.md |
| Backtesting e taxas | https://www.freqtrade.io/en/stable/backtesting/ | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/backtesting.md |
| Estratégia interface v3 | https://www.freqtrade.io/en/stable/strategy-customization/ | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/strategy-customization.md |
| Callbacks | https://www.freqtrade.io/en/stable/strategy-callbacks/ | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/strategy-callbacks.md |
| Exemplo Binance | — | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/config_examples/config_binance.example.json |
| Estratégia de referência | — | https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/freqtrade/templates/sample_strategy.py |

## Versões verificadas

- Docker 28.4.0; Docker Compose v2.40.3; daemon respondeu.
- Imagem oficial `freqtradeorg/freqtrade:stable`, Freqtrade 2026.9.
- Digest fixado: `sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199`.
- Dentro da imagem: Python 3.14.7, CCXT 4.5.84.
- Host: Python 3.12.14, usado apenas para o runner sem dependências externas.

O digest identifica o artefato executado; a branch stable é móvel. Os exemplos
foram adaptados para pesquisa: comando padrão backtesting, sem restart permanente,
sem portas, sem credenciais, sem Telegram/API e com estratégia própria simples.

Opções de conectividade foram verificadas também no código instalado do CCXT
4.5.84 dentro dessa imagem: `binance.fetch_markets` aceita
`options.fetchMarkets.types=["spot"]`; clientes sync/async aceitam
`requests_trust_env`/`aiohttp_trust_env`; `async_support.Exchange.open` usa
`include_OS_certificates` para incluir a CA gerenciada mantendo TLS verificado.

## Fontes da aquisição desbloqueada

- Arquivos oficiais Binance Public Data e documentação dos checksums e mudança
  de ms para µs em janeiro/2025: https://github.com/binance/binance-public-data
- Base dos ZIPs spot/1h/BTCUSDT: https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/
- Documentação oficial do endpoint exclusivo de dados públicos:
  https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- Metadados públicos reais usados:
  https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT
- A documentação REST oficial recomenda esse endpoint para market data:
  https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md

O código instalado do Freqtrade 2026.9 foi inspecionado para verificar o construtor
`Backtesting(config, exchange=...)`, a configuração pelo parser nativo
`freqtrade.commands.Arguments` e o export normal do motor. O adaptador fica no
projeto, sem modificar o Freqtrade ou substituir sua lógica de indicadores/trades.
Metadados atuais são normalizados pelo mesmo CCXT 4.5.84. As precisões e limites
efetivamente retornados, o instante da coleta e o JSON completo estão no snapshot
de evidência; não foi usado fixture para cálculos financeiros.

## Auditoria temporal e custos

Documentação oficial stable consultada em 2026-10-11, antes de executar as análises:

- [Lookahead-analysis](https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/lookahead-analysis.md):
  encadeamento de backtests, overrides diagnósticos, quantidade mínima e force_exit.
- [Recursive-analysis](https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/docs/recursive-analysis.md):
  referência longa, startup variável, comparação da última linha e limitação sobre sinais.
- Código da mesma imagem Freqtrade2026.9: classes `BaseAnalysis`, `LookaheadAnalysis`,
  `RecursiveAnalysis`, seus helpers, `StrategyResolver` e `Backtesting.load_bt_data`.
  `BaseAnalysis.exchange` permite fornecer o adaptador offline sem alterar o motor.

O CI remoto foi conferido pela página pública do run com SHA e status explícitos,
porque `api.github.com` retornou CONNECT403 do proxy. Não foram requisitadas chaves
de GitHub/Binance. Cenários de spread/slippage são hipóteses documentadas, não dados
de order book extraídos dos candles.

## Paper trading e callbacks de risco

Documentação oficial stable consultada antes da implementação, no snapshot já
fixado `1f394eaebc2f46a83d26971388628707802f8602`:

- [Dry-run, carteira, SQLite, mínimos e logs](https://raw.githubusercontent.com/freqtrade/freqtrade/1f394eaebc2f46a83d26971388628707802f8602/docs/configuration.md).
- [Callbacks de stake e confirmação](https://raw.githubusercontent.com/freqtrade/freqtrade/1f394eaebc2f46a83d26971388628707802f8602/docs/strategy-callbacks.md): stake é ajustado aos mínimos; exceções podem retornar ao stake proposto e confirmação padrão permissiva. Os callbacks do paper capturam falhas e recusam a entrada.
- [Ciclo do bot](https://raw.githubusercontent.com/freqtrade/freqtrade/1f394eaebc2f46a83d26971388628707802f8602/docs/bot-basics.md).
- Código instalado Freqtrade2026.9 / CCXT4.5.84: `FreqtradeBot.create_trade`, `execute_entry`, `Exchange.create_order`, `create_dry_run_order`, `fetch_dry_run_order`, `Wallets._update_dry` e `DataProvider`. A integração testa esse motor, sem alterar a biblioteca.
- Kraken REST pública: `https://api.kraken.com/0/public/Time`, `Assets`, `AssetPairs`, `OHLC` e `Depth`; credenciais privadas não foram utilizadas.

O CA gerenciado é carregado via `cafile` no cliente async. O cliente síncrono usa
`requests_trust_env=true`; `trust_env=true` isoladamente não alterava a Session
na versão CCXT fixada. O acesso atual foi comprovado por requisições e pelo
serviço nativo, sem desabilitar TLS ou mudar os endpoints.

## Fontes adicionais da integração OKX

Esta continuação consultou a documentação estável do Freqtrade: exchanges,
configuration, strategy-callbacks e docker_quickstart no branch stable de
`freqtrade/freqtrade`, além do adaptador OKX da imagem fixada (2026.9/CCXT 4.5.84).
O bot nativo spot/dry-run funcionou; demo autenticado não foi executado.

- OKX API oficial: https://www.okx.com/docs-v5/en/ ; time/instruments spot,
  market ticker/books/candles. Demo requer chaves/passphrase próprias e
  `x-simulated-trading: 1`; fee de conta é endpoint privado, não consultado.
- Fee pública: https://www.okx.com/fees ; tabela padrão/contexto registrado,
  sem assumir tarifa autenticada ou substituir a fee paper de 40 bps/lado.
- Fontes de hospedagem e hashes das consultas: [public-sources.json](okx/evidence/public-sources.json)
  e [plano VPS](vps-plan.md). Cotação é snapshot, sem contrato/deploy.

O conteúdo histórico acima permanece como referência das etapas anteriores.
