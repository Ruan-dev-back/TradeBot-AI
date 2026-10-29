# QA da V1 do AgentTrader

Os testes adversariais em `test_agenttrader_v1_qa.py` cobrem os limites de stake e perda planejada com taxas/slippage, bloqueio de configurações live/futures/credenciais e variáveis `FREQTRADE__`, metadados e profundidade de mercado, persistência/exports SQLite e as três alternativas de replay. Também verificam entradas na abertura seguinte, bloqueio sem livro executável, stops no modelo de checkpoints, valores NaN e invariância dos controles de risco a candles ainda não fechados.

`test_agenttrader_v1_freqtrade_qa.py` testa a estratégia carregada no runtime Freqtrade, callbacks fail-closed de entrada/saída, ordens não preenchidas e o alinhamento temporal da série de 1h. O mesmo arquivo é ignorado com indicação explícita quando rodado no Python do host sem Freqtrade; o workflow CI executa-o dentro da imagem Freqtrade fixada.

No host Windows, `python -m unittest tests.test_agenttrader_v1_qa tests.test_agenttrader_v1_freqtrade_qa -v` executou 25 testes: 21 passaram e os 4 testes de integração Freqtrade foram ignorados por falta do pacote no host. O daemon Docker não estava acessível nesta execução local; portanto os testes de integração dependem do passo Docker do CI.

Durante a revisão, os testes detectaram e ajudaram a corrigir: validação de configuração que rejeitava o `userAgent` declarado; perda diária que não incluía o valor de mercado de posições abertas e que podia ser liberada por recuperação no mesmo dia; `False` aceito como metadata de taxa zero; equity de ordens pendentes contada como posição; stops artificiais em buy-and-hold; fills de saída sem livro/tick validados; e avaliação de risco do replay com preço de fechamento futuro. A versão atual rejeita esses casos.

Não houve acesso a endpoints privados, contas de exchange ou ordens. O preflight público OKX foi validado separadamente para BTC/USDT e ETH/USDT. O comparativo retrospectivo reporta sinais e retorno de preço buy-and-hold, mas bloqueia PnL de trades porque não há books históricos executáveis; stops são avaliados em checkpoints de book, sem assumir caminho intrabar. Stops nativos são nominais e gaps podem exceder a perda planejada.
