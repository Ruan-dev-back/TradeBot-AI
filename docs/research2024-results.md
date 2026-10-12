# Resultados de desenvolvimento 2024: nenhum candidato promovido

Quinze backtests nativos concluídos: cinco estratégias em D1, D2 e D3. Todos os candidatos falharam pelo menos um gate econômico/amostral. Resultados positivos em folds isolados não autorizam promoção, ML ou dinheiro real. Esta avaliação é desenvolvimento, sem validação independente.

## Fonte, protocolo e integridade

- Exclusivamente **Binance BTC/USDT spot 1h**, arquivo publicado com SHA256 `7c5aab75eb55620dda2518351ab9a857f5500b42cb15bc16e6d0632c74265321`. Nenhum preço OKX/Kraken foi usado na pesquisa.
- Arrow filtra antes de pandas: dezembro/2023 apenas para warmup e 2024 para desenvolvimento. 8784 candles de 2024, UTC, OHLCV íntegro, sem gaps/duplicações. Nenhum preço de 2025 foi consultado; o holdout UTC `[2025-07-01, 2026-07-01)` permanece fechado.
- Regras originais e evidências D1 de `e81b01c` preservadas. A extensão F2V e os custos foram congelados no commit **02890c9**, antes dos resultados D2/D3/F2V, com hashes em [research2024-extension-lock.json](research2024-extension-lock.json). F2V exige volume fechado >=1,5x média dos 20 candles anteriores, deslocada em uma barra. Nenhuma varredura de parâmetros.
- Freqtrade 2026.9 / CCXT 4.5.84, imagem pelo digest já publicado, motor offline sem rede, 1000 USDT por fold/estratégia, fee nativa 10 bps por lado, startup 200 e 400 horas de dados anteriores. B0 mantém sizing histórico de 99%; os candidatos usam sizing nominal de risco. Drawdown/cooldown persistentes não estão embutidos no backtest nativo.

| Fold | Primeiro open UTC | Último open efetivo UTC |
|---|---|---|
| D1 | 2024-04-01 00:00:00+00:00 | 2024-06-30 23:00:00+00:00 |
| D2 | 2024-07-01 00:00:00+00:00 | 2024-09-30 23:00:00+00:00 |
| D3 | 2024-10-01 00:00:00+00:00 | 2024-12-31 23:00:00+00:00 |

A fronteira final de uma hora a menos é a mesma do framework publicado. Não alegamos cobrir até a meia-noite seguinte. Todos os benchmarks usam as mesmas fronteiras efetivas; caixa tem retorno/DD zero, sem juros. D1 já era observado; D2/D3 também pertencem ao desenvolvimento, sem ajustes depois dos resultados.

## Backtests nativos: taxa de 10 bps por lado

Valores líquidos. DD marcado inclui posições abertas segundo os wallet marks nativos; DD fechado usa a série de trades encerrados. Exposição temporal é fração do período em posição; financeira é média/máximo de notional marcado sobre equity. Comparar retornos exige considerar o sizing diferente da B0.

