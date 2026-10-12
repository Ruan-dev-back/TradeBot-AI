# Backup, migração e recuperação verificáveis

Novo helper cobre **trades, risco, telemetria e observação**, com ambos os escritores
parados e locks exclusivos. O helper antigo de dois bancos continua preservado;
não é suficiente para migrar uma janela prospectiva. Não copiar SQLite aberto
como se quatro arquivos independentes formassem um snapshot temporal.

## Captura consistente na origem

1. Registrar status atual; confirmar que não há processo paralelo sem lock.
2. Parar o observador conhecido (Ctrl+C, controller ou systemctl) e o bot escolhido.
   Stop gracioso pode cancelar ordens fictícias pendentes conforme config; posições
   preenchidas/estado de risco permanecem. Não fabricar registros para testar.
3. Código revisado e commitado na branch autorizada. Arquivos congelados não mudam.
4. Executar como usuário operacional:

```sh
python3 scripts/paper_host.py backup --exchange okx
python3 scripts/paper_host.py verify-backup --exchange okx --bundle /caminho/complete-UTC
```

O resultado fica em `user_data/research/state-bundles/okx/complete-UTC/`, ignorado.
Contém quatro snapshots via API SQLite backup, `manifest.json` e `source.bundle`
Git com commit exato e histórico. Cada banco passa integrity_check, SHA256,
IDs dry_run/venue/spot sem leverage, reconciliação risk IDs/telemetria/journal,
cadeia de observação e hashes congelados. Código não commitado ou locks ativos
recusam backup. Capturas incompletas permanecem pending, sem ser anunciadas completas.

Verificar checksum do manifest em local confiável e guardar cópia fora do host
após autorização de armazenamento. Hash local detecta corrupção, não é assinatura
externa contra alguém que possa reescrever todos os arquivos. Não há upload,
conta de backup ou credenciais criadas. Não inclui .env, runtime.json, status.json,
proxy, chaves, logs privados ou dataset histórico de pesquisa ignorado.

Retomar a origem com o mesmo estado se ela continuar autorizada, registrando a
lacuna. Em migração definitiva, **não manter duas cópias operando simultaneamente**:
origem parada antes de iniciar destino; conta/venue e cronologia não se unem.

## Transferir e restaurar em host novo

Transferir o diretório completo por meio aprovado, preservando o manifest. No host
destino, instalar/verificar dependências e usuário UID1000. Usar Git do Linux/WSL,
com LF, sem extrair arquivo desconhecido por shell:

```sh
git clone --config core.autocrlf=false --branch feat/realtime-paper-trading /caminho/complete-UTC/source.bundle /home/usuario/TradeBot-AI
cd /home/usuario/TradeBot-AI
python3 scripts/paper_host.py verify-backup --bundle /caminho/complete-UTC
```

Para VPS substituir `/home/usuario/TradeBot-AI` por `/opt/tradebot-ai`, com
proprietário correto. Conferir HEAD igual ao source_commit do manifest e origem
do artefato. O bundle Git é local, sem credenciais; remoto de origem será o bundle,
não GitHub. Adicionar remoto GitHub depois só se necessário/autorizado.

No checkout recém-clonado, ainda sem bancos, restaurar para esse mesmo checkout:

```sh
python3 scripts/paper_host.py restore --bundle /caminho/complete-UTC --target /home/usuario/TradeBot-AI --exchange okx
```

O target pode ter código, mas deve estar sem os quatro bancos/sidecars e escritores
ativos. Contra o checkout ativo, os bancos existentes/locks fazem o comando recusar. Nenhum
arquivo existente é sobrescrito. Copia somente estados esperados, verifica-os e
grava recovery.json com T0/T1, última amostra, timestamp de restauração e SHA do
manifest. Falha parcial remove só arquivos criados pela tentativa; nunca dados
preexistentes. Não restaurar status/heartbeat antigo como evidência de saúde atual.

No destino:

```sh
cd /home/usuario/TradeBot-AI
python3 scripts/paper_host.py verify-recovery
python3 scripts/paper_host.py setup
python3 scripts/paper_host.py preflight
python3 scripts/paper_host.py start
python3 scripts/paper_host.py status
python3 scripts/paper_monitor.py health --exchange okx
python3 scripts/paper_monitor.py report --exchange okx
```

verify-recovery é integridade **offline**, não saúde/API/fills. Start aguarda dados
novos, não limpa risco nem abre nova janela. A primeira amostra detecta a lacuna
e o StartedAt novo; não ganha cobertura por tempo de transferência. T0/T1 seguem
12/10/2026 17:17:10.179088Z e19/10/2026 17:17:10.179088Z para a janela atual.
Se a cobertura não qualificar sete dias, relatar falha/inconclusivo. Nova janela
exige protocolo/autorização; nenhuma será iniciada automaticamente por essas tools.

## Backup recorrente e exercícios

Proposta inicial: diário,7 diários+4 semanais, RPO24h; RTO30min é meta a medir.
Agendador futuro deve parar ambos, fazer backup/verificar, retomar em bloco de
recuperação mesmo se backup falhar e alertar sobre o erro. Parada conta como
indisponibilidade; não apagar esses intervalos. Proteção extra: export online do
journal ao longo do dia, sem confundi-lo com snapshot completo dos quatro bancos.

Testes desta tarefa usam fixtures com posição/ordem pendente/halt/cooldown; restore
drill local real usa cópia de snapshot sem iniciar trading no destino de teste.
Não se chama esse exercício de migração/deploy em PC/VPS. Antes do aceite real:
medir backup, transferência, restore, boot, reconciliação/fees e alertas no host
definitivo. Corrupção/clock/arquivos faltantes devem bloquear start sem reset.
