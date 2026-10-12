# Integração OKX e operador fictício multiativos

Continuação de `e81b01cb551b2ea8f2133963f8f5abba839fc3bb`, exclusivamente em
`feat/realtime-paper-trading`. A OKX funcionou com API pública oficial e Freqtrade
nativo. Kraken continua funcional e sua configuração publicada permanece intacta.
Nenhum candidato foi promovido após a avaliação de desenvolvimento. Não houve
ML, deploy, criação de credenciais ou ordens reais.

Evidências capturadas em 11/10/2026, horário de Brasília; timestamps técnicos nos
artefatos são UTC (12/10/2026). Não confundir sucesso público com elegibilidade de
uma conta ou garantia de operação contínua.

## Conectividade, TLS, região e metadados

Inicialmente, o proxy recusou CONNECT com 403; após adicionar `www.okx.com` ao
rascunho de rede e propagação da política, apareceu HTTP 403 do provedor com
corpo `error code: 1010`. O User-Agent identificável `TradeBot-AI/0.1 public
research` obteve HTTP 200 no **mesmo host oficial**, com TLS verificado. Não houve
VPN, spoofing de navegador, mudança geográfica ou endpoint alternativo. O erro
1010 sozinho não demonstra uma restrição regional. Binance continua retornando
451 explícito de localização restrita; não foi contornado.

`/api/v5/public/time` e os três instrumentos spot retornaram `code=0`, status
`live`, metadados consistentes com CCXT e diferença de relógio de 0,421s. OHLCV
público: 240 candles fechados por par, de 02/10/2026 00h a 11/10/2026 23h UTC,
sem gaps/duplicações, UTC e 1h, OHLCV validado e >=200 candles de warmup.

Snapshot de preflight; spread/volume/mínimo em USDT variam com o mercado:

| Par spot | minSz | lotSz | tickSz USDT | Mínimo derivado USDT | Spread bps | Volume cotado 24h USDT |
|---|---:|---:|---:|---:|---:|---:|
| BTC/USDT | 0,00001 | 0,00000001 | 0,1 | 0,837655 | 0,011938 | 157100710,27 |
| ETH/USDT | 0,0001 | 0,000001 | 0,01 | 0,253736 | 0,039411 | 137674257,63 |
| SOL/USDT | 0,01 | 0,000001 | 0,01 | 1,1138 | 0,897868 | 40176166,78 |

OKX não informou um `cost.min` genérico nesses mercados; **não foi assumido zero**.
Só derivamos minSz × preço quando minSz/lotSz/tickSz oficiais correspondem a
amount.min/precisões do CCXT, instrumento SPOT/live e campos positivos. Valores
ausentes/inconsistentes bloqueiam entradas. Precisão e mínimo são novamente
verificados depois do arredondamento nativo; não aumentar stake para cumprir um
mínimo que exceda o orçamento de risco.

CCXT informa maker 10 bps e taker 15 bps como metadados estáticos/públicos, sem
tarifa autenticada. A página oficial de fees capturada trouxe uma linha padrão
`Regular user`, maker 20 bps/taker 35 bps (`assetType=6, tradeType=6`); não foi
comprovado que esse contexto corresponde aos pares/região/conta do usuário.
[Tabela e origem](okx/evidence/okx-public-fee-table.json). A política **permanece
40 bps por lado**, com reservas adicionais, sem reduzir proteções pela hipótese
barata do CCXT. Não consultamos `/api/v5/account/trade-fee`, endpoint privado.

## OKX versus Kraken

| Aspecto | OKX | Kraken |
|---|---|---|
| Uso nesta etapa | Primária proposta, API pública oficial verificada | Alternativa preservada e API pública funcionando |
| Pares | BTC/USDT, ETH/USDT, SOL/USDT spot/live | Os mesmos três pares spot/ativos |
| Configuração/estratégia | config.paper.okx.json / OkxPaperStrategy | config.paper.json / MultiAssetPaperStrategy |
| SQLite nativo | tradesv3.paper-okx.sqlite | tradesv3.paper.sqlite |
| Estado de risco | paper-okx/risk.sqlite | paper/risk.sqlite |
| Mínimo de custo | Derivado de minSz oficial quando cost.min ausente | Exige cost.min e amount.min públicos positivos |
| Precisão | Lote/tick oficiais conferidos | Metadados CCXT conferidos na integração publicada |
| Fee paper | 40 bps/lado, tarifa real não autenticada | 40 bps/lado, tarifa real não autenticada |
| Candles analisados no snapshot nativo | 299 por par; últimos 200 validados | 719 por par; últimos 200 validados |
| Sinais/decisões atuais | Último candle sem entrada/saída, no_trade | Último candle sem entrada/saída, no_trade |
| Ordens/trades no banco observado | 0 / 0 | 0 / 0 |
| Risco/sizing | Mesma política e hash da Kraken | Política preservada |

