# Protocolo prospectivo OKX: janela fixa de sete dias

Registrado antes da primeira coleta do novo observador. Objetivo primário:
validar operação técnica de paper trading, sem selecionar estratégia ou alegar
rentabilidade. Ponto de partida: `3dd86a8`; baseline, auditoria e fontes históricas
permanecem congeladas. OKX principal; Kraken alternativa **manual**, com carteira
e banco independentes. Não migrar posições nem somar as duas carteiras.

## Janela, regras congeladas e origem

T0 é o primeiro início real de `paper_monitor.py watch --exchange okx`, gravado
em UTC no metadata do diário. T1=T0+168 horas corridas, intervalo `[T0,T1)`.
Não antecipar T0 para o início antigo do container nem contar warmup como coleta
prospectiva. Reinício preserva T0/T1; a janela não é estendida para esconder falhas.
Amostras depois de T1 podem continuar como monitoramento, mas não reparam a janela
original nem entram no seu P&L ou cobertura. Relatório distingue elapsed, cobertura
amostrada e sete dias qualificados. Antes de T1, sempre sete dias incompletos.

Somente dados públicos **OKX spot BTC/USDT, ETH/USDT, SOL/USDT**, após o holdout
fechado. Preços REST a cada 20s no bot; sinais em candles fechados de 1h. Coleta
independente no host a cada 30s. UTC em todos os registros; apresentação de agenda
em Brasília deve indicar UTC-03 explicitamente. Não consultar preços do holdout
UTC `[2025-07-01,2026-07-01)`; janeiro–junho/2025 continua observado e vedado à
seleção. Nenhum download/backtest histórico nesta janela.

Sinais SMA20/50+RSI14 da cópia paper, stop 5%, carteira fictícia 1000 USDT,
stake proposto 25, uma posição, cap de gasto reservado 10%, risco nominal <=0,5%,
fee 40bps/lado e reservas publicadas, aviso DD3%/halt DD6%, cooldown1h/24h.
Não reduzir filtros, alterar sizing ou forçar sinais. `dry_run=true`, sem
alavancagem, API privada, chaves, demo autenticado, painel ou ML.

O manifest fixa hashes de protocolo, config, estratégia, política, monitor,
telemetria, healthcheck e Compose. HEAD inicial é registrado como proveniência;
commits de evidência/documentação fora desses arquivos podem avançar sem mudar a
janela. Mudança de qualquer conteúdo congelado é recusada pelo observador,
inclusive em execução. Se uma correção operacional for indispensável, encerrar
explicitamente a janela e registrar a falha; criar novo protocolo em etapa
autorizada, preservando o diário anterior. Não apagar SQLite para recomeçar.

## Evidência e disponibilidade

Cada amostra registra: UTC local, container ID/StartedAt/restart count/health,
heartbeat do engine, quotes com timestamps, último candle fechado, sinais,
motivo de não entrada, wallet, posições, ordens fictícias, P&L, fee, risco,
erros/tentativas e alertas. O monitor consulta somente arquivos e SQLite do bot
em modo leitura; não envia ordens nem altera seus bancos. Eventos operacionais
do bot ficam em `telemetry.sqlite`, separado do SQLite nativo e do risco.

`candidate` e `confirmed` são sizing/confirmação, não execução. Uma ordem/trade
exige evidência do SQLite nativo com ID dry_run. Sinais antigos no warmup e
eventos anteriores a T0 não viram operações prospectivas. Ordens e posições que
já existiam em T0 ficam identificadas como preexistentes; não liquidá-las para
limpar o estudo. P&L realizado incremental pode incluir saída de posição antiga.

Diário separado, transacional e com encadeamento SHA256; startup/report/export
verificam a cadeia. Alerta raised/recovered é deduplicado e persistente. Hashes
detectam mudanças acidentais, não fornecem atestação externa inviolável. Fazer
export diário via SQLite backup online e preservar manifest/SHA fora do host
somente quando armazenamento e autorização estiverem definidos.

Intervalo <=45s entre duas amostras, com mesmo StartedAt, conta como intervalo
amostrado; ambas saudáveis contam no intervalo saudável. Intervalo maior, restart
ou heartbeat não avançando é registrado sem preencher lacunas por interpolação.
Cobertura usa tempo real limitado a T1; status Docker running sozinho não vale.
Saltos entre candles vistos são “candles não observados entre coletas”, diferentes
de gaps de OHLCV detectados pelo validador de 200 candles do bot.

Aceite técnico pré-registrado: 168h decorridas; cobertura amostrada >=99%;
intervalos saudáveis >=99% da janela; amostra perto de T1 (<=45s); último estado
da janela saudável e sem bloqueio operacional. Esse limiar permite até 1% de
indisponibilidade observada; não afirma continuidade perfeita. Relatar todas as
falhas independentemente do aceite, sem excluir dias ruins. Sem amostras ou
tempo insuficiente: inconclusivo, não aprovado. Aceite técnico não mede edge.

## Healthchecks, alertas e recuperação

- Bot: heartbeat/risco/wallet <=30s, quote <=30s, preço positivo/book não cruzado,
  candles fechados/UTC1h frescos e coerentes, >=200 barras validadas, SQLite
  nativo/risco/telemetria íntegros e política de risco preservada.
- Observador: último registro <=45s, SHA/SQLite válidos; timer independente ou
  consulta por outro terminal detecta travamento do próprio observador.
- Alertas locais: API/loop, stale/gaps, processo ausente, Docker unhealthy,
  persistência, journal ausente/corrompido, DD3%, halt6%, restart e lacuna de coleta.
  Halt é proteção ativa: liveness pode estar saudável enquanto entradas bloqueadas.
- Resposta: preservar bancos, investigar causa, corrigir dependência e verificar
  dados/risco antes da retomada. Não apagar halt, mudar endpoint/região ou produzir
  sinal artificial. Restart não deve apagar peak/cooldown/IDs.

Alertas desta etapa são SQLite/terminal/journald local proposto. Nenhuma mensagem
foi enviada a terceiros. Monitor externo ao host e canal humano de resposta são
pendências antes de uma alegação 24/7; perda do próprio host pode impedir alertas
locais. PC deve permanecer ligado, conectado, com NTP e suspensão desativada.
VPS, systemd e timer são templates, sem instalação ou contratação nesta tarefa.

## Análise permitida e encerramento

Durante a janela: analisar saúde, clock, gaps, recusa de entradas, custos
simulados, persistência e recuperação. Relatar zero ordens/trades se não houver
sinal ou se os limites recusarem entrada. Não otimizar sobre esses preços, nem
selecionar o “melhor par”. Ausência de operação não demonstra rentabilidade.

Ao final: reportar duração/cobertura, incidentes/restarts, ordens comprovadas,
PnL realizado/não realizado com fronteira explícita, fees reconstruídas, risco e
posições abertas. Não zerar posições automaticamente em T1. P&L marcado é uma
estimativa de liquidação ao bid com fee; não garante fill ou preço futuro.
Não anualizar retorno pequeno nem comparar as carteiras OKX/Kraken como uma só.

Preços recebidos ficam disponíveis para auditoria operacional, **não para
otimização** nesta janela. Eventual reutilização futura é observada, nunca holdout
independente. A etapa quantitativa continua NO-GO; próximos experimentos seguem
o [protocolo futuro](future-research-protocol.md), sem abrir a reserva histórica.
