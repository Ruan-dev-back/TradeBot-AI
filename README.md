# TradeBot AI

MVP de pesquisa quantitativa com **Freqtrade via Docker Compose**. Apenas dados
públicos, testes e backtesting de BTC/USDT spot em 1h. Não executa trading real,
não usa chaves de API e não inclui ML, LLM, painel web ou deploy.

## Requisitos

Docker com daemon acessível e plugin Docker Compose v2. Não há dependências
Python para instalar no host: os indicadores e testes da estratégia usam a imagem
oficial do Freqtrade, fixada por digest em `docker-compose.yml`.

```sh
docker --version
docker compose version
docker info
docker compose config --quiet
docker compose pull
docker compose run --rm freqtrade --version
docker compose run --rm freqtrade test
```

## Pesquisa reproduzível

A baseline publicada permanece em `docs/results.md` e `docs/evidence/`. O fluxo
atual é a auditoria de risco, sem aquisição de novos candles:

```sh
python3 scripts/run_audit.py
```

Veja o [relatório de risco](docs/risk-report.md) e o
[plano de experimento](docs/experiment-plan.md). O holdout UTC de
2025-07-01 a 2026-07-01 está reservado em `docs/holdout-lock.json`; janeiro–junho/2025
já é observado. Sizing menor e custos são cenários retrospectivos, sem mudar a
estratégia/configuração original nem representar validação independente.

O runner anterior e seus comandos de download/backtest estão bloqueados neste
estágio para preservar a reserva e o relatório publicado. As instruções abaixo
registram o fluxo **histórico**, executado antes dessa reserva; não use para
abrir o holdout. Não há comando de unlock nesta etapa.

Execute a partir da raiz deste checkout:

```sh
python3 scripts/run_research.py
```

O script registra comandos, saídas e códigos de retorno, testa a estratégia,
baixa candles públicos, verifica cobertura e executa dois backtests independentes.
Se a API principal estiver bloqueada, usa arquivos oficiais Binance Vision com
checksums e metadados reais do endpoint público `data-api.binance.vision`.
O fallback executa o motor nativo sem rede, usando esse snapshot de filtros atuais.
Gera `docs/results.md` e artefatos ignorados em `user_data/research/` e
`user_data/backtest_results/`. Falhas são registradas como falhas; nunca como
resultado financeiro zero. O processo retorna código diferente de zero se houver
etapa obrigatória malsucedida. Cada execução tem um diretório próprio.
Evidências compartilháveis, incluindo trades e logs integrais, ficam em `docs/evidence/`.
Uma falha da API preservada como diagnóstico não torna o fallback verificado uma falha.

Para escolher diretamente a fonte de arquivos oficiais:

```sh
python3 scripts/run_research.py --source archive
python3 scripts/network_diagnostics.py
```

Comandos individuais:

```sh
docker compose run --rm freqtrade download-archive
docker compose run --rm freqtrade list-data
docker compose run --rm freqtrade validate-data
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade backtesting --offline --period development
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade backtesting --offline --period validation
```

Não ajuste a estratégia usando os resultados de validação. Veja o
[protocolo de pesquisa](docs/research-protocol.md), os
[comandos e limitações](docs/commands.md) e o [relatório observado](docs/results.md).

## Estratégia inicial

`SmaRsiStrategy`: entrada long quando SMA20 cruza acima de SMA50 e
`50 <= RSI14 < 70`, com volume positivo. Saída quando SMA20 cruza abaixo de SMA50
ou RSI14 atinge 75, com volume positivo. Stop-loss fixo de 5%, sem trailing stop,
sem ROI automático, sem short, sem alavancagem e sem aumento de posição.
Os sinais usam somente candles fechados; no backtest, execução normalmente na
abertura do candle seguinte, segundo o modelo do Freqtrade.

Capital fictício: 1000 USDT; até uma posição; 99% do saldo disponível;
taxa simulada: 0,1% na entrada e na saída. Não há alegação de lucratividade.

## Segurança

`dry_run=true`, mercado `spot`, credenciais ausentes, API e Telegram desativados.
O Compose não expõe portas nem inicia um bot: seu comando padrão é um backtest.
A entrada adaptada só aceita pesquisa e testes; `trade` e argumentos de
configuração alternativos são recusados. Overrides `FREQTRADE__*` também são
recusados. Não forneça credenciais nem substitua a entrada por comandos de trading.
Essas proteções não impedem alguém de editar o projeto ou invocar Docker diretamente.

Base oficial e decisões de versão em [docs/sources.md](docs/sources.md).
O diagnóstico de rede e a solução de aquisição nesta nuvem estão em
[docs/environment-status.md](docs/environment-status.md).
O histórico e a justificativa do stop-loss de 5% estão em
[docs/stoploss-review.md](docs/stoploss-review.md); nenhum parâmetro foi otimizado.
