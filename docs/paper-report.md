# Integração da auditoria e validação do paper trading

Status em 11/10/2026 20:17:46 de Brasília (2026-10-11T23:17:46.294588+00:00 UTC).
O motor nativo está processando dados públicos Kraken dos três pares. A suíte
completa passou: **86 testes, zero falhas/erros/skips**. O banco ativo contém
**0 trades e 0 ordens**. Nenhum trade foi inventado ou
injetado nesse banco. Isso é validação técnica em ambiente de desenvolvimento,
sem deploy, operação real ou garantia24/7. CI remoto do novo commit deve ser
conferido depois do push pelo SHA exato; evidência final indicada na entrega.

## Histórico e congelamento

A integração preserva os pais `1d3e143bd652ff549ee8f96c5d8d39d4e4dbad86` e
`46d376ebdd141f2fb20da6fcd88ed5b2833b0138`. O conflito de CI foi resolvido usando
o override de auditoria com rede desativada e a montagem somente leitura do
Compose paper exigida pela correção `1d3e143`. O CI desse pai estava verde:
[execução38166689604](https://github.com/Ruan-dev-back/TradeBot-AI/actions/runs/38166689604).

Todos os sete arquivos do lock da baseline coincidem com seus hashes; os15
arquivos da auditoria original, incluindo relatório, plano, reserva e evidências,
foram preservados byte a byte. A baseline histórica continua SMA20/50 + RSI14,
stop5%, Binance BTC/USDT1h, com os resultados publicados69/41 trades e prejuízo.
O relatório original não foi sobrescrito. O holdout UTC
`[2025-07-01, 2026-07-01)` permaneceu fechado; os scripts legados continuam
bloqueados. A ressalva de aquisição antiga de candles de fronteira foi preservada.

## Conectividade e dados atuais

- Binance: HTTP451 e mensagem explícita de localização restrita da exchange.
  Não houve tentativa de contornar esse bloqueio.
- Kraken: inicialmente CONNECT403 do proxy. Inclusão de `api.kraken.com` preservou
  os domínios antigos; após propagação, Time/AssetPairs retornaram200.
- CCXT4.5.84 síncrono exigiu `requests_trust_env=true`; o async precisou do bundle
  de CA gerenciado. TLS continuou habilitado, sem endpoints alternativos.
- Schema nativo: Telegram desativado exige token/chat_id vazios. A seção API de
  controle remoto foi omitida para mantê-la desativada sem criar segredo JWT.
- Consulta opcional CoinGecko403 foi removida desativando apresentação fiat;
  essa consulta não é necessária para trading em USDT.

A verificação pública obteve219 candles fechados por par, UTC/1h, sem gaps nem
duplicações, suficientes para startup200. Mínimos de quantidade atuais:
BTC0,00005, ETH0,001, SOL0,06; mínimo notional0,5USDT nos três. A tarifa taker
reportada pelos metadados CCXT foi0,0026; não é tarifa autenticada de conta.
O paper usa hipótese conservadora0,004 por lado, explicitamente fixada.
API pública acessível e pares ativos não comprovam elegibilidade regional de
uma conta; nenhuma credencial ou conta foi conectada.

O snapshot final nativo mostra719 candles em memória por par após reinicialização,
com os últimos200 íntegros e último candle fechado aberto em
`2026-10-11 22:00:00+00:00`. Antes do restart o cache tinha723
candles e havia avançado durante a pausa de uso. O tamanho muda ao recarregar a
janela pública; isso não representa perda de trades ou retorno à reserva histórica.
O `latest_enter_long` é0 nos três pares. Cada janela de200 possui2 sinais
históricos de warmup; eles não são ordens retroativas e não foram apresentados
como trades observados. Não se pode inferir lucratividade da ausência de trades.

## Motor nativo, estado e testes

`FreqtradeBot.create_trade/get_entry_signal/execute_entry` foi exercitado offline
com fixture explícito e banco SQLite temporário: sem sinal criou0 trades; com
sinal criou1 trade com ordem `dry_run_buy_*`, preenchimento e taxas nativas.
O limite de uma posição bloqueou repetição. O método privado CCXT `create_order`
foi um detector de falha e não recebeu chamada. Esses dados artificiais são
exclusivamente testes de software, não pesquisa histórica nem resultados Kraken.

A integração também recuperou ordem limit pendente em instância nova da exchange,
confirmou seu preenchimento com book fixture e reconstruiu trade/wallet pelo
SQLite. A recriação do container real preservou peak, equity, halt, cooldown,
sequência de perdas, IDs e SHA da política. Os três pares voltaram a processar
candles atuais; Docker marcou `healthy`. Um segundo processo foi recusado pelo
lock antes de iniciar o bot. Nenhum banco ativo foi apagado para passar testes.

Cobertura adicional: custos nos dois lados, cap/risco em carteiras diferentes,
min-stake clamp, precisão de quantidade, mínimos desconhecidos, spread/depth,
book antigo/cruzado, candles abertos/antigos/curtos/gaps/duplicatas/volume zero,
falhas de callbacks, dry-run/futuros/credenciais/overrides, cooldown e halt após
restart, healthcheck de dados antigos e causalidade dos novos candidatos.
Os41 testes originais e os18 da auditoria continuam incluídos. Docker/Compose,
compileall, os dois JSON e os Compose de pesquisa/paper/cloud também passaram.

## Gestão de capital implementada

Carteira1000USDT fictícios, posição única, proposta25USDT, sem alavancagem/DCA.
Reserva por posição≤10% da equity e perda nominal projetada≤0,5%. Para stop5%,
taxa base40bps + extra5bps por lado, spread completo10bps e slippage10bps por
lado, a perda projetada por unidade de cash reservado é
`0.0613319319`. Em equity1000, o teto de stake é
`81.036834 USDT`; a proposta25USDT permanece mais baixa,
com risco projetado de cerca de0.1543% da carteira.
Mínimos nunca aumentam automaticamente esse teto; confirmação verifica também
a quantidade arredondada. Os custos extras são reserva de risco, não taxa
adicional efetivamente cobrada pelo motor nativo.

Equity marcada ao bid com custos de liquidação; aviso DD3%, halt persistente em
DD6% e solicitação de saída fictícia. Cooldown1h após qualquer saída e24h após
três perdas consecutivas. Gaps, movimentos entre consulta/fill e desconexões
podem superar risco/DD nominal. Entrada limit, saída/stop market: Freqtrade dry-run
admite até5% de slippage em mercado e não reproduz fila, latência ou fills reais.
O alerta readonly de chown do Freqtrade é não fatal; mounts preservam os arquivos.

## Framework 2024

Smoke nativo realizado somente em D1:2024-04-01 00h a2024-06-30 23h UTC,
Binance BTC/USDT1h, taxa10bps por lado. Todos os resultados vêm dos exports reais
nativos. B0 mantém stake original; candidatos têm sizing menor, portanto suas
perdas em carteira não isolam o efeito dos sinais.

| Candidato | Trades | Líquido USDT | Retorno | DD nativo | Profit factor | Acerto |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 17 | -185.3353 | -18.5335% | 23.7587% | 0.4031 | 23.53% |
| trend | 5 | -11.4483 | -1.1448% | 1.1448% | 0.0000 | 0.00% |
| breakout | 20 | -9.9112 | -0.9911% | 1.0935% | 0.5746 | 40.00% |
| mean_reversion | 16 | -0.9525 | -0.0953% | 0.4636% | 0.8978 | 62.50% |

O market change bruto nativo foi−11,7787% no mesmo intervalo. Não é buy-and-hold
líquido com custos. O smoke verifica compatibilidade; não valida candidatos e
não é ranking para promoção. Spread/slippage extras não foram aplicados aos
fills desses resultados. Faltam D2/D3, benchmark líquido, stress de custos,
curva marcada, pausas no replay, auditorias nativas dos candidatos e incerteza.
Não foram otimizados parâmetros por esses resultados ou por2025. O planejamento
completo e orçamento estão em `docs/development-framework.md`; ML segue fora.

## Correção de isolamento dos testes no CI

O primeiro push de integração (`50e0ce8`) teve CI remoto com falha, preservada em
`ci-integration-failed.json`. O HTML público identifica o job de testes, mas seus
logs completos exigem login e o endpoint público de logs respondeu404. Não foram
extraídas credenciais do proxy para acessá-los.

Uma cópia dos arquivos versionados em diretório temporário, sem novo checkout,
reproduziu dois `PermissionError` ao tornar `user_data/data` somente leitura:
`Configuration.get_config` tentava criar `/freqtrade/user_data/data/kraken` nos
novos testes nativos. Localmente o diretório já existia, mascarando essa dependência.
Os testes agora passam `--user-data-dir` temporário e `--strategy-path` explícito
antes de carregar a configuração, preservando todas as asserções e o banco ativo.

A mesma reprodução restritiva passou86 testes após a correção, e a suíte do
checkout principal também passou86. Esses logs foram preservados em
`ci-permissions-before.log` / `ci-permissions-after.log`. O resultado do CI remoto
do commit corretivo será conferido pelo SHA exato na entrega; não confundir o
status do primeiro push com o estado final da branch.

A nova execução ainda falhou no handler de log. Um wrapper de CI passou a
preservar o exit code da suíte e publicar os tracebacks reais como annotations
GitHub, sem desativar testes. Isso confirmou remotamente dois `PermissionError`
para `/freqtrade/user_data/logs/paper.log`. Os dois testes agora também usam
`--logfile` no diretório temporário. As anotações reais estão em
`ci-remote-errors.log`; a suíte continuou com86 testes aprovados. O teste não
precisa de acesso de escrita ao log do bot ativo.

## Ambiente e operação

As instruções de instalação/startup e o checkout final serão salvos no rascunho
para revisão. Não há requisitos de segredo. A ferramenta retorna
`requires_publish=true`: revisão/salvamento e publicação do ambiente são ações
na interface pelo usuário. O agente não pode publicar nem confirmar que o aviso
visual “Requer atenção” desapareceu. Isso não bloqueou o teste na instância atual.

Para24/7 faltam hospedeiro persistente, monitoramento externo, alertas e resposta
a falhas, backup/restore dos dois SQLite, reconciliação e teste de desconexões,
retenção de logs e verificação regional. Docker restart/healthcheck não suprem
essas condições. O bot ativo nesta máquina é apenas paper; não é deploy.

Evidências completas em `docs/paper/evidence/`: `tests.log`, `market.json`,
`status-final.json`, `restart-validation.json`, `single-writer.json`,
`integration.json`, `ci-local-commands.json`, exports `development-*.json` e logs
de erros anteriores. CI remoto pós-push será verificado separadamente e citado
na entrega para não confundir o CI do pai com o commit final.
