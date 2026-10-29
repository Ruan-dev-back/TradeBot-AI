# AgentTrader V1

Implementação isolada na branch `feat/agenttrader-v1`. Os arquivos e estados anteriores foram preservados. A V1 usa a imagem Freqtrade já fixada por digest no projeto, a FreqUI dessa imagem e um Compose próprio. Não requer chaves de exchange.

## Política fixa

OKX spot, somente BTC/USDT e ETH/USDT; `dry_run=true`, banca inicial de 100 USDT. Uma posição por vez. O orçamento máximo é 10 USDT, incluindo reserva dos custos assumidos; o valor nominal é reduzido para caber nesse orçamento. Mínimos da exchange nunca justificam aumentar o orçamento.

Stop inicial de 2%, take profit inicial de 4%, risco planejado máximo de 0,50 USDT, limite diário de perdas de 2 USDT e pausa persistente por drawdown de 5% em relação ao pico. Os dias são UTC. Stops e orçamento de perda são controles planejados: gaps, atraso e execução adversa podem ultrapassar a perda estimada. A pausa de drawdown não é apagada por reiniciar o processo.

Custos provisórios: taxa de **0,10% por lado** e slippage adverso de **0,05% por lado**. São hipóteses identificadas; não representam consulta autenticada ao tier da conta. O pré-trade exige metadados de mercado e book recentes, mínimos e incrementos válidos, profundidade e spread compatíveis. Dados desconhecidos ou inconsistentes bloqueiam a entrada. A validação final verifica o tamanho efetivamente calculado pelo Freqtrade, após seu arredondamento e eventual ajuste ao mínimo.

## Sinais

Candles fechados de 5m, EMA 9/21/200 e RSI 14. Entrada long no cruzamento novo da EMA9 acima da EMA21, fechamento acima da EMA200, RSI entre 50 inclusive e 70 exclusive e volume positivo. No candle de 1h já encerrado: fechamento acima da EMA200 e EMA9 acima da EMA21. Saída por cruzamento inverso em 5m ou RSI ≥75, além do stop/ROI e das pausas de risco.

O alinhamento de 1h usa `merge_informative_pair`; a informação horária só fica disponível ao encerrar o candle correspondente. Não há short, futuros, margem, alavancagem, DCA ou aumento de posição. A implementação retrospectiva executa decisões após o fechamento do sinal.

## Correção do histórico inicial (29/10/2026)

`startup_candle_count` foi reduzido de 2400 para **1199 candles por timeframe**.
O DataProvider carrega 1h separadamente: não é necessário transformar a EMA200
horária em 2400 candles de 5m. A decisão, os limites numéricos, os resultados e os
comandos para atualizar a VM estão em [agenttrader-v1-startup.md](agenttrader-v1-startup.md).

## Windows

Na raiz do repositório, com Docker Desktop em modo Linux e engine funcionando:

```powershell
python scripts/agenttrader_v1.py preflight
powershell -NoProfile -File ops/windows/AgentTrader.ps1 start
powershell -NoProfile -File ops/windows/AgentTrader.ps1 status
powershell -NoProfile -File ops/windows/AgentTrader.ps1 logs
powershell -NoProfile -File ops/windows/AgentTrader.ps1 dashboard
powershell -NoProfile -File ops/windows/AgentTrader.ps1 stop
```

FreqUI: `http://127.0.0.1:8081`. A publicação da porta fica restrita ao loopback do host. As credenciais locais da interface são geradas no diretório de estado ignorado pelo Git; não são credenciais OKX. Consulte as instruções do comando `dashboard` após iniciar.

## WSL2 / Linux

Em uma distribuição WSL2 com Docker integrado, a partir do checkout:

```bash
bash ops/linux/agenttrader.sh preflight
bash ops/linux/agenttrader.sh start
bash ops/linux/agenttrader.sh status
bash ops/linux/agenttrader.sh logs
bash ops/linux/agenttrader.sh dashboard
bash ops/linux/agenttrader.sh stop
```

Os comandos não instalam WSL, não alteram a versão padrão e não provisionam VPS.

## Persistência, exportação e comparação

