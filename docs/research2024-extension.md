# Extensão de avaliação 2024, registrada antes de D2/D3

Os candidatos de e81b01c e os resultados D1 publicados permanecem preservados.
Concluir D2 (jul–set/2024) e D3 (out–dez/2024), com o mesmo universo Binance
BTC/USDT1h, regras, warmup e fronteira final de uma hora a menos. Não há dados
OKX/Kraken nos experimentos. Nenhum dado de2025 seleciona parâmetros; holdout
UTC [2025-07-01,2026-07-01) permanece fechado.

O F2 original só exige volume positivo, não volume relativo. Não será modificado
silenciosamente após observar D1. Uma hipótese distinta F2V exige volume do candle
fechado >=1,5 vezes a média dos20 candles anteriores (shift1); usa as outras
regras F2 intactas. Esse limiar é fixado antes de executar e não sofrerá varredura.
F2V consome a vaga de combinação ainda não executada: B0,R1,F1,F2,F3,C1,F2V e uma
correção documentada, máximo8 candidatos. Executar F2V também em D1; isso é
novo desenvolvimento em período já observado, nunca validação independente.

Todos os folds começam com1000USDT e taxa nativa10bps por lado. Relatar trades,
retorno líquido, PF, acerto, taxas reconstruídas, exposição temporal e financeira,
DD nativo marcado e de fechamentos. Nenhum retorno será usado isoladamente.

Comparações predefinidas: referência10bps/lado, low (spread4bps, slippage2bps/lado),
central (spread10bps, slippage10bps/lado, extra5bps/lado) e adverso
(spread20bps, slippage20bps/lado, extra10bps/lado). Não usar custos baratos para
selecionar candidato. Dois diagnósticos: repricing de quantidades nativas fixas
(sem afirmar viabilidade de caixa) e replay sequencial de oportunidades nativas
com caixa, rounding/minimos, cap10%, risco nominal0,5%, cooldown1h/24h e DD6%.
O replay usa somente sinais que geraram trades nativos; sinais suprimidos pelo
motor não são reconstruídos. Não equivale a backtest nativo completo com custos
nem constitui validação independente. Se falhar um gate econômico/amostral, não
promover. Mesmo passando provisoriamente, promoção exige replay integral de todos
os sinais, lookahead/recursive nativos, stress de gaps, incerteza por blocos e
congelamento do protocolo conforme a auditoria original.

O replay marca equity por close horário, custo conservador de liquidação e taxas.
DD6% pede saída fictícia no mark disponível; gaps podem exceder6%. Os limites de
spread/slippage são cenários, não medidas de2024. O stop histórico permanece5%.
Nenhuma otimização em D2/D3 ou mudança de regras depois de ver seus resultados.

Buy-and-hold: mesmas datas efetivas, capital1000, custos de ambos os lados;
quantidade arredondada com o snapshot Binance publicado. Caixa: retorno0 e DD0,
sem juros. Relatar período explícito, custos e concentração em meses/folds.
Critérios originais: >=50 trades na soma D1–D3 e >=10 por fold, PF central>=1,10,
líquido central positivo em >=2 folds, agregado adverso>=0, DD marcado<=6% e
controles de causalidade/risco completos. Gates não executados são pendências,
não aprovações. Não reduzir limites para aprovação. ML e operações reais excluídos.
