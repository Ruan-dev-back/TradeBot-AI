# Diagnóstico do ambiente de nuvem

Verificação em 2026-10-11 UTC; resultados do runtime atual, sem presumir publicação
de uma nova versão da configuração do ambiente.

## Estado após a auditoria de risco

O CI do commit remoto `490caa7ab0f4fdaf50507edad29538bcca0231f2` foi confirmado
verde na [execução38163008559](https://github.com/Ruan-dev-back/TradeBot-AI/actions/runs/38163008559).
Essa correção de teste já existente foi incorporada por fast-forward, preservando
o histórico. Os 41 testes originais passaram novamente; a suíte foi ampliada
com os testes da auditoria. Contagem final e evidências em [risk-report.md](risk-report.md).

As análises oficiais de lookahead/recursive agora funcionam com a exchange
offline em cache e dados estritamente de 2024. Os novos relatórios não alteram
a pesquisa financeira publicada. O holdout está fechado; o fluxo atual é
`python3 scripts/run_audit.py`, sem consultas a preços novos. O runner histórico,
a entrada Docker e os scripts diretos de download/validação/backtest recusam o
fluxo anterior antes de tocar candles enquanto durar esta reserva.

A API GitHub retornou403 do proxy. A conferência de CI usou a página pública
GitHub com SHA e status explícitos, sem solicitar tokens. Não foi necessário
alterar configurações do ambiente ou publicar uma versão nova da nuvem.

## Runtime e testes

- Docker 28.4.0, Compose v2.40.3 e daemon operacional.
- Imagem oficial fixada por digest; Freqtrade 2026.9, Python 3.14.7, CCXT 4.5.84.
- Configuração aceita e `SmaRsiStrategy` listada como `OK`.
- 41 testes passaram dentro da imagem; a verificação final do script de setup,
  executado a partir de `/tmp`, também passou com 41 testes.
- Nenhum Docker, pacote de sistema ou dependência Python foi instalado no host.
- `dry_run=true`, spot, BTC/USDT, capital fictício 1000 USDT e credenciais vazias.
  Nenhuma ordem real foi enviada; os backtests offline executam com rede desativada.

## Rede: proxy e exchange são problemas diferentes

| Destino público | Resposta observada | Interpretação |
|---|---|---|
| `api.binance.com/api/v3/time` | HTTP 451 e JSON de localização restrita | Recusa geográfica da Binance; não é HTTP 403 do proxy |
| `data.binance.vision/...zip.CHECKSUM` | HTTP 200 | Arquivos históricos oficiais acessíveis com TLS verificado |
| `data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT` | HTTP 200 | Metadados públicos oficiais acessíveis com TLS verificado |

O erro anterior `CONNECT tunnel failed, response 403` ocorreu no proxy, antes de
uma resposta HTTP da exchange. O download nativo atual alcança a Binance, mas
falha com HTTP 451 ao carregar mercados. Esses erros continuam registrados nos
logs; não foram tratados como dados adquiridos.

O override cloud encaminha nomes das variáveis de proxy e monta a CA gerenciada
como somente leitura; valores não são gravados no repositório. CCXT respeita o
proxy e inclui as CAs do sistema sem desligar TLS. Erros DNS, TLS, timeout, HTTP
403 do destino e HTTP 403 do túnel são classificados separadamente pelo diagnóstico.

O rascunho de configuração inclui `api.binance.com`, `data.binance.vision` e
`data-api.binance.vision`, preservando os presets existentes. Salvar o rascunho não
publica uma versão do ambiente. A conectividade acima foi medida nesta máquina;
persistir a configuração em novas máquinas depende das configurações do ambiente.

## Aquisição e pesquisa desbloqueadas

`python3 scripts/run_research.py` foi executado literalmente. A primeira execução
registrou a falha de API e a ausência do dataset. Após implementar o fallback,
a execução `20261011T175632005777Z` retornou zero: erro nativo preservado, aquisição
oficial alternativa, integridade e os dois backtests verificados.

A alternativa é outra forma de entrega da **mesma Binance spot**, sem misturar
exchanges: ZIPs mensais BTCUSDT/1h, SHA-256 oficiais e snapshot real de mercados do
endpoint público exclusivo de dados. Foram validados 13896 candles UTC, sem gaps,
duplicações ou OHLCV inválidos, com 8784 candles ativos em desenvolvimento e 4344
em validação. As mudanças oficiais de milissegundos para microssegundos são tratadas.

O adaptador de pesquisa fornece metadados reais em cache ao motor nativo Freqtrade;
não altera o motor nem permite trading. O parsing usa a versão fixada do CCXT.
Na investigação foram corrigidos o import do parser nativo e a inicialização dos
campos de margem exigidos internamente pelo parser CCXT, sem consultar margem.

Os exports foram conferidos contra par, mercado spot, alavancagem 1, taxas de 0,1%
por lado, carteira, stop-loss e limites temporais exatos. A extensão do dataset até
2025-07-02 fornece a fronteira do fim do período; não permite entradas posteriores
ao limite de validação. Estratégia e configuração permaneceram congeladas.

Resultados, custos, benchmarks e limitações estão em [results.md](results.md).
Logs integrais e exports públicos ficam em [evidence/](evidence/README.md).

## Limitações e próximo passo

A API principal permanece bloqueada pela exchange; o fallback oficial funciona.
Filtros de preço/lote/notional são atuais, não históricos. Spread, slippage e
impacto não foram modelados. Testes de causalidade por prefixos não substituem
uma execução completa das ferramentas de análise de lookahead.

Comando histórico de aquisição, anterior à reserva do novo holdout; atualmente
recusado pelo bloqueio temporal. O fluxo atual é `python3 scripts/run_audit.py`:

```sh
python3 scripts/run_research.py --source archive
```

Os retornos foram negativos nos dois períodos. Revisar a baseline e reservar um
novo período não observado antes de avaliar qualquer ajuste de parâmetros.

## Atualização: integração de paper trading

A configuração Kraken existente na branch realtime foi preservada. Após adicionar
`api.kraken.com` à permissão de internet, a API pública respondeu200 e os três
pares BTC/USDT, ETH/USDT e SOL/USDT tiveram candles reais horários validados. A
Binance principal continua451 por restrição regional. Foram corrigidos o proxy do
CCXT síncrono, a CA async e campos obrigatórios do schema nativo. A apresentação
fiat foi desativada para remover uma consulta opcional bloqueada ao CoinGecko.

O Freqtrade nativo processou os três pares, com heartbeat RUNNING, healthcheck e
persistência em recriação do container. Isso não comprova disponibilidade24/7.
Detalhes, snapshots, erros anteriores e teste completo: [paper-report.md](paper-report.md).

O rascunho de onboarding recebe instruções testadas de setup/start e a referência
do checkout preservado. A ferramenta de configuração salva rascunhos; o retorno
`requires_publish=true` exige revisão/salvamento e publicação na interface pelo
usuário. Não há requisito de segredo/credencial. Não foi efetuada publicação do
ambiente pelo agente, nem há ferramenta que permita confirmar o estado visual
“Requer atenção”. A conexão Kraken funciona na instância atual independentemente
dessa confirmação de publicação/restauração futura.
