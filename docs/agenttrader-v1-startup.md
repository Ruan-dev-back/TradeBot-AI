# Inicialização das EMAs do AgentTrader V1

Correção de 29/10/2026: `startup_candle_count=1199`, anteriormente 2400.
A única alteração operacional é esse atributo. EMAs 9/21/200 em 5m e 1h,
RSI14, merge de candles fechados, sinais e limites de risco foram preservados.
O JSON versionado permanece com `dry_run=true`. Nenhum arquivo de credenciais,
configuração runtime ou estado operacional foi acessado ou alterado nesta correção.

## Fundamentação

O [DataProvider do Freqtrade 2026.9](https://github.com/freqtrade/freqtrade/blob/2026.9/freqtrade/data/dataprovider.py)
usa `get_required_startup(timeframe)` para carregar o histórico de cada timeframe.
Sem FreqAI, retorna o mesmo `startup_candle_count`; o histórico horário tem sua
própria janela em horas. A estratégia declara BTC/USDT e ETH/USDT como pares
informativos de 1h e os busca por `get_pair_dataframe`. Não faz resampling de 5m.
Isso também é explicado na [documentação oficial de inicialização](https://www.freqtrade.io/en/stable/strategy-customization/#strategy-startup-period).

A [implementação OKX spot](https://github.com/freqtrade/freqtrade/blob/2026.9/freqtrade/exchange/okx.py)
retorna 300 candles por chamada. O [validador de startup](https://github.com/freqtrade/freqtrade/blob/2026.9/freqtrade/exchange/exchange.py)
calcula `ceil((startup + 1) / 300)` e admite até cinco chamadas. Portanto,
1499 é o máximo e 2400 exigiria nove chamadas. 1199 mais a reserva do candle
aberto cabem exatamente em quatro chamadas por par/timeframe. Essa reserva
não autoriza a estratégia a negociar usando um candle ainda aberto.

200 observações tornam a EMA200 disponível, mas não garantem convergência.
Na TA-Lib, a semente inicial é uma SMA de 200 observações. Depois dela,
`EMA[t] = (2/201)*close[t] + (199/201)*EMA[t-1]`.
Com 1200 observações há 1000 atualizações após a semente: sua influência
remanescente é `(199/201)^1000`, aproximadamente **0,00454% do erro inicial**.
Isso não é um limite universal do erro percentual da EMA em relação ao preço.
As EMAs 9 e 21 convergem mais rapidamente. O RSI também foi comparado.

A janela inicial solicitada é 1199 candles de 5m (99h55m) e, separadamente,
1199 candles de 1h (49d23h). Não é necessário aguardar esses períodos após
iniciar o bot quando o histórico está disponível. O merge só disponibiliza
a informação horária quando o respectivo candle fecha; sua defasagem também
está incluída nos testes. Histórico horário curto mantém a EMA200 como NaN e
o bloqueio existente de entrada continua funcionando.

## Evidência e limites

[Script reproduzível](../scripts/agenttrader_v1_startup_analysis.py),
[testes](../tests/test_agenttrader_v1_startup.py) e
[resultado completo](agenttrader-v1-startup-analysis.json).

A varredura usa três séries determinísticas: oscilação, tendência e mudanças
abruptas entre 100 e 200. São 44 pontos finais por série (132 comparações por
indicador/janela), contra referências de 5001 a 10892 observações. A recorrência
depende da sequência de observações, portanto a varredura vale para cada
timeframe independentemente. A tolerância escolhida é **0,001%** para EMAs.

| Startup | Maior erro relativo da EMA200 na varredura |
| --- | --- |
| 199 | 12,11409% |
| 399 | 2,25429% |
| 599 | 0,27422% |
| 799 | 0,03003% |
| 999 | 0,00559% |
| **1199** | **0,000680%** |
| 1499 | 0,0000339% |

1199 é a menor janela candidata que passou nessa tolerância e economiza uma
chamada frente a 1499. Essa tolerância é um critério de engenharia para as
fixtures, não garantia de igualdade de sinais para qualquer série de preços:
um valor arbitrariamente próximo de um limiar pode mudar uma decisão.

O script executa `RecursiveAnalysis.start()` nativo do Freqtrade, incluindo as
comparações recursivas e de lookahead, com um adaptador que substitui apenas o
carregamento via Backtesting por dados sintéticos em memória. Usa o
`populate_indicators` real e varia separadamente as janelas 5m e 1h. Não chama
`bot_start`, wallets, journal ou APIs. A estratégia operacional deliberadamente
recusa runmodes diferentes de dry-run; essa proteção não foi relaxada para análise.

Na janela 1199, o desvio nativo foi aproximadamente 0,0000157% para EMA200 de
5m e 0,0000670% para EMA200 de 1h. EMAs 9/21 e RSI ficaram iguais ao benchmark
na precisão reportada. Os testes confirmam ausência de alteração retrospectiva
na amostra de lookahead e igualdade dos sinais de entrada/saída nos últimos
50 candles da fixture comparada. Isso não representa teste financeiro de mercado.

Resultados locais:

- Python 3.13.14, Freqtrade 2026.9, TA-Lib 0.8.3, NumPy 2.5.4 e pandas 3.1.0,
  instalados em ambiente virtual isolado: **32 testes V1 aprovados, zero skips**.
- **8 testes legados de segurança aprovados** com o Python do host.
- Sintaxe Python, JSON da evidência, `git diff --check` e
  `docker compose -f docker-compose.agenttrader.yml config --quiet`: aprovados.
- A engine Docker retornou HTTP 500. Não foi executado o container fixado por
  digest nem o CLI completo `freqtrade recursive-analysis` com histórico real
  OKX. O algoritmo nativo foi exercitado conforme descrito acima, sem alegar
  equivalência com uma execução completa do CLI. A imagem tem dependências
  próprias; a repetição dos testes nela está prevista na CI e nos comandos abaixo.

Reproduzir no ambiente virtual local:

```powershell
.venv-startup/Scripts/python -m unittest discover -s tests -p 'test_agenttrader_v1*.py' -v
.venv-startup/Scripts/python scripts/agenttrader_v1_startup_analysis.py
python -m unittest discover -s tests -p 'test_safety.py' -v
```

## Atualizar a VM

O commit é local. Publicar primeiro, no checkout onde foi criado:

```bash
git push origin feat/agenttrader-v1
```

Na VM, a partir da raiz do checkout, com a engine Docker funcionando:

```bash
set -e
git switch feat/agenttrader-v1
git pull --ff-only origin feat/agenttrader-v1
docker compose -f docker-compose.agenttrader.yml config --quiet
docker compose -f docker-compose.agenttrader.yml run --rm --no-deps \
  --entrypoint python agenttrader -m unittest discover -s tests \
  -p 'test_agenttrader_v1*.py' -v
docker compose -f docker-compose.agenttrader.yml run --rm --no-deps \
  --entrypoint python agenttrader /freqtrade/scripts/agenttrader_v1_startup_analysis.py
docker compose -f docker-compose.agenttrader.yml up -d --force-recreate
docker compose -f docker-compose.agenttrader.yml ps
docker compose -f docker-compose.agenttrader.yml logs --tail=100 agenttrader
```

O `set -e` interrompe a sequência se um teste falhar. O serviço usa bind mounts,
portanto não requer build de imagem. O diretório persistente
`user_data/agenttrader-v1/` deve ser preservado: recriar o container mantém o
histórico e as pausas de risco. O dispatcher continua forçando `--dry-run`.
