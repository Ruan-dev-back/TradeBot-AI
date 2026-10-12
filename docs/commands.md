# Comandos e operação local

## Auditoria atual, holdout fechado

```sh
python3 scripts/run_audit.py
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm freqtrade test
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm freqtrade audit-bias
```

Sem aquisição, credenciais, serviços ou operações reais. O override de auditoria
monta documentação, estratégia e dados de origem como somente leitura e desliga
a rede. Os resultados novos ficam em `docs/audit/evidence/` e `docs/risk-report.md`;
as evidências e o relatório publicados permanecem congelados por hash.
`python3 scripts/run_audit.py --reuse-bias` reusa somente artefato temporal com
hashes compatíveis; a suíte e a verificação de CI continuam sendo executadas.

O runner histórico e seus comandos de aquisição/validação/backtest são recusados
enquanto a reserva está ativa, inclusive no Compose base sem docs montado. Os
comandos abaixo documentam a execução anterior à reserva, não são instruções
para abrir o holdout. Um novo protocolo deve ser congelado antes de ler a janela
2025-07-01–2026-07-01. Consulte [experiment-plan.md](experiment-plan.md).

Execute todos os comandos na raiz do checkout. Esta tarefa já está isolada;
não é necessário criar worktree. Os arquivos de dados e exports persistem no bind
mount `user_data`; contêineres de pesquisa são descartáveis, sem serviços de trading.

## Runtime

```sh
docker --version
docker compose version
docker info
docker compose config --quiet
docker compose pull
docker compose run --rm freqtrade --version
```

Se Docker ou Compose não estiver disponível, ou o daemon não responder, pare
o fluxo Docker e registre o erro. Não há instalação automática de Docker, Compose,
pacotes de sistema ou dependências no host.

## Entrada de pesquisa adaptada

O Compose oficial usa `freqtrade trade` como padrão. Aqui isso foi substituído
por uma entrada Python com lista restrita de comandos. Flags do Freqtrade não
podem ser passadas livremente: o wrapper define configuração, par, timeframe,
períodos, estratégia, taxas e export de forma fixa.

| Comando aceito após `docker compose run --rm freqtrade` | Ação interna |
|---|---|
| `--version` | `freqtrade --version` |
| `test` | `python -m unittest discover -s /freqtrade/tests -v` |
| `list-strategies` | `freqtrade list-strategies --config /freqtrade/user_data/config.json` |
| `download-data` | Download público 20231201-20250702, BTC/USDT, 1h, spot, feather |
| `download-archive` | ZIPs mensais oficiais, checksums e metadados reais BTCUSDT; conversão Feather |
| `list-data` | Lista datasets e seus intervalos |
| `validate-data` | Confere OHLCV e escreve manifesto de integridade |
| `backtesting --period development` | Backtest 20240101-20250101 |
| `backtesting --period validation` | Backtest 20250101-20250701 |

O wrapper traduz download para os argumentos estáveis oficiais:

```text
freqtrade download-data --config /freqtrade/user_data/config.json
  --pairs BTC/USDT --timeframes 1h --trading-mode spot
  --timerange 20231201-20250702 --data-format-ohlcv feather
```

E backtesting para:

```text
freqtrade backtesting --config /freqtrade/user_data/config.json
  --strategy SmaRsiStrategy --timeframe 1h --timerange <intervalo-fixo>
  --fee 0.001 --cache none --export trades --backtest-directory <diretório>
```

Não há comando de trading. `docker compose up` executaria apenas o backtest padrão;
prefira `run --rm` ou o runner, que preserva logs, separa resultados e confere exports.
API server foi omitido para manter o padrão desativado sem criar credenciais JWT.
Telegram está desativado, com token e chat_id vazios exigidos pelo schema.

## Fluxo e evidências

```sh
python3 scripts/run_research.py
```

O runner usa apenas a biblioteca padrão no host. Ele imprime progresso e salva
as saídas integrais em `user_data/research/<run-id>/`. Os contêineres têm nomes
únicos; no timeout o runner remove somente o contêiner que criou naquela etapa.
Backtests completos ficam em `user_data/backtest_results/<run-id>/<period>/`.
São gerados `commands.json`, manifesto de dados e uma cópia do relatório por run;
`docs/results.md` representa a execução mais recente. Artefatos locais são ignorados
pelo Git; o relatório markdown e o código podem ser versionados por decisão humana.

Para executar apenas as verificações de segurança no host:

```sh
python3 -m unittest discover -s tests -p test_safety.py -v
```

As demais verificações precisam de pandas, NumPy, TA-Lib, technical e Freqtrade:
use `docker compose run --rm freqtrade test`, sem instalar nada adicional.

## Aquisição alternativa oficial e backtest sem rede

```sh
python3 scripts/network_diagnostics.py
python3 scripts/run_research.py --source archive
```

O modo padrão `auto` tenta a API configurada e, se falhar, preserva o erro e usa os
arquivos oficiais. A etapa de API falha permanece no relatório como diagnóstico,
mas o runner retorna zero se todos os requisitos do fallback e ambos os exports
forem verificados. `--source api` desabilita fallback e falha se a API não funcionar.
Cada execução atualiza evidências financeiras para evitar confusão com exports antigos.

