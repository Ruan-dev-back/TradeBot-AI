# Preparação de host persistente: resultados e limites

Continuação de `aac10b2`, exclusivamente feat/realtime-paper-trading. Ferramentas
adicionadas fora do código congelado: nenhum sinal, parâmetro, config OKX/Kraken,
política de risco, hash histórico ou holdout foi alterado. Não houve deploy no
computador/VPS, instalação de Docker/systemd, cadastro de serviços ou notificações.

## O que foi preparado

- [Instalação Windows/WSL2 e Linux](host-installation.md): requisitos, UID/permissões,
  LF/ext4, Docker nativo versus Desktop externo, comandos executáveis.
- `scripts/paper_host.py` e wrappers Linux/PowerShell: setup, preflight, start/stop,
  status, export, backup, verify-backup, restore e verify-recovery. Start exige
  quatro bancos e janela existentes; não abre nova janela automaticamente.
- [Backup/recuperação](host-recovery.md): quatro bancos consistentes, código Git
  arquivado, checksums/cadeia, recuperação sem sobrescrever nem restaurar heartbeat
  antigo. T0/T1, peak/halt/cooldown/IDs e ordens/posições são preservados.
- Units corrigidas e renderer: conta não root, ordem bot-pronto antes do observer,
  guard de recuperação e executáveis reais. Modo Desktop não depende de um
  docker.service inexistente. O renderer não instala/habilita units.
- [Monitor externo](external-monitor-design.md): receptor independente, ausência de
  heartbeat, P1/P2, ACK/escalonamento humano. `external_health.py` só gera JSON
  mínimo local, sem sender/endpoint/credenciais ou envio de mensagens.
- [Checklist](host-checklist.md) separa preparação, autorização, migração e aceite.

## Testes e verificações reais

**147 testes passaram; todas as 122 verificações originais preservadas**,25 novas.
[Log completo](host/evidence/tests.log), [baseline anterior](host/evidence/original-122.log)
e [integridade](host/evidence/integrity.json). Incluem quatro bancos, corrupção,
locks, halt/cooldown/ordens/posições, T0/T1 e gap após migração, recusa de ordem
não-dry, UID/arquitetura/Compose inválidos, rollback de cópia parcial, PID reciclado
ou desconhecido e stop SIGINT de um processo controlado isolado. Fixtures não são
operações reais de mercado e não entram nos bancos ativos.

Preflight real Linux/Cloud passou com API OKX oficial, imagem pelo digest,
engineLinux/x86_64, UID1000 e Compose2.40. [Evidência](host/evidence/preflight.json).
A disponibilidade pública não comprova elegibilidade regional de conta.

O primeiro run dos testes novos falhou por mounts ausentes de Compose OKX e infra
na auditoria Docker. Os mounts foram acrescentados somente leitura, sem liberar
rede da suíte; [erro registrado](host/evidence/tests-first-missing-mounts.log).
Nenhuma verificação foi removida/relaxada.

## systemd: estrutura verificada, boot pendente

Os templates anteriores tinham caminhos fixos inadequados nesta nuvem
(`/usr/bin/docker` não existe; CLI está em `/usr/local/bin/docker`), observer sem
ordem explícita após o bot e usuário padrão root. Foram preparados User/Group,
Requires/After e guard que recusa estado ausente. Renderer escolhe caminhos de
executáveis locais; pode substituí-los por caminhos revisados no host definitivo.

Nesta nuvem docker.service continua ausente. Com uma **dependência Docker de
fixture** que executa true, systemd-analyze verificou a estrutura/renderização das
units nativas; isso não é um Docker service real nem prova de startup.
A variante Desktop/engine externo passou a análise estrutural sem essa dependência.
[Erro de caminho anterior](host/evidence/systemd-fixture-verify.log),
[análise renderizada nativa](host/evidence/systemd-rendered-fixture-final.log),
[variante externa](host/evidence/systemd-desktop-structure.log).
Usuário/grupo Docker, PID1, permissões, boot e restart precisam ser testados no
PC/VPS. Nenhuma unit/tarefa foi registrada nesta tarefa.

PowerShell/WSL/Docker Desktop não existem aqui. Os PS1 são preparados e revisáveis,
mas **não executados em Windows**. Não declarar instalação Windows validada pelos
resultados Linux. Host ARM, NTFS/sync/NFS e container user alternativo não são
anunciados compatíveis. Preflight bloqueia arquitetura/UID/Compose inválidos e
/mnt; tipo de filesystem, sync e confiabilidade de rede devem ser verificados
no host definitivo, sem alegar detecção automática de todo armazenamento remoto.

