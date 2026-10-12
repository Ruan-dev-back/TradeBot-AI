# TradeBot AI

Pesquisa quantitativa e operador de **paper trading com Freqtrade via Docker Compose**.
Dados públicos spot em 1h: pesquisa Binance BTC/USDT de 2024 e simulação atual
OKX/Kraken de BTC/USDT, ETH/USDT e SOL/USDT. Não executa trading real,
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
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm freqtrade test
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
O Compose de pesquisa não expõe portas nem inicia um bot: seu comando padrão é um backtest.
A entrada de pesquisa só aceita pesquisa e testes; `trade` e argumentos de
configuração alternativos são recusados. Overrides `FREQTRADE__*` também são
recusados. Não forneça credenciais nem substitua a entrada por comandos de trading.
Essas proteções não impedem alguém de editar o projeto ou invocar Docker diretamente.

Base oficial e decisões de versão em [docs/sources.md](docs/sources.md).
O diagnóstico de rede e a solução de aquisição nesta nuvem estão em
[docs/environment-status.md](docs/environment-status.md).
O histórico e a justificativa do stop-loss de 5% estão em
[docs/stoploss-review.md](docs/stoploss-review.md); nenhum parâmetro foi otimizado.

## Mercado atual: paper trading
O serviço Kraken em `docker-compose.paper.yml` recebe candles atuais de
BTC/USDT, ETH/USDT e SOL/USDT e pode simular ordens automaticamente quando houver
sinais válidos. Usa Freqtrade nativo com `dry_run=true`, carteira fictícia de
1000 USDT, uma posição e stake de até25 USDT, limitada também pelo teto10% e
orçamento nominal0,5% com custos. Não há credenciais privadas nem ordens reais.

A estratégia de paper é uma cópia dos sinais da baseline que perdeu dinheiro em
Binance BTC/USDT. Esses resultados não são resultados Kraken; não há comprovação
de lucratividade da simulação. A baseline e as evidências históricas permanecem
congeladas. [Relatório da integração e dos testes](docs/paper-report.md),
[operação e comandos](docs/realtime-roadmap.md) e
[framework de desenvolvimento 2024](docs/development-framework.md).

O serviço foi validado nesta máquina, com dados reais e reinicialização. Isso não
constitui deploy ou monitoramento 24/7. Processos do ambiente de desenvolvimento
não têm garantia de sobreviver à publicação ou restauração do ambiente.

## OKX e desenvolvimento concluído nesta etapa

O perfil separado `docker-compose.okx.yml` usa `OkxPaperStrategy`, banco/carteira
próprios e dados públicos oficiais da OKX. O modo demo autenticado da exchange
não é utilizado: ordens são simuladas localmente pelo Freqtrade. Kraken permanece
como alternativa manual, sem migração automática de posições. Os dois perfis
mantêm as mesmas proteções; monitoram bid/ask a cada 20s e calculam sinais em
candles fechados de 1h. Acesso público não comprova elegibilidade de uma conta.

[Integração e evidências](docs/okx-integration-report.md),
[comandos seguros](docs/okx-commands.md),
[resultados D1–D3 de 2024](docs/research2024-results.md) e
[plano VPS e custos](docs/vps-plan.md).
Nenhum candidato passou todos os gates; nenhum foi promovido e ML continua
bloqueado. O holdout reservado permanece fechado. Os relatórios históricos
permanecem preservados. Não houve contratação ou deploy de VPS.

## Observação prospectiva OKX

CLI independente, somente leitura do operador:

```sh
python3 scripts/paper_monitor.py snapshot --exchange okx
python3 scripts/paper_monitor.py watch --exchange okx
python3 scripts/paper_monitor.py health --exchange okx
python3 scripts/paper_monitor.py report --exchange okx
```

Diário UTC persistente, alertas locais raised/recovered, hashes e janela fixa de
168h, sem reutilizar warmup como trades. O monitor mostra saldo/P&L/fees, sinais,
motivos de recusa, quotes e posições nativas; health exige dados/risco/SQLite,
além da evidência do processo. Nenhum monitor local comprova disponibilidade do
host inteiro. [Protocolo](docs/prospective-protocol.md),
[operação Linux/WSL2](docs/prospective-operation.md),
[relatório real desta etapa](docs/prospective-report.md) e
[pesquisa futura com controle de múltiplos testes](docs/future-research-protocol.md).
Sete dias só serão declarados depois da janela e das evidências suficientes.

## Host persistente: Windows/WSL2 e Linux

Ferramentas de operação adicionais, sem alterar os arquivos congelados:

```sh
python3 scripts/paper_host.py preflight
python3 scripts/paper_host.py verify-recovery
python3 scripts/paper_host.py start
python3 scripts/paper_host.py status
```

Start exige uma janela já restaurada/autorizada. Backup completo inclui quatro
bancos e código Git pelo commit; recuperação não sobrescreve estados, não muda
T0/T1 e não fabrica saúde atual. Windows usa dispatcher PowerShell para WSL2;
Linux tem templates renderizáveis de systemd, sem instalação automática.
[Instalação e comandos](docs/host-installation.md),
[backup/migração/recuperação](docs/host-recovery.md) e
[monitor externo e alertas humanos](docs/external-monitor-design.md).
Não houve deploy em PC/VPS nem cadastro de monitor/serviço externo.
Veja [verificações reais e pendências](docs/host-report.md) e
[checklist de implantação](docs/host-checklist.md).
