# Saúde e riscos da observação prospectiva OKX

Continuação de `3dd86a8`; código/protocolo congelados em `98e4195` antes da primeira coleta. Somente a branch feat/realtime-paper-trading. Nenhuma VPS contratada, nenhum systemd instalado, nenhum ML ou dinheiro real. Configs OKX/Kraken, política de risco e hashes históricos preservados.

## Resultados verificados

- **106 verificações originais preservadas; 122 testes passaram**, com 16 novos testes de observação, persistência, falha/recuperação e marcação de posição. [Log original](prospective/evidence/original-106.log), [suíte ampliada](prospective/evidence/tests.log) e [integridade](prospective/evidence/integrity.json).
- API pública oficial OKX funcionou novamente: instrumentos spot e candles atuais dos três pares; fonte/UTC/integridade em [preflight](prospective/evidence/okx-public.json). Nenhum endpoint privado ou contorno regional. API saudável no CLI significa quotes públicos recentes, não confirmação de elegibilidade de conta.
- OKX e Kraken carregaram schema3 e ficaram saudáveis após reload. SQLite/estado preservados; [comparação antes/depois](prospective/evidence/reload-preservation.json). São duas carteiras fictícias distintas.
- Bancos ativos: **zero trades, zero ordens, zero posições**, wallet/equity1000USDT em cada perfil; P&L realizado/não realizado e fees0. Esses zeros resultam das contagens nativas vazias. Último candle tinha enter_long=0/exit_long=0, motivo no_entry_signal. Não foram reexecutados sinais do warmup. [CLI OKX](prospective/evidence/cli-okx.log), [CLI Kraken](prospective/evidence/cli-kraken.log).

## Janela real iniciada, sete dias ainda incompletos

T0: **2026-10-12T17:17:10.179088+00:00** UTC (12/10/2026, 14:17:10 de Brasília). T1: **2026-10-19T17:17:10.179088+00:00** UTC (19/10/2026, 14:17:10 de Brasília). A agenda depende da continuidade da coleta, não é promessa de disponibilidade.

No snapshot inicial deste relatório: **3 amostras**, 63.2s decorridos, 60.0s entre amostras e 60.0s saudáveis, 0 lacunas/restarts no novo diário. Sete dias decorridos: **false**; janela qualificada: **false**. Não houve candle novo desde a primeira amostra nessa curta captura. Esses números são datados, não o estado futuro do monitor.

O observer host foi iniciado nesta sessão de desenvolvimento, separado dos bots. Health confirmou heartbeat do observer, dados do engine e SQLite. O Docker antes do reload indicava aproximadamente16–17h de uptime; esse indicador histórico não foi contado como observação prospectiva nem sete dias monitorados. Processos desta nuvem podem parar na publicação/restauração; não há garantia24/7.

Análise permitida até aqui é técnica: consultas recebidas, candlestick correto/fechado, quotes e risco frescos, persistência reconciliada, zero operações e nenhum alerta nas primeiras coletas. A captura é curta; não demonstra rentabilidade, taxa de falhas de longo prazo ou comportamento em mercado extremo. Não foi feita otimização sobre dados atuais.

## Defeito encontrado e corrigido

O cálculo da equity com posição aberta usava `Trade.calc_profit(bid).profit_abs`. No Freqtrade2026.9 instalado, calc_profit retorna float; nenhuma posição ativa havia exposto a incompatibilidade. Foi trocado por `Trade.calculate_profit(bid).profit_abs`, sem mudar sinais, stop ou política. O teste usa um Trade nativo fictício de25USDT: compara a equity e o P&L ao método nativo, com fees nos dois lados. Todos os objetos/bancos dessa prova são temporários.

## Falhas e recuperação testadas

| Situação isolada | Evidência esperada e aprovada |
|---|---|
| API desconectada | risk_ready=false, sizing/entrada bloqueados, evento loop_error; recuperação registrada sem replay de sinais |
| Book/candle/wallet antigos ou quote cruzado | saúde falha mesmo com processo running; nenhum lucro indisponível é substituído por zero |
| Disco/telemetria indisponível | confirmação negada; entradas permanecem bloqueadas até recuperação verificável |
| Journal travado/corrompido | TTL45s/SHA/SQLite detectam falha; amostra não persistida não é declarada salva |
| Reinício do observador | T0/T1 e deduplicação de alertas preservados; lacuna/restart sem crédito de cobertura |
| Halt DD6% | liveness pode continuar saudável, entradas bloqueadas e alerta crítico independente |
| Backup online do diário | cópia via API SQLite, cadeia/SHA válidos, fonte não alterada e restore de fixture aprovado |
| Tempo7dias sem registros | não qualifica observação; amostras posteriores não consertam primeira janela |

