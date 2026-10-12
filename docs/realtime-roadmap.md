# Paper trading com dados atuais

O serviço Kraken é exclusivamente fictício. `MultiAssetPaperStrategy` copia os
sinais SMA20/50 + RSI14 da baseline histórica não lucrativa, com gestão de risco
separada. O histórico Binance não valida resultados Kraken. Não há ML, painel,
credenciais privadas ou ordens reais. A baseline `SmaRsiStrategy` permanece intacta.

## Iniciar e verificar

Execute na raiz do repositório. Docker/Compose já existem; nenhum pacote novo foi
instalado. Em host com proxy e CA gerenciados, use ambos os arquivos abaixo:

```sh
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml config --quiet
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml run --rm \
  --entrypoint python papertrade /freqtrade/scripts/check_market.py
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml up -d
python3 scripts/paper_status.py
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml ps
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml logs -f --tail=100
```

Em host sem esse proxy Linux, omita `-f docker-compose.paper.cloud.yml`. Não use
`up` se a verificação pública falhar. Kraken não é um endereço alternativo da
Binance: é outra exchange, declarada em configuração independente. Não use VPN,
endpoints alternativos ou credenciais para contornar geobloqueios. A resposta
pública não comprova elegibilidade legal ou de uma conta na região.

A entrada Python não aceita argumentos nem `FREQTRADE__*`, valida configuração,
hashes e holdout, e fixa `freqtrade trade --dry-run`. Um lock impede dois processos
escrevendo o mesmo estado. API de controle remoto ausente/desativada; Telegram
explicitamente desativado com campos vazios exigidos pelo schema. Não há portas
expostas. `fiat_display_currency=""` evita consultas desnecessárias ao CoinGecko.
TLS permanece verificado: clientes CCXT respeitam o proxy e o bundle de CA
somente leitura; não se alteram URLs da exchange.

## Política fixa de risco

Carteira inicial1000 USDT, spot, uma posição long, sem DCA ou alavancagem. Stake
proposto25 USDT; o callback pode reduzi-lo. O gasto reservado por posição deve ser
≤10% da equity atual e a perda projetada pelo stop5%, com custos, ≤0,5% da equity.

Taxa nativa simulada40bps por lado. O orçamento reserva mais5bps de taxa por lado,
spread completo10bps e slippage10bps por lado. São hipóteses conservadoras de
simulação; não tarifas de conta verificadas. Em carteira1000 USDT, o teto calculado
é aproximadamente81,04 USDT de stake, mas o limite proposto permanece25 USDT. O
notional é verificado novamente após os mínimos do Freqtrade e o arredondamento
de quantidade. Se o mínimo exigir exceder o orçamento, nenhuma posição é criada.

Book cruzado/inválido, spread acima do orçamento, impacto sem profundidade,
metadados/minimos desconhecidos, taxa pública superior à reservada, candle ainda
aberto, gaps, duplicatas, UTC/1h inválidos, indicadores ausentes, volume zero,
menos200 candles, observação de risco antiga e exceções bloqueiam entradas.
A idade do último candle aberto deve ficar entre1h e2h05; a atualização da
observação de risco deve ter no máximo30s. O book é obtido por chamada pública
limitada a3s; timestamp, quando disponibilizado, precisa ter no máximo30s.

Equity marcada: USDT livre + valor líquido de liquidação dos trades abertos ao
bid. Peak persistente; aviso DD3%, bloqueio permanente de entradas e saída
fictícia solicitada ao atingir DD6%. Restart não remove o bloqueio. Cooldown1h
após saída; três perdas consecutivas acionam24h. IDs de trades fechados impedem
processamento duplicado. Alterar a política exige reconciliação explícita do
estado; não existe comando automático para apagar peak/cooldown/halt.

Stop, spread e slippage podem exceder o cenário nominal em gaps ou desconexão.
Saída de mercado no dry-run usa o modelo nativo de book do Freqtrade, que admite
slippage de até5%; não há garantia de perda máxima. Entradas são limit, expiram
após10min. Reservas de custos extras não alteram a taxa nativa ou criam fidelidade
à fila/latência real da exchange.

## Persistência, saúde e reinicialização

- `user_data/tradesv3.paper.sqlite`: trades, ordens e wallet nativos.
- `user_data/paper/risk.sqlite`: peak, halt, cooldown e IDs processados.
- `user_data/paper/status.json`: última observação e candles/sinais por par.
- `user_data/logs/paper.log`: log rotativo nativo; Docker limita logs a3×10MB.

Esses arquivos são locais, ignorados pelo Git e preservados por bind mount.
Não os apague para reiniciar. O healthcheck usa dados, observação de risco e
SQLite; um PID isolado não passa. Docker marca `unhealthy` se o teste falhar,
mas isso não reinicia automaticamente o container por si só.

```sh
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml restart
python3 scripts/paper_status.py
# Para encerrar o processo sem excluir os bancos:
docker compose -f docker-compose.paper.yml -f docker-compose.paper.cloud.yml stop
```

O teste desta tarefa comprovou recriação do container com persistência e
processamento atual dos três pares. Zero operações fictícias foram observadas no
banco ativo até o snapshot do relatório. Sinais existentes no warmup não são
reexecutados como trades retroativos. Fixtures de integração ficam em bancos
temporários e não são resultados do mercado atual.

## O que falta para funcionamento 24/7

Não houve deploy. Codex Cloud e GitHub Actions não oferecem garantia de operação
contínua. É necessário hospedeiro persistente, monitoramento externo e alertas,
resposta a quedas de API/host, reconciliação após desconexão, backups consistentes
dos dois SQLite e testes de restauração, verificação regional e política de
retenção. O restart do Compose e o healthcheck são recursos locais, não evidência
de disponibilidade24/7. Nenhuma etapa deste roteiro autoriza trading real.

## Atualização OKX

A operação Kraken descrita acima foi preservada. O entrypoint agora aceita
somente `--exchange kraken` (padrão) ou `--exchange okx`, selecionando perfis
explícitos e estados separados; argumentos arbitrários continuam recusados.
Monitoramento REST de bid/ask a cada 20s e saúde schema2 exigem quotes atuais.
O timestamp público é comparado ao recebimento, com jitter futuro máximo de 2s.
Sinais continuam em candles fechados de 1h. Credenciais/demo/sandbox são recusados.
Veja [integração atual](okx-integration-report.md), [comandos](okx-commands.md) e
[plano VPS sem deploy](vps-plan.md). Evidências antigas permanecem preservadas.