## Backup real e restauração isolada

Foi feita manutenção breve na OKX, sem alterar bancos para fabricar trades.
O controller recusou stop de observer não gerenciado; esse guard permaneceu.
Ctrl+C via sessão da nuvem não encerrou o processo. O próprio observer foi
identificado por argv, UID, start-time e inode/owner do lock no kernel e recebeu
SIGINT; nenhum PID desconhecido ou kill forçado foi usado. Leitura de cwd em proc
não estava permitida; a confirmação usou o lock do arquivo correto.
[Recusa](host/evidence/refused-unmanaged-stop.log),
[verificação](host/evidence/verified-observer-stop.json).

Com ambos os escritores parados, criou-se backup real com integrity_check,
SHA256, cadeia, reconciliação e Git bundle; restore num clone local de código em
`/tmp/tradebot-host-restore-check` preservou exatamente os quatro bancos e a janela.
**Nenhum bot foi iniciado nesse destino de teste.** Isso é drill local, não
migração ou deploy para outro computador.
[Evidência do backup](host/evidence/real-backup-verified.json),
[receipt](host/evidence/real-restore-receipt.json),
[estado recuperado](host/evidence/real-recovered-state.json).

Pacote local pronto para transferência após decisão/autorização:
`/workspace/TradeBot-AI/user_data/research/state-bundles/okx/complete-20261012T180748373459Z.tar.gz`.
Tamanho 634143bytes; SHA256
`a6d91f1b742893531eef1c22d36cbba2b171535ed457ae703509ef4dcbea13fd`; código arquivado no commit
`46cccd18c88c122dc5701922f428cccc680cc991`. [Manifesto do pacote](host/evidence/portable-archive.json).
É snapshot histórico da manutenção, **não** a posição atual futura da origem.
Para migração definitiva, gerar snapshot final e manter origem parada antes de
iniciar destino. Não operar as duas cópias simultaneamente.

A origem retomou pelo start controller com observer gerenciado e saúde funcional.
T0 e T1 são idênticos ao snapshot anterior. O diário registrou monitor_gap e
engine_restart_observed, sem preencher o intervalo perdido.
[Comparação de observação](host/evidence/observation-after-maintenance.json),
[start real](host/evidence/start-after-backup.json).
Verificação de backup simultânea ao start foi recusada pelo lock de operação;
executada depois, no checkout de recuperação, passou. Operações do controller são
serializadas; aguardar operação em curso, ou usar CLI readonly independente para
diagnóstico. Não chamar recusa conservadora de perda de dados.

## Observação atual e pendências

No checkpoint 2026-10-12T18:15:08.995614+00:00 UTC: 113 amostras,
3478.8s decorridos, 3330.0s de intervalos
amostrados e 1 lacuna/restart. Sete dias decorridos: **false**;
janela qualificada: **false**. Último estado saudável; zero trades/ordens/posições,
wallet fictício1000USDT, P&L/fees0 e ausência de sinal. Os números são datados,
não rentabilidade nem promessa24/7. [Checkpoint](host/evidence/observation-final.json).

T0 permanece12/10/2026 17:17:10.179088Z (14:17:10 de Brasília), T1
19/10/2026 17:17:10.179088Z. Transferência/reboot contam como lacunas, sem mudar
essas datas. Nova janela só com autorização/protocolo novo, preservando a antiga.

Pendências concretas: acesso/autorização ao PC ou VPS escolhido, dependências e
UID/permissões locais, teste PowerShell/WSL e startup systemd/boot real, região/API
naquele host, receptor externo e contatos/ACK autorizados, backup externo/retenção,
restore/energia/outage drills e janela168h suficientemente observada. Nenhuma
contratação, notificação ou operação com dinheiro real foi feita. Kraken segue
alternativa manual, carteira e eventual janela independentes; ML/holdout fechado
permanecem bloqueados. CI da implementação está verde no SHA remoto
`fd0b871e24ecec86d1b7bfdf38160053bef408d3`: [run38289960290](https://github.com/Ruan-dev-back/TradeBot-AI/actions/runs/38289960290)
e [evidência de SHA/status/hash](host/evidence/ci-verified.json). API GitHub permanece
bloqueada com CONNECT403; HTML público confirmou o run exato. O commit posterior
apenas registra essa evidência; seu HEAD também será verificado ao finalizar.
