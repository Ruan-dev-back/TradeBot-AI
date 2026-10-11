# TradeBot AI: execução com mercado ao vivo

## Objetivo
Robô 24/7 para consumir candles e monitorar estratégias em exchange usando dados atuais, inicialmente com **operações simuladas automáticas (dry-run)**. O modo financeiro real requer uma avaliação separada e autorização explícita. O backtesting permanece para validar hipóteses; não é o produto final.

## O que está preparado
- Um serviço Docker independente (`docker-compose.paper.yml`) com Freqtrade nativo em modo `trade --dry-run`, rede habilitada para consultas públicas.
- Configuração independente em `user_data/config.paper.json`, banco SQLite de simulações persistido em `user_data/`.
- Mercado spot, pares BTC/USDT, ETH/USDT e SOL/USDT (disponibilidade a verificar via exchange selecionada).
- Kraken como candidato inicial para teste de conectividade; não há conta ou API vinculada. Não assuma disponibilidade regional, do servidor ou de cada par.
- Apenas 1 posição aberta e 25 USDT fictícios por operação, carteira fictícia de 1.000 USDT; sem alavancagem.
- API de controle remoto desativada e sem secrets; `--dry-run` obrigatório também na linha de comando.
- Estratégia SMA/RSI pré-existente usada SOMENTE para validar o fluxo: falhou no backtest e não é recomendada para dinheiro real.

## Antes de executar, testar acesso ao mercado
```bash
docker compose -f docker-compose.paper.yml config --quiet
docker compose -f docker-compose.paper.yml pull
docker compose -f docker-compose.paper.yml run --rm --entrypoint python papertrade /freqtrade/scripts/check_market.py
```
Teste apenas dados públicos. Se a corretora ou algum par não estiver disponível, altere o candidato no arquivo de configuração **somente para testes simulados**. Nunca contorne restrições geográficas ou termos do provedor.

## Iniciar e acompanhar, somente quando a conexão pública funcionar
```bash
docker compose -f docker-compose.paper.yml up -d
docker compose -f docker-compose.paper.yml logs -f --tail=100
docker compose -f docker-compose.paper.yml ps
docker compose -f docker-compose.paper.yml down
```
O Docker hospedeiro precisa ficar ligado continuamente; GitHub Actions e Codex Cloud não são hospedagem 24/7. Para operar continuamente, escolher VPS com Docker, monitoramento, armazenamento persistente, backups e reinicialização automática. **Não foi realizado deploy e não há processo ativo.**

## Requisitos antes de sequer considerar ordens reais
1. Validar a conectividade da corretora e elegibilidade da conta.
2. Elaborar, comparar e validar estratégias com novo holdout e paper-trading contínuo. Não há estratégia comprovadamente lucrativa.
3. Adicionar kill switch, limites de perdas diárias, limite máximo de posição, alertas, reconciliação de ordens, tolerância a desconexões e logs auditáveis.
4. Simular taxas, spread, slippage e execução falha; estimar risco de ruína.
5. Separar credenciais de código-fonte; usar secrets seguros, API sem saques e escopo mínimo.
6. Auditar integração e realizar aprovação explícita de capital/risco antes de ativar `dry_run=false` em configuração diferente da pesquisa e da simulação.

## Estratégias de pesquisa (nenhuma garantia de lucro)
- Tendência + filtro de regime/volatilidade (reduzir entradas em mercado lateral).
- Rompimento com confirmação de volume e gestão de saída.
- Reversão à média em regime lateral, com limites rigorosos.
Comparar com baseline, buy-and-hold e caixa, usando períodos não vistos e custo realista. Só então avaliar ML (XGBoost/FreqAI) em dados contínuos.