| Fold/candidato | Trades | Líquido USDT | Retorno % | PF | Acerto % | DD marcado/fechado % | Taxas USDT | Exposição temporal % | Exposição financeira média/máxima % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D1 B0 SMA20/50 + RSI14 | 17 | -185.3353 | -18.5335 | 0.4031 | 23.53 | 24.473/23.759 | 30.0403 | 16.35 | 16.18/99.02 |
| D1 F2 rompimento original | 20 | -9.9112 | -0.9911 | 0.5746 | 40.00 | 1.154/1.093 | 3.5447 | 25.52 | 2.29/9.43 |
| D1 F2V rompimento + volume | 16 | -5.1455 | -0.5145 | 0.7019 | 37.50 | 0.789/0.719 | 2.8461 | 21.16 | 1.91/9.40 |
| D1 F3 reversão/lateral | 16 | -0.9525 | -0.0953 | 0.8978 | 62.50 | 0.495/0.464 | 2.8577 | 10.95 | 0.97/9.10 |
| D1 F1 tendência/regime | 5 | -11.4483 | -1.1448 | 0.0000 | 0.00 | 1.211/1.145 | 0.8771 | 6.87 | 0.61/9.00 |
| D2 B0 SMA20/50 + RSI14 | 17 | 7.0979 | 0.7098 | 1.0314 | 41.18 | 11.890/10.185 | 33.9401 | 25.10 | 24.85/99.03 |
| D2 F2 rompimento original | 22 | 4.4727 | 0.4473 | 1.2481 | 36.36 | 0.918/0.644 | 3.9329 | 31.35 | 2.84/9.82 |
| D2 F2V rompimento + volume | 17 | 6.1297 | 0.6130 | 1.4598 | 41.18 | 0.830/0.527 | 3.0517 | 25.46 | 2.31/9.87 |
| D2 F3 reversão/lateral | 12 | -0.0901 | -0.0090 | 0.9853 | 58.33 | 0.367/0.346 | 2.1462 | 9.70 | 0.86/9.23 |
| D2 F1 tendência/regime | 10 | 4.1500 | 0.4150 | 1.3054 | 30.00 | 1.245/0.946 | 1.7994 | 20.34 | 1.86/10.01 |
| D3 B0 SMA20/50 + RSI14 | 17 | 115.0348 | 11.5035 | 1.8174 | 58.82 | 5.852/3.885 | 35.7368 | 23.56 | 23.32/99.04 |
| D3 F2 rompimento original | 29 | 3.8942 | 0.3894 | 1.1449 | 34.48 | 1.369/0.933 | 5.2077 | 38.42 | 3.48/9.94 |
| D3 F2V rompimento + volume | 26 | 5.4639 | 0.5464 | 1.2252 | 34.62 | 1.162/0.724 | 4.6701 | 32.94 | 3.00/9.94 |
| D3 F3 reversão/lateral | 11 | 4.2007 | 0.4201 | 2.5811 | 72.73 | 0.359/0.145 | 1.9718 | 6.93 | 0.62/9.08 |
| D3 F1 tendência/regime | 13 | 22.1130 | 2.2113 | 2.5839 | 53.85 | 1.368/0.929 | 2.3742 | 39.56 | 3.70/11.44 |

## Sensibilidade e gestão de capital: comparações hipotéticas

Não são operações observadas. Repricing com quantidades fixas preserva os trades nativos e não comprova viabilidade de caixa. O replay sequencial usa apenas oportunidades que viraram trades nativos, caixa inicial 1000, rounding/minimum do snapshot Binance publicado, cap 10%, orçamento nominal 0,5%, stop 5%, cooldown 1h/24h e halt DD 6%. Marcação/liquidação é horária; gaps podem ultrapassar os limites. Custos baixos não aumentam sizing: reserva mínima central permanece. Esse replay não reconstrói sinais suprimidos e não equivale a uma nova execução nativa integral.

| Cenário | Fee base/lado bps | Fee extra/lado bps | Spread total bps | Slippage/lado bps |
|---|---:|---:|---:|---:|
| reference_fee_only | 10 | 0 | 0 | 0 |
| low | 10 | 0 | 4 | 2 |
| central | 10 | 5 | 10 | 10 |
| adverse | 10 | 10 | 20 | 20 |

Execução paga metade do spread + slippage em cada lado. São sensibilidades predefinidas, não spreads medidos em 2024. A fee paper atual de 40 bps/lado não é a fee histórica Binance e não foi misturada nesses experimentos.

### Replay central por fold

