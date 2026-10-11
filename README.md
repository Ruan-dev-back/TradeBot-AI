# TradeBot AI

Laboratório de estratégias quantitativas para BTC/USDT usando **Freqtrade** (Python). O MVP executa **backtesting e simulação com capital fictício**, sem habilitar ordens reais.

## Escopo atual
- Mercado spot BTC/USDT, candles de 1 hora.
- Estratégia de referência: cruzamento de SMA(20/50) filtrado por RSI(14), stop-loss de 3%, take-profit escalonado.
- Carteira fictícia de 1.000 USDT e posição nominal de 100 USDT.
- Sem Machine Learning ou LLM nesta etapa: primeiro validamos o motor e métricas.

## Pré-requisitos
Docker com Docker Compose. Execute na raiz do repositório.

```bash
docker compose pull
docker compose run --rm freqtrade list-strategies --config user_data/config.json
docker compose run --rm freqtrade download-data --config user_data/config.json --pairs BTC/USDT --timeframes 1h --days 730
docker compose run --rm freqtrade backtesting --config user_data/config.json --strategy SmaRsiStrategy --timerange 20250101-20260101
docker compose run --rm freqtrade backtesting --config user_data/config.json --strategy SmaRsiStrategy --timerange 20260101-20261001
```

**Importante:** são períodos propostos para desenvolvimento e validação, não resultados de testes. A disponibilidade histórica depende da exchange e da API. Registre a versão do Freqtrade, datas efetivamente disponíveis, taxas, número de operações, resultado líquido, drawdown e benchmark buy-and-hold. Não ajuste parâmetros com base no período de validação.

## Segurança
`dry_run: true`, `initial_state: stopped`, API desabilitada e nenhuma credencial real. O comando padrão do Compose configura o modo simulado, mas não o execute até revisar as configurações. Não armazene segredos no GitHub. **Não existe garantia de lucro.**

## Próximos passos
1. Executar a instalação e os dois backtests em ambiente com Docker.
2. Documentar resultados reais e comparar com comprar e manter.
3. Adicionar testes automatizados e, somente depois, experimentos de ML com divisão temporal rigorosa.