Metadados Kraken conferidos novamente nesta tarefa: amount.min BTC 0,00005,
ETH 0,001 e SOL 0,06; cost.min 0,5 USDT por par (o mínimo efetivo também considera
amount.min × preço), taker público CCXT 26 bps. Não são tarifas autenticadas.
[Preflight Kraken atual](okx/evidence/kraken-market.json) mantém fonte distinta.

Cada perfil tem carteira fictícia independente de 1000 USDT. Não somar resultados
como se houvesse uma única carteira. O plano VPS escolhe uma primária; fallback
é manual, sem migrar posições, ordens ou candles entre exchanges. Dados Binance
de pesquisa permanecem separados dos dados atuais OKX/Kraken.

## Freqtrade, CCXT e modo demo

Versões observadas: Freqtrade **2026.9**, CCXT **4.5.84**, imagem oficial pelo digest
fixado. O adaptador OKX nativo declara spot com margin mode NONE; sua inicialização
e processamento público foram demonstrados. Somente mercados spot são carregados
pelas opções CCXT, WS está desativado e TLS usa a CA gerenciada somente leitura
quando necessária, sem alterar URLs ou imprimir valores de proxy.

A documentação oficial OKX diz que Demo Trading exige API key/secret/passphrase
de demo e header `x-simulated-trading: 1`. CCXT expõe `enable_demo_trading`, mas a
presença do método não comprova integração de ponta a ponta no Freqtrade. Não
executamos nem validamos esse modo autenticado. Configurações demo/sandbox e
headers arbitrários são recusadas pelo projeto. **Freqtrade dry-run local com
dados públicos reais funcionou e atende esta etapa**, sem precisar da demo OKX.
Fontes estáveis/oficiais e hashes em [sources.md](sources.md) e
[public-sources.json](okx/evidence/public-sources.json).

## Operador, decisões e risco

Sinais continuam SMA20/50 + RSI14 [50,70), stop 5%, saída por cruzamento inverso
ou RSI75. `SmaRsiStrategy` histórica permanece congelada. `OkxPaperStrategy`
reutiliza a cópia paper sem mudar sinais. É uma baseline que perdeu dinheiro na
pesquisa Binance, sem resultado financeiro demonstrado para OKX/Kraken.

Bid/ask atual é consultado por REST a cada 20s; decisões usam candles **fechados
de 1h**, com `process_only_new_candles`. Cada resposta pública é limitada a 3s;
timestamp de book, quando presente, é comparado ao recebimento local, não ao início
anterior do callback. Tolerância de 2s para jitter futuro e limite de 30s para
antiguidade. Essa correção evita rejeitar uma resposta OKX nova por ser posterior
ao callback, sem aceitar book antigo ou dez segundos no futuro.

Entradas falham fechadas em erro/timeout, quote antigo, candles inválidos/abertos,
UTC/gaps/duplicatas, volume zero, warmup insuficiente, indicadores inválidos,
metadados desconhecidos, spread/impacto excessivos, wallet/risk antigo e exceções.
`paper_status.py --exchange ...` exige candles, quotes atuais, risco atualizado,
identidade do perfil e SQLite legível; PID sozinho não comprova saúde.

Política preservada: uma posição long por perfil, stake proposto 25 USDT, gasto
reservado <=10% da equity e risco nominal projetado <=0,5% com stop/custos; aviso
DD 3%, halt persistente de entradas e saída fictícia solicitada em DD 6%; cooldown
1h após saída e 24h após três perdas consecutivas. Hash:
`f46f0ade8299a8ca0f04e634cd73c7902d78646a9842853e4c536e8501de85e7`.
Cap é orçamento na entrada, não garantia de exposição marcada constante. Gaps,
latência e slippage podem superar o stop/risco nominal; dry-run não modela fila
real perfeitamente. O motor nativo pode admitir até 5% de slippage nas saídas de
mercado; não se promete perda máxima.