Para executar manualmente, depois do download e da validação:

```sh
docker compose run --rm freqtrade download-archive
docker compose run --rm freqtrade validate-data
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade backtesting --offline --period development
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade backtesting --offline --period validation
```

Na nuvem com proxy, acrescente `-f docker-compose.cloud.yml` para os comandos de
aquisição (ou use o runner que detecta isso). A execução offline necessita apenas
dos arquivos já adquiridos, e seu override define `network_mode: none`.
Os metadados atuais vêm exclusivamente de `data-api.binance.vision` e são
verificados contra o hash registrado; o adaptador passa os filtros reais ao motor
nativo Freqtrade. Não há comandos de ordens nem serviço de trading.

`docs/evidence/` contém logs integrais, comandos, manifesto, snapshot público e
os resumos nativos com todos os trades. ZIPs grandes e dados brutos ficam em
`user_data/`, ignorados; SHA-256 de cada export é registrado nos JSONs de evidência.

## Rede e diagnóstico

Neste ambiente de nuvem, o host disponibiliza um proxy HTTPS e uma CA gerenciados.
O runner detecta `HTTPS_PROXY` junto ao bundle Linux `/etc/ssl/certs/ca-certificates.crt`
e usa também `docker-compose.cloud.yml`. Esse override encaminha somente nomes
de variáveis de proxy e monta o bundle de CA como somente leitura. Valores não
são escritos em arquivos. TLS continua sendo verificado. Para comandos individuais
neste mesmo host Linux, use antes:

```sh
export COMPOSE_FILE=docker-compose.yml:docker-compose.cloud.yml
docker compose config --quiet
docker compose run --rm freqtrade download-data
```

Em Docker Desktop ou hosts sem esse proxy, use somente `docker-compose.yml`.
Não imprima `docker compose config` completo quando houver proxy autenticado;
use `--quiet`. O CCXT async usa `aiohttp_trust_env=true` e o cliente síncrono
usa `requests_trust_env=true` para respeitar o proxy;
o cliente async inclui as CAs do sistema com `include_OS_certificates=true`,
respeitando o bundle montado via `SSL_CERT_FILE`, sem desativar a verificação TLS;
as consultas de mercados dos dois clientes são limitadas a `fetchMarkets.types=[spot]`
para evitar chamadas desnecessárias a metadados de futuros.

Dados e metadados de mercado exigem HTTPS público para `api.binance.com` e, conforme
a rota utilizada pelo Freqtrade, `data.binance.vision`. O registry Docker e suas
rotas de distribuição são necessários para `docker compose pull`. Não há chaves
de exchange. Não altere Binance para outra exchange silenciosamente se houver
restrição geográfica ou de rede.

Um download pode falhar por timeout, DNS, proxy, TLS ou resposta geográfica 451.
Verifique o log real. Não desative verificação TLS e não adicione credenciais.
Se houver bloqueio, registre-o e repita a pesquisa após restabelecer acesso público.
O downloader pode retornar zero sem disponibilizar candles; a validação obrigatória
do dataset impede tratar isso como sucesso financeiro.

O rascunho inclui `api.binance.com`, `data.binance.vision` e `data-api.binance.vision`,
preservando os presets anteriores. Nesta máquina, os dois destinos Vision responderam
200; a API principal respondeu 451 da exchange, não 403 do proxy. Publicação de uma
nova versão do ambiente não foi executada pelo agente. Para persistir a configuração
em novas máquinas, revise, salve e publique pelas configurações do ambiente; isso
não faz deploy de um bot. Uma aprovação de rascunho não prova publicação.

Atualizar a imagem requer escolher e registrar um novo digest oficial e executar
novamente testes e backtests. Não use imagem de ML/plotting neste MVP.

## Paper Kraken e framework 2024

Os comandos atuais de conexão, inicialização, saúde, logs e restart estão em
[realtime-roadmap.md](realtime-roadmap.md). O serviço independente usa
`docker-compose.paper.yml`; o override `.paper.cloud.yml` mantém proxy/CA do host.
O endpoint público permitido adicional é `api.kraken.com`. O framework restrito
está em [development-framework.md](development-framework.md); não use os comandos
históricos bloqueados para executá-lo.

Suíte completa de pesquisa, risco, estratégia, SQLite e motor nativo sem rede:

```sh
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm freqtrade test
python3 scripts/check_ci.py --branch feat/realtime-paper-trading \
  --output user_data/research/paper-ci.json
```

O override de auditoria monta docs, estratégias, dados históricos, candidatos e
`docker-compose.paper.yml` somente para leitura. Essa última montagem preserva a
correção `1d3e143`; não substitua pelo Compose base sem os arquivos necessários.
O teste de CI identifica status e SHA exato, mesmo se a API GitHub estiver bloqueada.

A verificação de saúde `python3 scripts/paper_status.py` funciona com stdlib no
host, sem Freqtrade instalado. As operações e indicadores nativos usam somente a
imagem fixada. O relatório desta integração fica em `docs/paper-report.md`; as
evidências históricas e da auditoria anterior continuam nos caminhos originais.
