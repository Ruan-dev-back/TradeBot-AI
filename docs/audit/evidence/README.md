# Evidências da auditoria de risco

Esta pasta é separada de `docs/evidence/`, que preserva a pesquisa publicada.

- `ci.json`/`ci.log`: CI verde verificado para o commit remoto exato `490caa7`, via
  status explícito e link do commit no HTML público. A API GitHub foi bloqueada
  por CONNECT403 do proxy; badge isolado não foi usado como prova do commit.
- `baseline-41-tests.log`: os 41 testes originais após incorporar a correção
  remota de CI por fast-forward, antes de adicionar os testes da auditoria.
- `tests.log`: suíte ampliada completa, com controles de custos, capital, vazamento,
  integridade da baseline, cache e bloqueio temporal.
- `bias.log`/`bias.json`: saída completa e resultado das classes oficiais
  `LookaheadAnalysis`/`RecursiveAnalysis` com exchange offline real em cache,
  147 prefixos e recursive rolling em todas as horas de 2024.
- `risk-analysis.json`: distribuições, saídas, contabilidade das taxas, todos os
  cenários de exposição/custos e trajetórias de equity após fechamentos.
- `commands.json`/`run-console.log`: comandos e códigos reais do runner de auditoria.
- `legacy-runner-blocked.log`: recusa do fluxo anterior antes de qualquer aquisição
  ou atualização do relatório publicado, enquanto o holdout está reservado.

Os inputs financeiros são exclusivamente os exports publicados de Binance
BTC/USDT spot, 69 trades de 2024 e 41 de janeiro–junho/2025. `../baseline-lock.json`
congela hashes dos sete arquivos publicados que devem permanecer intactos.
Arquivo bruto completo é identificado por hash; somente o recorte de desenvolvimento
é entregue aos indicadores/motor nativo. Não há download ou consulta de preço do
holdout nesta auditoria. A existência anterior do ZIP de julho/2025 e do candle
de fronteira está documentada no plano; não se afirma que nunca foram adquiridos.

O native lookahead ignora force_exit e usa overrides diagnósticos de capital;
não é um novo relatório de retorno da baseline. O recursive nativo compara a
última linha. Zero mudanças rolling refere-se aos dados de desenvolvimento
verificados, não é garantia para outros períodos/indicadores.

Reproduza com `python3 scripts/run_audit.py`. Para reusar um resultado temporal
sem repetir os cálculos, `--reuse-bias` exige os mesmos hashes de inputs, script
de auditoria, adaptador offline, janela e sucesso da análise; resultados antigos
ou relativos a outra janela são recusados. Arquivos em `user_data/` continuam
ignorados. Os outputs de auditoria são separados e nunca substituem a baseline.