A suíte anterior mantém testes nativos OKX/Kraken de ordens fictícias, posição/wallet e ordens pendentes após nova instância. Esses fills são **fixtures isoladas**, não operações observadas no mercado. Nenhum banco ativo foi manipulado para fabricar trades.

## Monitoramento e limites

CLI mostra API/heartbeat, candle/bid/ask, sinais/rejeição, posições/ordens, saldo/equity, P&L/fees e risco. Diário separado registra amostras, cadeia, tentativas e transições raised/recovered. Alertas são locais em SQLite/stderr; nenhum canal externo foi configurado ou mensagem enviada. Health do bot valida wallet/risco/quotes/candles e três SQLite; health do observer exige registro recente e operador funcional. Running/PID não bastam.

Política: cap10% na entrada, risco nominal0,5% com custos, stop5%, avisoDD3%, haltDD6% persistente e cooldown1h/24h. Custos e gaps podem superar a projeção; P&L aberto é liquidação estimada ao bid, não fill garantido. As fees são reconstruídas das ordens preenchidas e taxa dry, sem invoice autenticada. Stores de wallet/snapshot/SQLite não formam uma transação global; timestamps mostram diferenças de observação.

O observer verifica conteúdos congelados e recusa mudança; não desliga o bot nem altera seu estado. Se houver incidente de protocolo, o operador deve parar/reconciliar os serviços conforme documentação. Modificação de código não autorizada não é neutralizada magicamente pelo monitor.

## Infraestrutura e próximos passos

Código e templates preparados para Linux/WSL2 ou VPS Linux: observer host separado, timer independente30s e journald. Não instalados/habilitados. [Comandos](prospective-operation.md), [protocolo de168h](prospective-protocol.md), [pesquisa futura](future-research-protocol.md) e [plano de hospedagem já publicado](vps-plan.md).

`systemd-analyze verify` dos três templates retornou erro porque `docker.service`
não existe nesta nuvem, embora o daemon Docker seja acessível. [Erro real](prospective/evidence/systemd-verify.log).
Não foi tratado como aprovação nem instalado um serviço para ocultar a limitação.
Dependências/startup dos templates continuam pendentes no host definitivo; em
WSL2 com Docker externo, revisar a dependência do serviço e verificar o daemon.
O observer/health via CLI foram executados com sucesso independentemente disso.

Pendências: completar a janela com evidência/cobertura, decidir PC persistente ou VPS elegível com autorização e orçamento, monitor externo ao host, destinatário/canal de alerta autorizado, backup externo/retenção e restore/reboot/outage drills no ambiente escolhido. Repetir health após restauração desta nuvem; retomar o mesmo diário sem apagar lacunas.

Todos os candidatos de2024 continuam NO-GO. Pesquisa futura mantém orçamento cumulativo, hipóteses pré-registradas e controle de múltiplos testes; não usa holdout fechado ou dados novos para otimização nesta janela. Gates de causalidade/custos nativos e validação independente continuam pendentes. ML e operações reais permanecem bloqueados; não se promete lucro.

CI **verde** no SHA `253fd7ac75102c5aea579b03c64f6ded2c565576`: [run 38283903199](https://github.com/Ruan-dev-back/TradeBot-AI/actions/runs/38283903199), [evidência do SHA/status/hash](prospective/evidence/ci-verified.json). A API GitHub permanece bloqueada com CONNECT403 nesta nuvem; HTML público confirmou o resultado exato. Logs locais integrais preservam os 122 testes; logs completos do GitHub podem exigir login. O commit posterior apenas registra documentação/evidências, com seu CI também verificado ao finalizar.

## Checkpoint posterior da sessão

Em 2026-10-12T17:25:57.265325+00:00 UTC: 18 amostras, 527.1s decorridos, 510.0s de intervalos amostrados, 510.0s saudáveis; sete dias decorridos/qualificados continuam false. Ordens acrescentadas desde T0: 0. Último estado saudável: True. [Checkpoint](prospective/evidence/observation-final.json). A coleta continua nesta sessão, sem garantia de sobrevivência ao encerramento/publicação do ambiente.