O diretório `user_data/agenttrader-v1/` contém o SQLite nativo de operações, journal de sinais/rejeições, PnL, curva de capital, estado de risco e configuração local da interface. É ignorado pelo Git. Preserve esse diretório entre reinícios; apagar estado não é um procedimento de retomada de risco.

O PnL nativo inclui a taxa configurada do Freqtrade. O journal registra também o PnL ajustado pelo slippage provisório adicional; essa dedução não altera os fills do motor nativo. A exportação inclui operações nativas quando o banco existe. Sinais de teste e PnL sintético não são inseridos no estado operacional real.

```powershell
python scripts/agenttrader_v1.py export
python scripts/agenttrader_v1.py compare
python -m unittest discover -s tests -p 'test_agenttrader_v1*.py' -v
```

A comparação consulta dados públicos recentes da OKX, fora do holdout reservado do repositório, e inclui buy-and-hold e uma baseline EMA21/200. O motor de replay exige snapshots executáveis contemporâneos para simular operações. Candles históricos e um book atual não demonstram a liquidez passada; por isso, a execução real desta etapa produziu contagens de sinais e variação de preço do buy-and-hold, com **PnL comparativo bloqueado**, sem ranking financeiro. O pipeline de PnL é testado com fixtures sintéticas identificadas. A saída pública preservada está em [agenttrader-v1-comparison.json](agenttrader-v1-comparison.json).

## Validação neste ambiente

As evidências de infraestrutura estão em [agenttrader-v1-environment.json](agenttrader-v1-environment.json). A revisão e os testes específicos estão em [agenttrader-v1-qa.md](agenttrader-v1-qa.md).

Em 29/10/2026, o primeiro probe público de instrumentos da OKX recebeu HTTP 403; consultas posteriores do pré-flight V1 passaram para BTC e ETH. O [snapshot público validado](agenttrader-v1-preflight.json) registra orçamento abaixo de 10 USDT e perda planejada próxima de 0,23 USDT para ambos. A consulta de candles recentes também funcionou. O acesso público mostrou intermitência; cada nova entrada requer validação atualizada.

Docker Compose está instalado, mas a engine está indisponível e o Docker Desktop não conseguiu iniciar. O WSL não tem distribuições instaladas e informa versão padrão 1. Portanto, a execução contínua Freqtrade e abertura efetiva da FreqUI permanecem sem validação ponta a ponta neste host. A comparação de PnL histórico ficou bloqueada pela ausência de books históricos contemporâneos. Nenhum trade simulado foi forçado para contornar esses bloqueios.

Saídas simuladas também exigem metadados e book válidos; sem liquidez verificada, ficam pendentes. Isso pode ampliar a perda após o stop nominal. A marcação de preenchimentos parciais depende dos eventos do Freqtrade e ainda precisa ser exercitada na imagem fixada: antes da atualização do contador de entradas preenchidas, a marcação pode atrasar. A existência de uma operação pendente continua bloqueando uma segunda entrada e o orçamento original permanece limitado a 10 USDT.

Os comandos de verificação local, seus resultados e os limites de cobertura estão registrados no relatório QA. A CI foi ampliada para validar o novo JSON/Compose, executar os testes portáveis e repetir a suíte V1 na imagem Freqtrade fixada. A execução remota dessa CI não foi solicitada nem atestada nesta entrega.

Execução final: **21 testes V1 passaram e 4 testes de integração ficaram ignorados explicitamente**, além de **8 testes de segurança legados aprovados**. JSON/Compose, compilação Python, parsing do dispatcher PowerShell e exportação passaram. As saídas e códigos de retorno estão em [agenttrader-v1-tests.json](agenttrader-v1-tests.json).

Binance, OKX Demo API e VPS ficam fora desta etapa. Nenhuma credencial existente foi editada e nenhuma ordem real foi enviada.

## Referências técnicas

- [OKX API V5: instrumentos públicos, books e candles](https://www.okx.com/docs-v5/en/).
- [Freqtrade: callbacks de stake e confirmação final de entrada](https://docs.freqtrade.io/en/stable/strategy-callbacks/).
- [Freqtrade: alinhamento de candles informativos](https://docs.freqtrade.io/en/stable/strategy-customization/).
- [Freqtrade: configuração de dry run e mínimos](https://docs.freqtrade.io/en/stable/configuration/).
