# Plano de experimento antes de ML

Estado: **proposta, sem alteração/implementação da estratégia**. Plano definido
depois da auditoria da baseline; portanto não é protocolo original dessa baseline.
Todos os parâmetros de candidatos serão escolhidos somente com dados de 2024.
Não há promessa de retorno futuro.

## Papéis dos períodos e bloqueio

| Papel | Intervalo UTC, fim exclusivo | Uso permitido nesta etapa |
|---|---|---|
| Aquecimento | 200 horas anteriores ao início de cada janela | Somente indicadores causais |
| Desenvolvimento | 2024-01-01–2025-01-01 | Auditoria e desenho/seleção futura de candidatos |
| Histórico já observado | 2025-01-01–2025-07-01 | Diagnóstico dos exports publicados; não selecionar parâmetros |
| Novo holdout reservado | 2025-07-01–2026-07-01 | Nenhum preço/resultado consultado nesta auditoria |

A reserva consta em [holdout-lock.json](holdout-lock.json). Não existe comando de
unlock nesta etapa. O runner antigo e a entrada Docker recusam downloads,
validações/backtests antigos que poderiam acessar a fronteira reservada ou
sobrescrever o relatório publicado. A auditoria de risco lê somente exports;
a auditoria de indicadores entrega ao pandas/motor apenas dados anteriores a
2025-01-01, filtrados em Arrow, em um diretório separado e com rede desativada.

**Limite da reserva:** o MVP publicado já havia baixado o ZIP mensal de julho/2025
e mantido 24 candles de 2025-07-01 no Feather para a fronteira de encerramento do
backtest anterior. O preço de execução na fronteira foi usado na validação
publicada. Não consultamos esses candles/arquivo mensal nesta etapa; aquisição
prévia não pode ser descrita como inexistente. A reserva operacional passa a valer
agora. O relatório do próximo holdout deve registrar essa fronteira previamente
presente e não afirmar que todos os dados jamais foram adquiridos.

Manter a reserva solicitada de 2025-07-01, sem mudá-la silenciosamente. Não usar
o conhecimento da fronteira para escolher parâmetros. Antes de abrir o holdout,
definir por escrito o tratamento das execuções no início/fim e uma análise de
robustez que exclua a primeira sessão UTC de 24h, sem selecionar por seu resultado.
Esse segundo recorte é apenas robustez do teste, não outro holdout independente.

## Desenvolvimento temporal em 2024

| Fold | Janela anterior disponível para desenho/calibração | Avaliação temporal de desenvolvimento |
|---|---|---|
| D1 | 2024-01-01–2024-04-01 | 2024-04-01–2024-07-01 |
| D2 | 2024-01-01–2024-07-01 | 2024-07-01–2024-10-01 |
| D3 | 2024-01-01–2024-10-01 | 2024-10-01–2025-01-01 |

Folds de desenvolvimento não serão chamados de validação independente após
selecionar candidatos por eles. Uma regra escolhida com D2 não pode ser anunciada
como predefinida para D1. Guardar a cronologia de cada escolha e seu resultado.
Cada avaliação inicia carteira fictícia de 1000 USDT, sem transportar posições,
saldo ou estado de pausas. Dados anteriores alimentam somente os indicadores.
Usar mesmos candles Binance spot, par BTC/USDT, 1h e motor/digest fixados.

Nenhuma seleção usa janeiro–junho/2025. Nem mesmo decidir qual cenário de capital,
filtro ou custo parece melhor nessa janela é permitido como critério de seleção.
Os replays desta auditoria nessa janela são somente diagnóstico retrospectivo.

## Orçamento de candidatos: no máximo oito, registrados antes de executar

| ID | Candidato futuro | Hipótese e mudança isolada |
|---|---|---|
| B0 | Baseline publicada, intacta | Referência; SMA20/50, RSI14 `[50,70)`, saída RSI75/cruzamento, stop5%, stake original |
| R1 | Mesmos sinais + política de capital proposta | Teto10%, orçamento de perda0,5% com custos; revisão DD3%, pausa DD6% |
| T1 | R1 + close anterior acima de SMA200 | Filtro causal de regime; período200 fixado, sem varredura |
| E1 | R1 + saída somente por cruzamento/stop | Testar hipótese de encerramento cedo por RSI; manter entradas |
| E2 | R1 + limiar de saída RSI80 | Comparação predefinida com RSI75, sem buscar o melhor limiar |
| C1 | R1 + pausa24h após três perdas seguidas | Limitar sequências de entradas após perdas; não é aplicada nos replays atuais |
| TC1 | T1 + C1, condicional | Executar somente se ambos passarem os critérios isoladamente |

Há sete candidatos possíveis incluindo B0, com uma vaga máxima para correção
de implementação documentada; não usá-la para procurar outro parâmetro após
resultados ruins. Não há hyperopt, ML, filtro escolhido em 2025 ou ajuste de stop
nesta auditoria. Caso o orçamento seja insuficiente, abrir outro protocolo de
desenvolvimento, registrar o motivo e manter o holdout fechado.

Antes de executar, implementar sizing/pausas em candidatos separados, sem editar
`SmaRsiStrategy` congelada. Conferir quantidades, reservas para taxas, mínimos,
rejeições, perda prevista por stop e sequência de eventos no motor. As tabelas
de 5/10/20% não substituem essa implementação e não incluem essas pausas.

## Custos, benchmark e critérios de seleção

