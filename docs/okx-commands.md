# Comandos OKX, Kraken e desenvolvimento fechado

Executar na raiz do checkout. Nenhum comando configura chaves, habilita modo real,
abre o holdout ou faz deploy. Dados privados e overrides `FREQTRADE__*` são
recusados. Docker e Compose já estão disponíveis; o setup não instala no host.

## Testes e configuração

```sh
sh scripts/setup_environment.sh
python3 scripts/ci_tests.py
docker compose -f docker-compose.okx.yml config --quiet
```

O primeiro comando valida JSON/Compose, obtém a imagem pelo digest e executa os
testes no container sem rede. O segundo captura erros para diagnóstico no CI.
Não instalar dependências científicas no Python do host.

## Preflight e operador OKX

Nesta nuvem o proxy gerenciado exige o overlay cloud e a CA do host somente
leitura. Não imprimir valores de proxy. Em VPS de acesso direto, omitir o overlay
cloud; não desabilitar TLS nem buscar outra região/endpoint para evitar recusas.

```sh
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml run --rm --entrypoint python okxpaper /freqtrade/scripts/check_okx.py --output /freqtrade/user_data/research/okx-market.json
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml up -d --wait --wait-timeout 90
python3 scripts/paper_status.py --exchange okx
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml logs --tail 100 --no-color okxpaper
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml restart okxpaper
python3 scripts/paper_status.py --exchange okx
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml stop okxpaper
```

O preflight consulta exclusivamente endpoints públicos oficiais. Se falhar,
investigar HTTP/TLS/proxy/clock, sem iniciar outra rota para contornar geobloqueio.
`up --wait` verifica liveness, não rentabilidade. Reinício preserva SQLite nativo,
risk.sqlite, peak/halt/cooldown/IDs, salvo corrupção/falha de disco. Nunca apagar
os bancos para reativar entradas. O engine.lock impede dois escritores por perfil.

Os snapshots de saúde distinguem bid/ask observado a cada 20s, preço do último
candle fechado, sinal/decisão candidata e contagem real de ordens/trades SQLite.
Sinal de warmup não é replayado como trade atual. Sinais são calculados em 1h,
somente candles fechados. Indicadores não são calculados em cada tick.

## Kraken alternativa manual

```sh
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml up -d --wait --wait-timeout 90
python3 scripts/paper_status.py --exchange kraken
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml logs --tail 100 --no-color papertrade
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml stop papertrade
```

Em VPS sem proxy, omitir o overlay cloud. Não usar `--remove-orphans`, que pode
apagar o outro perfil. A configuração Kraken publicada permanece intacta. Cada
perfil tem 1000 USDT fictícios e bancos distintos; duas sessões não formam uma
carteira unificada. Para o plano VPS, escolher uma primária. Fallback é decisão
manual sem transportar posições/ordens entre exchanges.

## Backup local, depois de parar o perfil

```sh
python3 scripts/backup_paper.py --exchange okx
```

O helper recusa engine ativo e verifica ambos os snapshots SQLite. Não envia dados
externamente nem faz restore automático. Manifesto/SHA256 e snapshots ficam em
`user_data/research/backups/okx/`, ignorados pelo Git. O plano de agendamento,
retenção e recuperação está em [vps-plan.md](vps-plan.md).

## Pesquisa: somente desenvolvimento Binance 2024

Precisa do Feather histórico com SHA publicado; não refazer download de 2025.
Comandos abaixo executam em container com `network_mode: none`. Os intermediários
não são commitados; `docs/okx/evidence/research2024/` preserva os exports desta tarefa.

```sh
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm --entrypoint python freqtrade /freqtrade/scripts/run_development_suite.py
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm --entrypoint python freqtrade /freqtrade/scripts/run_development_suite.py --execute
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm --entrypoint python freqtrade /freqtrade/scripts/analyze_development.py
```

Sem `--execute`, apenas imprime o protocolo e verifica hashes. A suite executa
15 combinações fixas; uma falha deixa diretório pending, excluído da análise.
O analisador usa o último complete, guarda métricas em
`user_data/research/research2024-analysis/` e não modifica relatórios publicados.
Executar novamente não significa nova validação. Nenhum candidato aprovado;
não promover com base em um fold positivo. O runner legado `run_research.py`
permanece bloqueado pelo protocolo histórico.

## Git e CI

```sh
python3 scripts/check_ci.py --branch feat/realtime-paper-trading --output user_data/research/okx-ci.json
```

Confere o SHA remoto exato e status explícito no GitHub; erro/in_progress não é
CI verde. O GitHub API pode falhar com CONNECT 403 nesta nuvem; o verificador usa
HTML público e registra hash/URL do run, sem criar tokens.