| Fold/candidato | Trades | Líquido USDT | Retorno % | PF | Acerto % | DD marcado % | Taxas USDT | Exposição temporal/financeira média % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| D1 B0 SMA20/50 + RSI14 | 17 | -23.5554 | -2.3555 | 0.3176 | 23.53 | 2.923 | 4.4664 | 16.35/1.45 |
| D1 F2 rompimento original | 20 | -16.9386 | -1.6939 | 0.3834 | 35.00 | 1.829 | 5.2908 | 25.52/2.28 |
| D1 F2V rompimento + volume | 16 | -10.7891 | -1.0789 | 0.4788 | 37.50 | 1.079 | 4.2508 | 21.16/1.90 |
| D1 F3 reversão/lateral | 16 | -6.6268 | -0.6627 | 0.4269 | 56.25 | 0.791 | 4.2669 | 10.95/0.97 |
| D1 F1 tendência/regime | 4 | -10.4193 | -1.0419 | 0.0000 | 0.00 | 1.055 | 1.0524 | 6.05/0.54 |
| D2 B0 SMA20/50 + RSI14 | 17 | -4.6527 | -0.4653 | 0.8001 | 41.18 | 1.450 | 4.5446 | 25.10/2.25 |
| D2 F2 rompimento original | 22 | -3.3777 | -0.3378 | 0.8527 | 36.36 | 1.100 | 5.8771 | 31.35/2.83 |
| D2 F2V rompimento + volume | 16 | -4.9013 | -0.4901 | 0.7104 | 31.25 | 1.138 | 4.2699 | 21.84/1.97 |
| D2 F3 reversão/lateral | 12 | -4.3755 | -0.4376 | 0.4741 | 33.33 | 0.593 | 3.2066 | 9.70/0.86 |
| D2 F1 tendência/regime | 10 | 0.5767 | 0.0577 | 1.0360 | 30.00 | 1.384 | 2.6896 | 20.34/1.86 |
| D3 B0 SMA20/50 + RSI14 | 17 | 4.2084 | 0.4208 | 1.2899 | 47.06 | 0.608 | 4.5690 | 23.56/2.10 |
| D3 F2 rompimento original | 28 | -10.5280 | -1.0528 | 0.6874 | 28.57 | 2.335 | 7.4738 | 35.34/3.19 |
| D3 F2V rompimento + volume | 25 | -7.9535 | -0.7954 | 0.7381 | 28.00 | 2.018 | 6.6796 | 29.86/2.70 |
| D3 F3 reversão/lateral | 11 | 0.2849 | 0.0285 | 1.0672 | 54.55 | 0.355 | 2.9468 | 6.93/0.61 |
| D3 F1 tendência/regime | 13 | 17.3471 | 1.7347 | 2.0596 | 38.46 | 1.438 | 3.5505 | 39.56/3.68 |

### Soma das três simulações independentes: sensibilidade de PnL USDT

Cada fold reinicia com 1000 USDT. A soma não é retorno composto de uma carteira contínua. PF agregado usa todos os PnLs individuais, sem média de PF.

| Candidato | Fee apenas | Low | Central | Adverso | Trades central | PF central | Gates reprovados |
|---|---:|---:|---:|---:|---:|---:|---|
| B0 SMA20/50 + RSI14 | -5.7732 | -9.4317 | -23.9998 | -39.0637 | 51 | 0.6681 | PnL/PF central, 2 folds positivos, adverso >=0 |
| F2 rompimento original | -6.0429 | -10.9643 | -30.8443 | -50.5808 | 70 | 0.6332 | PnL/PF central, 2 folds positivos, adverso >=0 |
| F2V rompimento + volume | -3.3999 | -7.4318 | -23.6439 | -40.9017 | 57 | 0.6523 | PnL/PF central, 2 folds positivos, adverso >=0 |
| F3 reversão/lateral | 3.1581 | 0.3495 | -10.7174 | -22.9273 | 39 | 0.5558 | amostra, PnL/PF central, 2 folds positivos, adverso >=0 |
| F1 tendência/regime | 17.2468 | 15.2801 | 7.5045 | -2.0556 | 27 | 1.1752 | amostra, adverso >=0 |

### Buy-and-hold: 1000 USDT e custos de entrada/saída

Concentração de 100% versus cap 10% do replay: comparação informativa, sem risco equivalente. Quantidade BTC arredondada; preços são opens inicial/final do fold. DD de liquidação marcado nos closes horários, com último mark no open efetivo final.

