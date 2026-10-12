# Operação local prospectiva

Somente paper; não houve deploy. Perfil principal OKX e alternativa manual Kraken,
sem wallet/estado compartilhados. Requisitos: Python3 stdlib no host, Docker/Compose
já instalados, imagem fixada, horário UTC sincronizado e permissões nos bind mounts.
Leia o [protocolo](prospective-protocol.md) antes da primeira coleta. O código do
observador roda separado do bot; não lê chaves, configurações de proxy ou histórico
reservado, não escreve nos SQLite nativos e não envia ordens/mensagens.

## Consultar visão resumida e funcional

```sh
python3 scripts/paper_monitor.py snapshot --exchange okx
python3 scripts/paper_monitor.py snapshot --exchange okx --json
python3 scripts/paper_monitor.py snapshot --exchange kraken
```

Mostra processo verificado, saúde inferida das consultas públicas recentes, candle,
bid/ask com timestamp, sinais/motivo de não entrada, posições, ordens fictícias,
wallet, P&L, taxas e risco. `None` é indisponível, nunca lucro zero inventado.
Fee é reconstruída de notional preenchido e taxa nativa dry-run, sem invoice real.
PnL aberto usa bid/fee de saída e fica indisponível com quote antigo. Snapshot de
wallet e leitura transacional de trades/ordens podem ter pequenos desvios temporais
entre stores; os timestamps são preservados.

## Bot existente e host com proxy gerenciado

```sh
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml run --rm --entrypoint python okxpaper /freqtrade/scripts/check_okx.py
docker compose -f docker-compose.okx.yml -f docker-compose.okx.cloud.yml up -d --wait --wait-timeout 90
python3 scripts/paper_status.py --exchange okx
```

Em PC/VPS de acesso direto omitir `docker-compose.okx.cloud.yml`; não desativar
TLS nem alterar região/endpoints para contornar bloqueios. Kraken usa o Compose
paper existente, check_market.py e `--exchange kraken`. Não iniciar fallback
automaticamente em falha OKX; não migrar ordens/posições entre exchanges.

## Iniciar, acompanhar, interromper e retomar observação

```sh
python3 scripts/paper_monitor.py watch --exchange okx
```

Rodar em terminal dedicado durante a validação local. Ctrl+C encerra somente o
observador, preservando janela e bancos; o bot continua separado. Retomar com o
mesmo comando registra a lacuna. Lock impede dois observadores da mesma carteira.
Não apagar `user_data/observation/okx/` para esconder incidentes. Manifest bloqueia
mudanças dos arquivos congelados antes de novas amostras; não otimizar na janela.
Nunca inferir duração pelo número de candles de warmup.

Em outro terminal, ou por timer independente:

```sh
python3 scripts/paper_monitor.py health --exchange okx
python3 scripts/paper_monitor.py report --exchange okx > user_data/research/prospective-report.json
python3 scripts/paper_monitor.py export --exchange okx
```

`health` retorna não zero se o observador travou, dados/SQLite falharam ou há halt;
`snapshot` não inicia janela; `report` não cria janela que ainda não existe.
`export` usa SQLite backup online, verifica cadeia e SHA, escreve somente em
`user_data/research/observation-exports/` (ignorado), sem alterar o diário ativo.
Guardar o export/manifesto em local independente após definição/autorização de
armazenamento. Backup nativo/risco exige perfil parado pelo helper já publicado;
incluir também telemetria e diário na política futura de retenção/restauração.

## Alertas e execução contínua futura

Eventos raised/recovered são gravados no journal e emitidos no stderr. São alertas
**locais**, não notificações entregues por email/Telegram. O healthcheck original
do container verifica schema3/quotes/candles/wallet/SQLite; halt permanece proteção
ativa, separado da liveness. O monitor o alerta e o health independente falha.
`restart: unless-stopped` não reinicia automaticamente um container unhealthy.

Templates em `infra/tradebot-paper-observer.service`, `tradebot-paper-health.service`
e `tradebot-paper-health.timer`: observer host separado, timer30s, restart limitado
e journald. Não foram instalados/habilitados. Revisar `/opt/tradebot-ai`, permissões,
usuário com acesso Docker e credenciais **de infraestrutura** somente se autorizadas;
acesso ao socket Docker dá privilégios elevados e não deve ser exposto.

PC: impedir suspensão/hibernação, NTP, energia/rede estáveis e disco monitorado.
VPS: seguir [plano já publicado](vps-plan.md), sem contratar ou instalar sem
autorização. Antes de afirmar24/7: monitor fora do host, canal de alerta verificado,
reboot/outage/restore drills e período observado suficiente. Perda do host inteiro
não pode ser detectada por um alerta que roda nele.

Sem sinais: ordens/trades zero, motivo no_entry_signal. Com sinal mas risco inválido:
registrar tentativa recusada, sem relaxar filtros. “Confirmado” em telemetria não
comprova fill. O SQLite nativo é a origem de ordens/trades; nunca manipulá-lo para
produzir resultados. Os testes usam bancos temporários com fixtures identificadas.
