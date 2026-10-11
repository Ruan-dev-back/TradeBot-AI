# Auditoria técnica de perdas e gestão de risco

Baseline SMA20/50 + RSI14 publicada, stop-loss de 5%, Binance BTC/USDT spot 1h.
Estratégia, configuração, relatório original e exports permanecem congelados.
2024 é desenvolvimento; janeiro–junho/2025 já foi observado e não seleciona parâmetros.
Holdout 2025-07-01–2026-07-01 UTC reservado, sem consulta de preços/resultados nesta auditoria.

## Integridade, CI e análises temporais

Commit de origem: `da44deec143805e6016906e734e259e8595ee175`. Hashes em `docs/audit/baseline-lock.json`.
CI remoto: **success**, commit `490caa7ab0f4fdaf50507edad29538bcca0231f2`, [execução](https://github.com/Ruan-dev-back/TradeBot-AI/actions/runs/38163008559).
Esse CI corresponde ao commit remoto inspecionado antes desta auditoria; não prova CI do novo commit local.
Lookahead nativo Freqtrade 2026.9: 68 trades/sinais avaliados; entradas enviesadas 0, saídas 0, indicadores []; has_bias=False.
Causalidade suplementar: 147 prefixos, diferenças {'sma_fast': 0, 'sma_slow': 0, 'rsi': 0, 'enter_long': 0, 'exit_long': 0}.
Recursive nativo compara a última linha para 50/100/200/400/800 candles de histórico.
Complemento rolling com 200 candles: 8784 horas, erro máximo RSI 0.00008527 pontos, mudanças de sinais {'enter_long': 0, 'exit_long': 0}, critério RSI ≤ 0.001 ponto.
O lookahead nativo força carteira 1 bilhão, stake 10000 e max_open_trades=-1 (um par),
sem alterar arquivos da baseline. Ignora force_exit; seus valores financeiros não são uma nova comparação.
Não detectar viés nessas verificações não prova ausência universal de vazamento.
O recursive nativo avalia apenas a última linha; o complemento verifica efeitos nos sinais em todo 2024.

| Histórico (candles) | Diferença relativa RSI na última linha, nativo (%) |
|---|---:|
| 50 | 1.01566017 |
| 100 | 0.00514634 |
| 200 | 0.00002976 |
| 400 | 0.00000000 |
| 800 | sem diferença registrada |

O nativo arredonda diferenças relativas a 12 casas e interrompe comparação ao convergir;
zero/ausência nessa tabela não garante igualdade matemática em todas as horas. O rolling
de 200 mantém a diferença absoluta sem esse arredondamento e confere sinais em todo 2024.

## Fatos observados: 110 operações simuladas com candles reais

| Métrica | 2024 | Jan–jun/2025 observado |
|---|---:|---:|
| Trades | 69 | 41 |
| P&L antes de taxas, mesmos fills (USDT) | -67.8166 | -52.3873 |
| Taxas (USDT) | 111.9616 | 69.7307 |
| P&L líquido (USDT) | -179.7782 | -122.1180 |
| Retorno líquido (%) | -17.9778 | -12.2118 |
| Profit factor líquido | 0.7655 | 0.7346 |
| Taxa de acerto (%) | 37.68 | 39.02 |
| Exposição temporal (%) | 22.35 | 29.17 |
| Drawdown de trades fechados (%) | 30.12 | 22.18 |
| Drawdown da carteira marcada pelo motor (%) | 33.60 | 22.63 |
| Média de retorno dos vencedores (%) | 2.9070 | 2.5353 |
| Média de perda dos perdedores (%) | 2.1510 | 2.0869 |
| Acerto de equilíbrio, pesos constantes (%) | 42.53 | 45.15 |
| Maior sequência de perdas | 8 | 6 |
| Trades positivos brutos tornados não positivos pelas taxas | 2 | 0 |

As taxas são reconstruídas de amount × preço × taxa em ambos os fills.
P&L bruto menos taxas = P&L líquido, nas quantidades publicadas. Mesmo sem taxas, ambos
os conjuntos de fills apresentam prejuízo. Esse contrafactual não recalcula capital nem decisões.
A taxa de equilíbrio usa médias dos retornos por posição, com pesos iguais; não é garantia
para stakes variáveis. O modelo original usou aproximadamente 99% do saldo por posição.

### Distribuição de retorno líquido por posição (%)

| Quantil/estatística | 2024 | Jan–jun/2025 |
|---|---:|---:|
| min | -5.1898 | -5.1898 |
| p10 | -3.7075 | -3.4707 |
| p25 | -2.1065 | -1.8907 |
| median | -0.9555 | -0.5883 |
| p75 | 1.5155 | 1.7150 |
| p90 | 3.9762 | 2.9357 |
| max | 7.8582 | 6.9846 |
| mean | -0.2451 | -0.2831 |
| std_sample | 3.0323 | 2.7804 |

Quantis usam interpolação linear tipo 7; desvio padrão amostral. Distribuições em USDT,
duração em horas e histograma estão no JSON integral. Amostras de 69/41 trades são pequenas
e temporalmente dependentes; não foram tratados como observações IID para alegar significância.

### Motivos de saída

| Período | Motivo exportado | Trades | Bruto USDT | Taxas USDT | Líquido USDT |
|---|---|---:|---:|---:|---:|
| 2024 | sma_down_or_rsi_75 | 64 | 110.7360 | 103.5516 | 7.1844 |
| 2024 | stop_loss | 4 | -173.8172 | 6.7789 | -180.5961 |
| 2024 | force_exit | 1 | -4.7354 | 1.6311 | -6.3664 |
| 2025 H1 | sma_down_or_rsi_75 | 38 | 84.6906 | 64.3846 | 20.3060 |
| 2025 H1 | stop_loss | 3 | -137.0779 | 5.3460 | -142.4240 |

O tag `sma_down_or_rsi_75` agrega cruzamento contrário e RSI ≥ 75; o export sozinho
não separa essas causas. `force_exit` é fechamento administrativo no fim de 2024.
As perdas dos stops dominam o P&L agregado, mas eliminar stops a posteriori não reproduziria
os mesmos trades nem demonstra melhoria: as posições poderiam sofrer perdas adicionais.

## Cenários hipotéticos de capital

Replays aritméticos dos mesmos trades, preços relativos e datas; não são novos backtests nem
validação independente. Cada período reinicia com 1000 USDT. A fração inclui a taxa de compra;
o restante fica em caixa sem rendimento. Não há arredondamento de lotes, mínimos, rejeições,
impacto ou mudança no conjunto de operações. Essa convenção difere do stake original antes da taxa.

`r = (P_exit/P_entry) × (1-c)/(1+c) × (1-fee)/(1+fee) - 1`
`E_next = E × (1 + fração × r)`; `c = spread_completo/2 + slippage_por_lado`.

| Período | Fração da carteira | Líquido USDT | Retorno % | Drawdown fechado % | Capital × tempo médio % |
|---|---:|---:|---:|---:|---:|
| 2024 | 5% | -8.4990 | -0.8499 | 1.6876 | 1.1174 |
| 2024 | 10% | -17.0802 | -1.7080 | 3.3577 | 2.2347 |
| 2024 | 20% | -34.4753 | -3.4475 | 6.6452 | 4.4695 |
| 2025 H1 observado | 5% | -5.8256 | -0.5826 | 1.2106 | 1.4583 |
| 2025 H1 observado | 10% | -11.6945 | -1.1694 | 2.4115 | 2.9167 |
| 2025 H1 observado | 20% | -23.5573 | -2.3557 | 4.7842 | 5.8333 |

Exposição temporal permanece igual: o replay mantém todas as datas. Exposição financeira
diminui. Capital × tempo é um proxy (fração-alvo × tempo posicionado), não uma média exata
da exposição marcada a mercado durante cada posição. Drawdown desses cenários usa apenas
fechamentos; não reconstrói perdas intrabar.
Menor stake limita a magnitude das perdas e também dos ganhos; não cria vantagem estatística.

## Sensibilidade de execução e custos

Hipóteses de estresse, não estimativas de spread ou slippage histórico a partir de OHLCV 1h.
Spread é completo e aplicado pela metade em cada lado; slippage e taxa extra são por lado.
A taxa base de 10 bps por lado já está incluída; não é cobrada duas vezes.

| Cenário | Spread completo bps | Slippage/lado bps | Taxa extra/lado bps |
|---|---:|---:|---:|
| reference_fee_only | 0 | 0 | 0 |
| low | 4 | 2 | 0 |
| central | 10 | 10 | 5 |
| adverse | 20 | 20 | 10 |

Decomposição estática nas quantidades originais; não é carteira reexecutada:

| Cenário | P&L líquido 2024 USDT | P&L líquido 2025 H1 USDT |
|---|---:|---:|
| reference_fee_only | -179.7782 | -122.1180 |
| low | -224.5628 | -150.0103 |
| central | -403.7015 | -261.5795 |
| adverse | -627.6250 | -401.0410 |

Replays com frações menores e execução adversa, todos igualmente hipotéticos:

| Período | Exposição | Cenário | Retorno % | Drawdown fechado % |
|---|---:|---|---:|---:|
| 2024 | 5% | central | -2.2030 | 2.6188 |
| 2024 | 5% | adverse | -3.5326 | 3.6931 |
| 2024 | 10% | central | -4.3730 | 5.1806 |
| 2024 | 10% | adverse | -6.9566 | 7.2633 |
| 2024 | 20% | central | -8.6141 | 10.1365 |
| 2024 | 20% | adverse | -13.4891 | 14.0493 |
| 2025 H1 observado | 5% | central | -1.3907 | 1.7477 |
| 2025 H1 observado | 5% | adverse | -2.1893 | 2.4837 |
| 2025 H1 observado | 10% | central | -2.7700 | 3.4722 |
| 2025 H1 observado | 10% | adverse | -4.3391 | 4.9136 |
| 2025 H1 observado | 20% | central | -5.4942 | 6.8519 |
| 2025 H1 observado | 20% | adverse | -8.5222 | 9.6160 |

## Proposta de gestão de capital, sem implementação

Orçamento de perda nominal por trade: 0,5% do saldo; teto de exposição: 10%; uma posição
spot long, sem DCA/alavancagem. Alocação inclui taxas. Essas são restrições de risco
propostas, não uma escolha do cenário mais rentável nem uma otimização sobre 2025.
`fração = min(10%, 0,5% / perda_por_posição_no_stop_com_custos)`.
Com stop de 5% e custos centrais, perda modelada por posição 5.5683%;
teto resultante 8.9794% da carteira, em vez de 99%.
Antes de simular ordens, arredondar quantidade para baixo, conferir lote/notional, rejeitar
stakes abaixo do mínimo e reservar caixa para custos. Não elevar stake para atingir o mínimo.
Propor revisão ao atingir 3% de drawdown e pausa de novas entradas aos 6%, até revisão registrada;
3 perdas consecutivas acionam pausa simulada de 24h. Regras não foram aplicadas aos exports.
Um gap hipotético de −10%, nessa fração e custos centrais, causaria 0.9463%
de perda da carteira, acima do orçamento nominal: stop não garante o limite em gaps.

## Por que perdeu: fatos e hipóteses

**Fatos:** P&L bruto negativo, custos relevantes, profit factor abaixo de 1, mais trades
perdedores que vencedores e perdas agregadas concentradas nos stops. O buy-and-hold já
publicado foi superior nos dois períodos; a exposição temporal foi somente 22,35%/29,17%.
Isso explica a identidade contábil das perdas e a baixa participação no movimento do ativo,
sem identificar sozinho uma causa econômica única.

**Hipóteses a testar somente em 2024:** cruzamentos atrasados em movimentos curtos podem
gerar reversões; RSI ≥ 75 pode encerrar tendências cedo; ausência de filtro de regime pode
aumentar whipsaws. Os exports não comprovam regime lateral nem permitem atribuir todas as
saídas especificamente ao RSI. Ajustar/remover stops pelos trades já vistos seria seleção retrospectiva.

## Próxima etapa e critérios para ML

Veja [experiment-plan.md](experiment-plan.md) para folds de 2024, orçamento de experimentos,
critérios de risco/custos e congelamento antes de abrir o novo holdout. A baseline atual não
passa o critério econômico: perdeu mesmo antes de taxas nos fills publicados. ML fica bloqueado
até dados/protocolo causais, benchmark simples robusto, custos de estresse e critérios objetivos
serem satisfeitos. Nenhum ML, chave, operação real ou alegação de lucratividade futura nesta etapa.

Suíte final: **59 testes passando**, incluindo os 41 originais. Execução `20261011T185104627849Z`.
