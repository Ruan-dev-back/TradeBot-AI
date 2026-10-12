# Pesquisa futura com controle de múltiplos testes

Plano, não implementação. Nenhum experimento novo, hyperopt ou ML foi executado
nesta etapa. D1–D3 de 2024 já foram observados e todos os candidatos falharam gates;
qualquer alteração usando esses folds é desenvolvimento adaptativo, sem validação
independente. O holdout UTC `[2025-07-01,2026-07-01)` continua fechado. 2025-01 a
2025-06 não seleciona parâmetros. Preços novos da janela prospectiva não são
usados para otimizar, nem por inspeção manual de “melhores trades”.

## Registro cumulativo e orçamento

Preservar a família publicada de no máximo oito hipóteses: B0, R1, F1, F2, F3,
C1, F2V e uma correção documentada. Não criar novas vagas quando um candidato
falhar. Auditar o livro de experimentos antes de qualquer execução futura;
se o orçamento estiver consumido, parar e solicitar um novo escopo previamente
definido, sem liberar o holdout. Correção de instrumentação/P&L do paper não é
um novo parâmetro de estratégia e não torna resultados anteriores validados.

Registro pré-execução obrigatório: ID, hipótese falsificável, regra/limiar único,
universo e fonte, hash do código/config/dataset, folds e warmup, custo primário e
stress, benchmark, tamanho de amostra, métrica primária, rejeições, limite de
tentativas, análise de incerteza e regra de decisão. Guardar também runs falhos,
bugs, descartes e escolhas manuais. Contar toda variação que possa influenciar a
seleção: candidatos, parâmetros, universos/pares e regras de saída. Sensibilidades
predefinidas são diagnósticas; escolher o melhor custo depois de ver resultados
adiciona testes à família e invalida o protocolo.

## Critérios e incerteza

Continuam exigidos: >=50 trades e >=10/fold, PF central >=1,10, líquido central
positivo em pelo menos dois folds, adverso agregado >=0, DD marcado <=6%, risco
com custos, mínimos/arredondamento, cooldown e causalidade completos. Caixa e
buy-and-hold líquido nas mesmas fronteiras; não comparar concentração100% com
cap10% como risco equivalente. Benchmark adicional com 10% BTC e 90% caixa seria
uma proposta futura previamente registrada, não substituição retroativa.

Antes de inferência: replay integral de todos os sinais, custos/fills nativos,
lookahead/recursive de candidatos e stress de gaps. Nenhum deles está aprovado
por haver testes unitários. Incerteza deve respeitar dependência temporal:
proposta de bootstrap por blocos de dez dias UTC em equity diária, comprimento
fixado antes do run, sementes e número de reamostragens registrados. Resultados
de poucos trades não justificam aproximação normal ou intervalo confiante.

Uma única hipótese estatística primária por candidato: excesso líquido sobre
caixa sob o cenário central fixado, com teste unilateral pré-definido e todas as
falhas incluídas. Se houver testes de significância, aplicar Holm–Bonferroni com
FWER5% sobre a **família completa planejada**, incluindo tentativas não publicadas;
sem parar assim que p<0,05 ou remover candidatos perdedores. A validade do teste
base e das premissas de blocos deve ser revisada antes de usá-lo. Não calcular
p-valores retrospectivos nesta etapa e não chamar critérios econômicos de
significância estatística. Correção de multiplicidade não elimina overfitting
adaptativo do desenvolvimento já observado.

## Separação e promoção

Somente 2024 pode apoiar desenvolvimento nesta fase. OKX e Binance não se misturam
no mesmo backtest; transferir uma regra entre venues exige estudo próprio de
metadados, fee, liquidez e execução. Novo período independente futuro deve ser
reservado **antes** de acessar preços/resultados, em etapa expressamente definida.
Não renomear dados já vistos como holdout nem abrir a reserva fechada atual.

Uma estratégia só poderá avançar após gates econômicos/amostrais e operacionais,
controle de multiplicidade, incerteza honesta, protocolo e código congelados e
avaliação independente previamente autorizada. ML permanece bloqueado. Sete dias
de paper validam infraestrutura, não edge ou dinheiro real. Relatar NO-GO quando
necessário e não prometer lucro futuro.
