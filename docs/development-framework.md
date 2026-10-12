# Framework quantitativo de desenvolvimento

Esta revisão acrescenta hipóteses de tendência, rompimento e reversão à média à
auditoria `46d376e`, preservada em `docs/experiment-plan.md`. O universo de pesquisa
continua Binance BTC/USDT spot 1h, com a aquisição publicada verificada por SHA256.
Os candles Kraken atuais pertencem exclusivamente ao paper trading; não substituem
dados Binance e não entram nestes backtests.

## Protocolo e orçamento

As famílias abaixo substituem propostas ainda não executadas E1, E2 e TC1 no
orçamento de pesquisa. Isso ocorre antes de qualquer seleção, sem usar 2025.
O limite permanece oito: B0 original, R1 sizing isolado, F1 tendência, F2 rompimento,
F3 reversão, C1 cooldown isolado, uma combinação condicional e uma correção
documentada de implementação. Não abrir vaga por causa de resultado desfavorável.

| Hipótese fixa | Entrada em candle fechado | Saída e risco |
|---|---|---|
| B0: `SmaRsiStrategy` | SMA20/50 + RSI14 `[50,70)` original | RSI75/cruzamento, stop5%, stake original congelado |
| F1: `TrendDevelopment` | Cruzamento SMA20/50, close>SMA200, RSI `[50,70)` | Cruzamento inverso ou stop5% |
| F2: `BreakoutDevelopment` | Close cruza máxima dos 20 candles anteriores e supera SMA200 | Close abaixo da mínima dos 10 candles anteriores ou stop5% |
| F3: `MeanReversionDevelopment` | Close abaixo de Bollinger20/2 desvios, RSI<30, `abs(SMA20/SMA50-1)<1%` | Close retorna à média20 ou RSI≥50; stop5% |

F1–F3 usam sizing com teto10%, risco nominal0,5% e reserva de custos. São
comparações entre famílias com regras de saída diferentes, não experimentos que
isolam a contribuição de um único indicador. Não há varredura de parâmetros.
As classes recusam entradas fora de 2024 e execução live/dry-run do bot.

| Fold | Histórico anterior disponível | Avaliação de desenvolvimento |
|---|---|---|
| D1 | Janeiro–março/2024 | Abril–junho/2024 |
| D2 | Janeiro–junho/2024 | Julho–setembro/2024 |
| D3 | Janeiro–setembro/2024 | Outubro–dezembro/2024 |

Cada execução começa com 1000 USDT e sem posições. Os 400 candles anteriores ao
início são somente warmup; o motor usa startup200. O scanner Arrow entrega ao
pandas apenas dezembro/2023 e 2024, depois o runner restringe o fold. O candle
final disponível é 23h UTC do dia anterior ao fim exclusivo: há uma hora a menos
na fronteira de execução, documentada em cada manifesto. Não comparar esse
encerramento com o export anual original como se as fronteiras fossem idênticas.

## Custos e limites do runner

O motor nativo executa taxa Binance de 10bps por lado. O sizing reserva mais
5bps de taxa, spread completo10bps e slippage10bps por lado. Essa reserva de
capital não aplica spread/slippage ao preço dos fills do backtest. Para seleção,
ainda faltam replay de custos `central`/`adverse`, benchmark buy-and-hold líquido,
curva marcada e as pausas persistentes do paper. Os resultados brutos do runner
não validam a política de risco completa nem representam execução perfeita.

As hipóteses e os limites de aceite permanecem os da auditoria: no mínimo50
trades agregados e10 por fold, PF central≥1,10, líquido positivo em dois folds,
agregado adverso não negativo, DD marcado≤6%, causalidade e recursive aprovados.
Não reduzir esses limites depois de ver os resultados. Não promover um candidato
a paper ou ML a partir do smoke test D1. D2/D3 não foram executados nesta etapa.

## Comandos restritos

```sh
python3 scripts/development_framework.py
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm \
  --entrypoint python freqtrade /freqtrade/scripts/development_framework.py \
  --candidate trend --fold D1 --execute
```

`baseline`, `trend`, `breakout` e `mean_reversion` são as únicas escolhas;
`D1`, `D2`, `D3` são os únicos folds. Não há intervalo arbitrário, hyperopt ou
comando para abrir holdout. O manifesto registra hashes do código, baseline e
protocolo antes da execução. Saídas ficam em diretório novo sob
`user_data/research/development-experiments/`, sem sobrescrever evidências antigas.

Janeiro–junho/2025 continua observado e não serve para selecionar regras.
O holdout `[2025-07-01, 2026-07-01)` permanece reservado e fechado, inclusive a
ressalva histórica sobre dados de fronteira já adquiridos antes da reserva.
ML segue bloqueado até conclusão do protocolo sem ML, custos, risco e avaliação
de incerteza; nenhum backtest promete retorno futuro.

## Atualização OKX e avaliação completa

O texto acima registra o framework publicado em e81b01c. Nesta continuação,
D1–D3 foram executados para cinco candidatos, incluindo a hipótese F2V separada
de confirmação relativa de volume. As regras originais permanecem intactas;
F2V/custos foram congelados em 02890c9 antes dos novos resultados. Cenários de
custos, exposição financeira, replay de oportunidades com risco/cooldown e
benchmarks foram concluídos. Todos falharam gates; nenhum candidato promovido.
O replay integral de sinais e análises nativas dos candidatos ainda são pendências.
Veja [resultados completos](research2024-results.md),
[protocolo adicional congelado](research2024-extension.md) e
[comandos reproduzíveis](okx-commands.md). Somente Binance 2024; nenhuma mistura
de exchanges ou consulta ao holdout.