| Fold/cenário | Líquido USDT | Retorno % | DD % | Taxas USDT | Caixa retorno/DD % |
|---|---:|---:|---:|---:|---:|
| D1/reference_fee_only | -119.2697 | -11.9270 | 21.425 | 1.8799 | 0/0 |
| D1/low | -119.9360 | -11.9936 | 21.418 | 1.8786 | 0/0 |
| D1/central | -122.7662 | -12.2766 | 21.422 | 2.8140 | 0/0 |
| D1/adverse | -126.2469 | -12.6247 | 21.418 | 3.7444 | 0/0 |
| D2/reference_fee_only | 9.2871 | 0.9287 | 28.639 | 2.0087 | 0/0 |
| D2/low | 8.4783 | 0.8478 | 28.633 | 2.0074 | 0/0 |
| D2/central | 5.2598 | 0.5260 | 28.642 | 3.0073 | 0/0 |
| D2/adverse | 1.2476 | 0.1248 | 28.645 | 4.0022 | 0/0 |
| D3/reference_fee_only | 473.1696 | 47.3170 | 15.122 | 2.4730 | 0/0 |
| D3/low | 471.8812 | 47.1881 | 15.120 | 2.4712 | 0/0 |
| D3/central | 467.3340 | 46.7334 | 15.123 | 3.7014 | 0/0 |
| D3/adverse | 461.5178 | 46.1518 | 15.124 | 4.9243 | 0/0 |

## Fatos, hipóteses e decisão

Fatos: F1 tem apenas 27 trades no replay central, quatro em D1 (cinco no backtest nativo D1), e agregado adverso de -2,0556 USDT. Seu agregado central +7,5045 USDT e PF 1,1752 não passam os gates de amostra/adversidade. F2/F2V/F3 têm PnL central e adverso negativos; confirmação de volume não resolveu os gates. B0 teve D1 nativo fortemente negativo e comportamento diferente nos folds; reduzir stake reduz perdas monetárias e DD, sem demonstrar edge. Custos transformam pequenas vantagens brutas em perdas.

Hipóteses, ainda não demonstradas causalmente: cruzamentos atrasados/whipsaws em lateralidade; filtros de regime inadequados; rompimentos falsos; reversão capturando movimento contra tendência. A variação entre folds e os poucos trades apoiam investigação, não provam esses mecanismos. Taxas foram contabilizadas, mas ausência de granularidade intrabar impede provar fills/impacto reais.

**Decisão: todos NO-GO.** Não alterar a baseline ou promover candidatos ao operador. Manter o paper atual como baseline explicitamente não lucrativa para validação de infraestrutura. Gates originais continuam: >=50 trades somados e >=10/fold, líquido central positivo/PF >=1,10, >=2 folds positivos, adverso agregado >=0, DD marcado <=6%, causalidade/risco completos.

Pendências antes de qualquer promoção: replay integral de sinais com custos nativos, lookahead/recursive dos candidatos no motor nativo, stress de gaps e incerteza por blocos. Não foram executados nem marcados como aprovados porque os gates econômicos/amostrais já falharam. A auditoria histórica permanece preservada; testes causais unitários não substituem essas análises. Novas hipóteses exigem protocolo anterior aos resultados e orçamento de pesquisa existente, apenas 2024. Se o orçamento se esgotar, não reabrir holdout para corrigir isso.

ML só poderá ser considerado após gates completos, linhagem de dados, controles de causalidade e protocolo congelado. Janeiro–junho/2025 é observado; não selecionar parâmetros nele. A eventual abertura do holdout reservado depende de um protocolo novo aprovado/congelado; nenhuma abertura ocorreu nesta tarefa. Backtesting não promete rentabilidade futura.

## Evidências e reprodução

- [JSON completo: métricas, fills hipotéticos, custos e gates](okx/evidence/research2024/comparison.json).
- Exports nativos completos e SHA256 dos ZIPs: `docs/okx/evidence/research2024/D*-*-native.json`; logs integrais [research2024-native.log](okx/evidence/research2024-native.log) e [research2024-analysis.log](okx/evidence/research2024-analysis.log).
- [Protocolo congelado](research2024-extension.md), [critérios históricos](experiment-plan.md) e [comandos](okx-commands.md). ZIPs/Feathers intermediários ficam ignorados em `user_data/research/`; reprodutibilidade exige o arquivo fonte publicado no ambiente, não novos downloads.
