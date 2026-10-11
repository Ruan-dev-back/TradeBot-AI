# Evidências públicas da pesquisa

Execução verificada: `20261011T175632005777Z`, em 2026-10-11 UTC.
`python3 scripts/run_research.py` retornou zero após o fallback oficial; a falha
HTTP 451 da API permanece documentada, não é uma etapa bem-sucedida de aquisição.

- `commands.json`: comandos exatos, códigos de saída e etapas obrigatórias.
- Logs por etapa: saída completa dos contêineres, inclusive o erro nativo.
- `final-run-console.log`: saída completa do comando solicitado após as correções.
- `initial-run-console.log`: execução inicial com falha, antes do fallback.
- `network-diagnostics.json` e `.log`: respostas dos três destinos públicos e
  distinção entre proxy, exchange, DNS, TLS e timeout.
- `final-setup-tests.log`: verificação portátil do setup e 41 testes finais.
- `final-tests.log`: última execução da suíte, com 41 testes passando e rede do
  contêiner desativada: `docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade test`.
- `data_manifest.json`: cobertura, fronteiras UTC, preços do benchmark, hash do
  Feather e proveniência de todos os arquivos mensais com checksums oficiais.
- `market_snapshot.json`: resposta pública real, data de coleta, URL e hash,
  normalizada por CCXT 4.5.84. Os filtros são atuais, não históricos.
- `backtest-development.json` e `backtest-validation.json`: resumo nativo completo,
  todos os trades, métricas derivadas, taxas e SHA-256 do ZIP exportado. O benchmark
  pode ser recalculado com os preços registrados em `data_manifest.json`.

Os dados brutos e ZIPs nativos permanecem em `user_data/`, ignorados pelo Git.
O export JSON permite recalcular profit factor, taxa de acerto, exposição e custos
sem depender de uma tabela transcrita. Os logs registram os períodos exatos e o
motor nativo executado; [../results.md](../results.md) registra os hashes do código.

## Reproduzir

Use o digest do Compose, execute `python3 scripts/run_research.py --source archive`
e compare o SHA-256 do Feather ao manifesto. Uma coleta nova usa metadados atuais;
mudanças de filtros da exchange podem mudar o arredondamento dos fills.

Para reproduzir também o snapshot de filtros desta execução, após adquirir os
mesmos arquivos oficiais, execute da raiz do checkout:

```sh
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

evidence = Path('docs/evidence')
data = Path('user_data/data/binance')
manifest = json.loads((evidence / 'data_manifest.json').read_text())
assert hashlib.sha256((data / 'BTC_USDT-1h.feather').read_bytes()).hexdigest() == manifest['sha256']
snapshot = (evidence / 'market_snapshot.json').read_bytes()
assert hashlib.sha256(snapshot).hexdigest() == manifest['provenance']['market_snapshot_sha256']
(data / 'market_snapshot.json').write_bytes(snapshot)
(data / 'archive_provenance.json').write_text(json.dumps(manifest['provenance'], indent=2) + '\n')
PY
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade validate-data
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade backtesting --offline --period development --output-dir /freqtrade/user_data/backtest_results/reproduced/development
docker compose -f docker-compose.yml -f docker-compose.offline.yml run --rm freqtrade backtesting --offline --period validation --output-dir /freqtrade/user_data/backtest_results/reproduced/validation
```

Use diretórios de export vazios para cada nova reprodução. O adaptador também
verifica a versão CCXT, o hash da resposta pública e o vínculo ao manifesto.
Nenhum candle nem filtro é inventado por esse procedimento.
