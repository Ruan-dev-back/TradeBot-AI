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

## Mercado ao vivo: simulação contínua (nova branch)
Um serviço **separado** permite observar preços atuais de BTC/USDT, ETH/USDT e
SOL/USDT em uma exchange, simulando entradas e saídas automaticamente quando
estiver conectado. Nunca envia ordens reais: `dry_run=true`, `--dry-run`,
sem chaves e com 25 USDT fictícios por posição.

**A estratégia atual teve prejuízo no backtest e não foi validada para operar dinheiro real.**
O serviço não foi implantado nem iniciado automaticamente.

Veja [o roteiro de execução ao vivo](docs/realtime-roadmap.md) antes de
ativá-lo manualmente. O Compose de pesquisa permanece independente.
