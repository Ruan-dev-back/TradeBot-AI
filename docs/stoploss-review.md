# Inspeção do stop-loss e congelamento da baseline

## Histórico observado

O último commit remoto da branch existente antes deste trabalho,
`75008e2a0982a4b8abf98f5cae660a9d078b2afd`, tinha `stoploss = -0.03` (3%).
O MVP local que o usuário pediu para preservar já tinha `stoploss = -0.05` (5%)
antes de qualquer backtest financeiro concluído. Esse valor já estava definido no
MVP local e foi mantido nesta continuação; não foi escolhido pelos resultados.

SHA-256 da estratégia preservada:
`b37becb4d3b98242053eaa699c4b744f3f3228865125c0330655b29efea073e6`.
O relatório registra esse hash para os dois períodos. Não houve mudança dos
parâmetros após observar desenvolvimento ou validação, nem hyperopt.

## Justificativa e consequência

5% é o limite nominal fixo desta baseline de pesquisa. Mantê-lo permite executar
e auditar o protocolo já estabelecido, sem misturar correções de aquisição de dados
com seleção de risco a partir dos resultados. Não há evidência de que 5% seja
melhor que 3% ou adequado para execução real; não foi feita essa comparação.

A mudança de 3% para 5% **relaxa** o limite e aumenta a perda nominal tolerada por
operação em aproximadamente 66,7%. Com uma posição que usa cerca de 99% do saldo,
um stop nominal de 5% representa aproximadamente 4,95% da carteira antes de custos,
e não 5% de um orçamento de risco independente. Taxas e o modelo de execução
podem elevar a perda; o backtest cobra 0,1% na compra e na venda. Stop-loss não
garante perda máxima em mercados reais com gaps ou slippage.

## Outras diferenças preexistentes

A baseline local também já usava RSI de entrada `[50, 70)`, saída adicional por
RSI ≥ 75, 200 candles de warm-up, ROI automático desativado e stake dinâmico de
99% do saldo. O remoto anterior usava RSI `(45, 70)`, apenas cruzamento contrário
para saída, 60 candles, ROI escalonado e stake de 100 USDT. Essas diferenças não
foram otimizações feitas nesta continuação: foram preservadas do MVP local.

Os períodos de desenvolvimento em 2024 e validação no primeiro semestre de 2025
também já estavam fixados localmente. Depois de observar a validação, qualquer
alteração de estratégia exige outro período ainda não observado; repetir o mesmo
período com parâmetros escolhidos por seus resultados deixa de ser validação.