Ordens/trades/preços/fees ficam no SQLite/log nativos; snapshots mostram candles,
quotes, sinais e decisões candidatas. `entry_candidate` não equivale a ordem:
sizing, arredondamento, mínimos e confirmação nativa ainda podem recusá-la.

## Evidências observadas e testes isolados

- [OKX pública: metadados, OHLCV, volumes, spreads](okx/evidence/okx-market.json).
- [OKX atual](okx/evidence/okx-current.json) e [Kraken atual](okx/evidence/kraken-current.json): RUNNING/healthy, candles dos três pares, quotes atuais, risco pronto, zero trades e zero ordens. Há sinais anteriores no warmup, não executados retrospectivamente.
- [Restart real](okx/evidence/restart-validation.json): novos timestamps, mesmos peak/halt/cooldown/losses/IDs/policy SHA e contagens SQLite; posição real fictícia não existia nesse snapshot.
- [Lock nativo](okx/evidence/okx-single-writer.log): segundo escritor recusado, sem iniciar outro motor.
- [106 testes](okx/evidence/tests.log), incluindo os 86 existentes, todos passando. Testes offline de Freqtrade para **ambas** as exchanges geraram entradas/fees fictícias em bancos temporários com sinal de fixture, recuperaram wallet/posição e ordem pendente após nova instância, sem chamar criação privada de ordem. São testes de integração, não trades observados no mercado.
- Risco: cap/risco/mínimos/arredondamento, halt/cooldown persistentes, política incompatível recusada, API/quotes inválidos, clock de recebimento, rejeição de credenciais/demo/options/mode real. Backup SQLite consistente e restauração foram testados com bancos sintéticos, não VPS implantada.
- [Integridade](okx/evidence/integrity.json): sete hashes da baseline, holdout reservado, config Kraken byte a byte e AST de RiskPolicy/RiskState/candidatos originais preservados.

CI **verde** para a implementação `4ce86849b90599041c9343efeacd4db6c58f95c0`,
enviada exclusivamente à branch autorizada: [run 38189151843](https://github.com/Ruan-dev-back/TradeBot-AI/actions/runs/38189151843).
[Verificação](okx/evidence/ci-verified.json) associa SHA remoto/local, URL exata,
status Success e hash do HTML público; não usa apenas badge. A API GitHub nesta
nuvem permanece bloqueada com CONNECT 403; o HTML público permite confirmar o
resultado. Logs completos do run podem exigir login no GitHub; os logs locais
integrais de 106 testes foram preservados. O commit posterior registra esta
verificação/documentação; seu HEAD também deve ser conferido com o comando CI.
Main e feat/mvp-foundation não foram alteradas.

[SQLite ao final](okx/evidence/sqlite-final.json): quick_check dos quatro bancos
retornou ok, equity fictícia 1000 por perfil, risco pronto, zero ordens/trades e
no_trade para os três pares em ambos os perfis.

## Pesquisa e hospedagem

[Resultados D1–D3](research2024-results.md): quinze backtests e cenários de custos,
exposição, fee, benchmark caixa/buy-and-hold. Todos falharam gates; nenhum promovido.
As análises nativas completas de bias/custos de candidatos continuam pendentes,
explicitamente sem aprovação. Holdout permanece fechado, 2025 observado não foi
usado para seleção.

[Plano VPS](vps-plan.md): Docker/systemd, persistência, backups, alertas e
recuperação; preços oficiais e limitações da cotação. DigitalOcean inicial com
2vCPU/2GiB custa US$18/mês + US$3,60 backup semanal, ou US$26,60 incluindo storage
externo opcional de US$5, antes de impostos/câmbio. Nenhuma contratação/deploy.
Os containers de desenvolvimento não demonstram disponibilidade 24/7.

## Pendências para qualquer etapa com dinheiro real

Primeiro completar os gates quantitativos e causalidade sem flexibilizá-los,
protocolo e validação independente pré-registrados; congelar regras antes de
qualquer avaliação reservada autorizada. Depois testar operação monitorada,
reboot/outages, backup/restore e reconciliação na VPS elegível. Região e tarifas
de conta não foram verificadas; isso exigiria uma etapa autorizada distinta.
Integração pública/paper não basta para aprovar execução real. Este projeto
continua sem credenciais, sem alavancagem e `dry_run=true`; nenhuma proteção foi
reduzida para gerar trades. Não há promessa de rentabilidade.
