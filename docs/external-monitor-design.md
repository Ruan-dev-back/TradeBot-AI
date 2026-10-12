# Monitor externo e resposta humana — desenho, sem cadastro ou notificações

Um timer que roda no mesmo host não detecta a perda total desse host. Proposta:
receptor em máquina/rede independente, com relógio sincronizado e armazenamento
próprio de heartbeats; painel/serviço pode ser escolhido depois. Nenhuma conta,
endpoint, webhook, destinatário ou serviço foi cadastrado nesta tarefa.

O host gera payload mínimo, **somente stdout local**:

```sh
python3 scripts/external_health.py --exchange okx
```

Inclui UTC de emissão/engine/candles, saúde funcional, ausência/antiguidade do
observer, códigos de falha e drawdown/halt. Não inclui saldo, P&L, preços, IP,
configuração de proxy ou credenciais. Não há sender HTTP ou mensagem. Receber
payload não significa disponibilidade contínua nem aprovação para dinheiro real.

## Contrato futuro do receptor

Após autorização de provedor/infraestrutura/recipientes: envio HTTPS autenticado
por credencial **de infraestrutura**, sem chave de exchange, TTL60s de envio.
TLS validado; rejeitar payload de esquema inesperado, timestamp no futuro>30s,
identidade desconhecida ou repetição/replay. Receptor deve usar seu relógio para
ausência de heartbeat, não confiar apenas no relógio do host.

Ausência por120s ou três ciclos consecutivos inválidos: incidente P1. O emissor
somente manda “OK” se engine e observer funcionais; não usar container running
como critério. Mesmo se o sender estiver travado, o receptor alerta por ausência.
Guardado histórico de receipt_utc, emitted_utc, assinatura, estado e incidentes.
Receptor precisa de backup/monitoramento próprio e redundância de contato.

| Condição | Alerta humano e ação |
|---|---|
| Host/bot parou ou heartbeat ausente | P1: confirmar energia/rede/Docker e incidente; preservar estados antes de reinício |
| Observer ausente/stale>45s | P1: collector interrompido; retomada mantém janela e registra gap |
| Candles/quotes/risco antigos ou API falhando | P1: entradas bloqueadas; diagnosticar TTL/TLS/proxy/clock/região, sem burlar bloqueio |
| Falha SQLite/persistência/cadeia/hash | P1: parar/reconciliar, preservar evidência; restore de snapshot aprovado, sem fabricar registros |
| DD>=3% | P2: revisar risco/posição; não reduzir proteções |
| Halt DD6% | P1: proteção ativa; não apagar halt/resetar peak para reativar |
| Backup vencido>24h ou disco>80% | P2: corrigir armazenamento, medir impacto/recuperação |

Resposta proposta: alerta primário imediato, ACK humano em5min; sem ACK, segundo
contato em10min. Canal e horários de cobertura precisam ser acordados. Local
stderr/journald **não é prova de entrega humana**. Teste autorizado de notificação,
ACK, perda total do host e falha do receptor será critério antes de afirmar24/7.

Manutenção planejada pode ter aviso no receptor, mas continua contando na
cobertura prospectiva. Não suprimir incidentes para qualificar janela. Sem restart
automático para um halt de risco; retries operacionais limitados, sem fallback
automático Kraken, alteração de parâmetros, ML ou chaves privadas.
