# Protocolo de pesquisa

Baseline definido antes de consultar os resultados; sem otimização nesta etapa.
Usa somente BTC/USDT spot da Binance, candles de 1h e operações long simuladas.
Não usa ML, LLM, API privada, dados de conta ou alavancagem.

## Regras fixas

| Item | Regra |
|---|---|
| Médias | SMA de fechamento, 20 e 50 candles |
| RSI | TA-Lib RSI14 |
| Entrada | SMA20 atual > SMA50 atual e SMA20 anterior ≤ SMA50 anterior; 50 ≤ RSI14 < 70; volume > 0 |
| Saída por sinal | Cruzamento contrário (SMA20 atual < SMA50 atual e anterior ≥) ou RSI14 ≥ 75; volume > 0 |
| Stop-loss | -5%, independente do sinal de saída; custos podem tornar a perda maior |
| ROI automático | Desativado (`minimal_roi = {}`) |
| Trailing / DCA / short | Desativados |
| Aquecimento | 200 candles anteriores ao início efetivo |
| Capital | Carteira fictícia nova de 1000 USDT por período |
| Exposição | 1 posição, `stake_amount=unlimited`, 99% do saldo disponível |
| Taxas | 0,001 (0,1%) por lado, inclusive compra e venda |
| Ordens simuladas | Market; stoploss_on_exchange=false |

Sinais são calculados com informações do candle fechado. O Freqtrade normalmente
simula o preenchimento na abertura do candle seguinte; consulte as limitações
do motor para colisões de sinais e prioridade de stop-loss. O fim do período pode
forçar o encerramento de posições abertas e isso aparece nos resultados.

## Separação temporal

Todos os intervalos são UTC, com fim exclusivo:

| Uso | Intervalo |
|---|---|
| Download, incluindo warm-up e candle de fronteira | 2023-12-01 a 2025-07-02 |
| Desenvolvimento | 2024-01-01 a 2025-01-01 |
| Validação original, já observada | 2025-01-01 a 2025-07-01 |
| Novo holdout, reservado sem consulta nesta auditoria | 2025-07-01 a 2026-07-01 |

Os 200 candles anteriores a cada início alimentam somente os indicadores; não
geram operações contabilizadas fora do intervalo. A validação pode usar candles
de dezembro de 2024 para warm-up: são informações passadas disponíveis naquele
momento, não dados futuros. Não há posições nem saldo transportados de um teste
para o outro. O download em um único arquivo não altera essa separação.

O candle real posterior à fronteira permite ao motor contabilizar a execução
exatamente no fim UTC do período. Não permite operações fora da janela: o parser
exige os limites exatos dos exports e todos os trades dentro deles. A estratégia
causal usa somente o candle anterior fechado; candles posteriores não influenciam
os sinais dentro da janela. Buy-and-hold usa apenas o último close **anterior** ao fim.

Não ajuste SMA, RSI, stop-loss ou custos depois de olhar a validação. Se os ajustar,
esse período deixa de ser uma validação independente: reserve outro período
não observado. Não há garantia de que os parâmetros sejam bons; são uma baseline.

## Dados e resultados

`validate-data` exige colunas OHLCV, timestamps únicos e ordenados, preços positivos,
volume não negativo, OHLC coerente e cobertura horária integral de cada período,
incluindo warm-up. O manifesto registra limites e SHA-256 do arquivo de dados.
Dados usados pelos testes unitários são sintéticos, nunca resultados financeiros.

O fallback usa exclusivamente arquivos oficiais `data.binance.vision/data/spot/`
para BTCUSDT, verificando cada `.CHECKSUM` SHA-256 antes de converter para Feather
compatível com Freqtrade. A conversão trata timestamps em ms até 2024 e em µs
desde 2025. Nenhuma exchange ou outro par é combinado com esse histórico.

Os metadados de BTCUSDT vêm da API oficial exclusiva de dados públicos
`data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT`. O snapshot integral,
origem, instante de coleta e SHA-256 ficam registrados. O CCXT da imagem fixada
normaliza esses filtros atuais; não são filtros históricos de 2024/2025.

O adaptador de pesquisa passa esse snapshot ao motor nativo `Backtesting` pela
opção `exchange=` existente no Freqtrade. Ele não altera o motor instalado e
recusa modos live/dry-run de serviço, credenciais, ordens e consultas remotas.
O contêiner de backtest tem `network_mode=none`; somente a aquisição tem rede.

Os backtests usam `--cache none`, diretórios novos por execução e exports do motor.
O relatório verifica número de trades e soma de lucro líquido contra o resumo.
O lucro do Freqtrade já inclui as taxas especificadas. A estimativa total de taxas
é reconstruída dos fills exportados, usando amount × safe_price × fee de cada lado.
Profit factor divide a soma dos lucros líquidos positivos pelo módulo das perdas;
taxa de acerto conta trades positivos; exposição temporal soma horas com uma posição
e divide pela duração UTC do período. Empates não são vitórias. Sem perdas o profit
factor é infinito; sem operações, profit factor e taxa de acerto são indisponíveis.

O benchmark buy-and-hold compra no primeiro open do período e vende no último
close, investindo 99% da carteira inclusive a taxa de compra; mantém 1% em caixa
e paga 0,1% por lado. A razão de preços é `r = último close / primeiro open` e o
retorno líquido da carteira é `0,99 × (r × (1 - 0,001) / (1 + 0,001) - 1)`.
O `Market change` do motor é close/close bruto e é reportado separadamente.
O stake do Freqtrade reserva aproximadamente 99% do saldo **antes** da taxa de
entrada; o benchmark investe 99% **incluindo** essa taxa. Essa pequena diferença
de exposição inicial fica explícita, junto à exposição temporal muito diferente.

Sem modelagem de spread, slippage, impacto, interrupções da exchange ou liquidez
intrabar. OHLCV 1h não permite reconstruir a sequência de todos os eventos dentro
do candle. O drawdown reportado é o campo da conta exportado pelo Freqtrade, não
uma garantia sobre perdas intrabar. Nada disso demonstra retorno futuro.
São apresentados tanto o drawdown sobre trades fechados como o drawdown da carteira
marcada nos instantes disponíveis ao motor (`wallet_stats`), sem alegar reconstrução
de todo o caminho intrabar. Filtros de lote/tick são os atuais, não históricos.

## Verificações

Obrigatórias: Docker/Compose, carregamento de configuração e estratégia, testes
unitários com dependências reais da imagem, download, cobertura de dados,
backtests separados e leitura dos exports atuais. O script não calcula métricas
se esses pré-requisitos falharem.

Na pesquisa original, os testes de causalidade comparavam indicadores e sinais
em prefixos; as ferramentas nativas ainda não tinham sido executadas. A auditoria
posterior executou `LookaheadAnalysis` e `RecursiveAnalysis` oficiais com o motor
offline, além de controles por prefixos e recursive rolling, somente em 2024.
Resultados e limitações estão em [risk-report.md](risk-report.md). Custos de execução
foram modelados como hipóteses de estresse em replays, sem reescrever os exports.

O protocolo futuro usa apenas 2024 para escolher melhorias. Janeiro–junho/2025
não pode selecionar parâmetros. A nova reserva, o limite da fronteira anteriormente
presente no cache, critérios de risco e gates para ML estão em
[experiment-plan.md](experiment-plan.md). O fluxo histórico permanece bloqueado
para impedir acesso inadvertido à fronteira e sobrescrita dos resultados publicados.