Os cenários `low`, `central`, `adverse` estão definidos no relatório. São stress
tests hipotéticos; OHLCV não mede spread/slippage histórico. Usar `central` como
hipótese principal e `adverse` como robustez, nunca selecionar custos mais baratos
para tornar o resultado positivo. Manter taxa base10bps por lado e registrar
taxas extras separadamente. Benchmark: caixa sem rendimento e buy-and-hold com
o mesmo capital, datas, taxa e hipóteses de execução; comparar também risco.

Limites propostos de engenharia/risco, não leis estatísticas nem metas garantidas:

1. Integridade UTC/1h, ausência de gaps/duplicatas, hashes, custos e limites temporais
   verificados; teste de vazamento conhecido deve falhar (controle negativo).
2. Lookahead nativo sem viés detectado e sem cancelamento por poucas operações;
   recursive com 200 candles: erro RSI ≤0,001 ponto e nenhuma mudança de sinais
   em todas as horas avaliadas. Se um indicador novo precisar de mais histórico,
   mudar e congelar warm-up usando somente desenvolvimento, depois repetir auditoria.
3. No mínimo50 trades fechados na avaliação agregada D1–D3, com ao menos10 por
   fold. Se insuficiente, registrar baixa informação e não baixar limites após olhar resultados.
4. P&L líquido agregado positivo com custos `central`, profit factor ≥1,10,
   resultado líquido positivo em pelo menos dois dos três folds; agregado não
   negativo no cenário `adverse`. Esses critérios não foram executados para candidatos.
5. Drawdown da carteira marcada pelo motor ≤6% no cenário principal, uma posição,
   orçamento nominal por trade ≤0,5% e teto10%, respeitando arredondamento e custos.
   Um stop/gap pode exceder o orçamento; testar shocks −5%, −10%, −20% sem declarar
   limite garantido. Não confundir drawdown de fechamentos do replay com o do motor.
6. Registrar meses/folds positivos e negativos, turnover, contribuição dos stops,
   distribuição de duração e concentração de P&L. Aplicar reamostragem por blocos
   temporais (não trades IID) em 2024, com semente/bloco predefinidos, para estimar
   incerteza; se resultados forem instáveis, declarar inconclusivo.

Ranking somente dos elegíveis: maior resultado líquido com custos centrais em
capital fixo; empate favorece menor drawdown e depois menor turnover. Não abrir
o holdout se nenhum candidato passar. Qualquer escolha depois de olhar o holdout
transforma aquela janela em desenvolvimento observado e exige outro período.

## Congelamento antes de consultar o holdout

Registrar em commit da branch de desenvolvimento, **antes** da aquisição/leitura:

- Código completo do candidato, configuração, sizing, pausas e stop; hashes e
  digest, universo, timeframe, bibliotecas e método de inicialização.
- Candidatos experimentados, ordem, orçamento consumido, folds e critérios acima.
- Custos principais/adversos, capital, benchmark, regras de força de encerramento,
  cobertura de warm-up e regra para candle de execução na fronteira final.
- Métricas, testes de integridade e critério de aceite/rejeição do holdout;
  comparação de robustez excluindo primeira sessão previamente presente.
- Manifesto datado com hashes de estratégia e protocolo, estado `frozen`, sem
  tolerar alteração desses hashes entre o registro e a avaliação.

Depois disso, em tarefa futura, adquirir/validar a janela reservada e executar
uma avaliação única do candidato escolhido; B0 é referência, não concorrente
para selecionar vencedor pelo holdout. Publicar também resultados ruins ou
inconclusivos. Nenhum preço/resultados desse holdout foi solicitado nesta etapa.

## Critérios objetivos para iniciar ML

| Gate | Condição | Estado atual |
|---|---|---|
| Reprodução | CI remoto conhecido, suíte completa, exports e hashes preservados | Verificado nesta auditoria; CI do novo commit local ainda não executado remotamente |
| Causalidade | Lookahead/recursive e controle negativo passam | Verificado para a baseline em 2024; repetir para cada candidato |
| Gestão de capital | Sizing, custos, mínimos e pausas implementados/testados em simulação | Proposta apenas; não implementada |
| Referência econômica simples | Candidato sem ML satisfaz critérios D1–D3 e custos adversos | Não satisfeito; baseline publicada perdeu antes e depois das taxas |
| Amostra/incerteza | Quantidade mínima por fold e incerteza temporal documentada | Ainda não avaliado no novo protocolo |
| Protocolo de ML | Labels/features/validação definidos e versionados antes do treino | Ainda não criado; ML não autorizado nesta etapa |

Quando todos os gates de desenvolvimento passarem, a próxima tarefa pode propor
um protótipo offline de ML, com objetivo incremental claro contra R1/candidato
simples. Não usar ML como justificativa para contornar gates econômicos/de risco.
O protótipo terá novo congelamento antes de acessar o mesmo holdout ainda fechado;
se esse holdout já tiver sido aberto para candidato simples, ele deixa de ser
holdout independente para seleção/validação posterior de ML.

O protocolo de ML deve especificar horizonte de label (por exemplo24h), features
calculadas apenas com candles fechados, custos na definição do alvo, normalização
ajustada somente no treino, split temporal e purga/embargo ≥horizonte máximo do
label entre folds. Não transportar labels de teste para treino. Definir orçamento
de modelos e seeds antes de treino; não procurar o melhor resultado em 2025.
Esses itens são requisitos de planejamento; nenhum modelo ou dataset de treino
de ML foi implementado.

**Decisão atual: não iniciar ML.** Primeiro implementar e avaliar, só em 2024,
a gestão de capital e um candidato simples que passe os gates. Nenhum backtest
autoriza operações reais ou demonstra lucratividade futura.
