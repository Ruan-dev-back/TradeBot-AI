# Instalação e operação em host persistente — sem deploy nesta tarefa

Aplicação reprodutível pela imagem Freqtrade fixada por digest e pelo commit
arquivado no backup. Não há pacotes científicos no host. Dependências de host:
Linux x86_64, Python>=3.10, Git, Docker com engine Linux e Compose>=2.40,
filesystem local e relógio sincronizado. Validados nesta nuvem: Docker28.4,
Compose2.40, Python stdlib, API OKX oficial e os scripts Linux. Windows, WSL2,
reboot e serviços da futura VPS ainda exigem acesso ao equipamento.

## Windows + Docker Desktop/WSL2

Recomendação: Windows11 em versão suportada pelo Docker Desktop, virtualização
ativada, WSL2 atualizado, Ubuntu24.04LTS e Docker Desktop com Linux containers e
integração habilitada nessa distribuição. Reservar pelo menos2GiB para o operador
Linux, com margem adicional para Windows/Docker; PC8GiB+ é um ponto inicial,
não medição de pico. Manter energia/rede e impedir suspensão durante observação.
Docker Desktop normalmente depende de login do usuário; isso difere de boot
autônomo de uma VPS. Verificar licença aplicável, sem cadastro/contratação aqui.

Com autorização no seu PC, PowerShell administrativo:

```powershell
wsl --install --distribution Ubuntu-24.04
wsl --update
wsl --list --verbose
```

Esses comandos modificam Windows e podem pedir reboot; não foram executados na
nuvem. Instalar Docker Desktop a partir do fornecedor, verificar assinatura e
habilitar WSL integration para Ubuntu24.04. Não instalar outro daemon Docker
dentro dessa distribuição ao usar o engine Desktop.

No Ubuntu/WSL, somente se dependências estiverem ausentes e a instalação autorizada:

```sh
sudo apt-get update
sudo apt-get install --yes python3 git ca-certificates
```

Guardar o checkout e os SQLite em `/home/usuario/TradeBot-AI`, **não** `/mnt/c`,
OneDrive, SMB/NFS ou pasta sincronizada. Clonar com Git do WSL e preservar LF:

```sh
git clone --config core.autocrlf=false --branch feat/realtime-paper-trading https://github.com/Ruan-dev-back/TradeBot-AI.git /home/usuario/TradeBot-AI
```

Ou clonar o `source.bundle` do backup conforme [recuperação](host-recovery.md),
que fixa o commit correto. Um clone sozinho não inclui os bancos ignorados nem
a janela. **Restaurar o backup completo antes de start**; não criar T0 novo.

PowerShell, depois de revisar os arquivos:

```powershell
./ops/windows/Check-Host.ps1
./ops/windows/TradeBot.ps1 -Action setup -LinuxRoot /home/usuario/TradeBot-AI
./ops/windows/TradeBot.ps1 -Action verify-recovery -LinuxRoot /home/usuario/TradeBot-AI
./ops/windows/TradeBot.ps1 -Action preflight -LinuxRoot /home/usuario/TradeBot-AI
./ops/windows/TradeBot.ps1 -Action start -LinuxRoot /home/usuario/TradeBot-AI
./ops/windows/TradeBot.ps1 -Action status -LinuxRoot /home/usuario/TradeBot-AI
```

Os dispatchers não instalam recursos nem registram tarefas. Bundles/targets usam
caminhos Linux. Se a política de execução bloquear PS1, revisar os scripts e
resolver com o administrador; não há bypass global automático. Os PS1 não foram
executados nesta máquina, onde PowerShell/WSL não estão disponíveis.

Continuidade: preferir systemd habilitado no WSL2, com units renderizadas em modo
`--external-docker`, ou tarefa agendada **a registrar somente com autorização**.
A tarefa deve executar em foreground `paper_host.py run-observer`, manter processo
supervisionado e reiniciar falhas; não apenas iniciar um background e considerar
a tarefa concluída. Login/Desktop/WSL devem estar disponíveis. Validar logoff,
reboot, suspensão e quedas de rede no PC antes de afirmar continuidade.

## Linux/VPS x86_64

Ubuntu24.04LTS é o alvo de referência. Confirmar região elegível para OKX;
não escolher outra região para contornar uma recusa. A API pública funcionando
nesta nuvem não prova acesso na VPS ou elegibilidade de conta.

Preparação administrativa futura: Python3/Git/CA, NTP, Docker Engine e Compose
pelos pacotes oficiais, usuário operacional e diretório próprio. A instalação do
Docker deve seguir o repositório assinado oficial; registrar versões exatas no
manifesto do host. Não executar scripts remotos via pipe. Nenhum pacote, conta,
grupo ou serviço foi instalado nesta tarefa. Imagem da aplicação é fixada;
o sistema operacional não é anunciado como snapshot bit a bit reproduzível.

O usuário do host/serviços precisa ter o **mesmo UID da imagem ftuser (1000 nesta
imagem)**, pois arquivos SQLite600 devem ser lidos por engine e observador.
Se UID1000 já pertence a uma conta, usar/revisar essa conta; não renumerar usuário
nem fazer chown global. Se livre, administrador pode criar conta dedicada UID1000
em etapa autorizada. Acesso ao grupo docker equivale a privilégios elevados;
não expor socket/daemon TCP. Não usar chmod777 ou trocar `user:` da imagem.

Checkout em `/opt/tradebot-ai`, pertencente a esse usuário, e bancos restaurados.
Executar como o usuário operacional, não root:

```sh
cd /opt/tradebot-ai
sh ops/linux/tradebot.sh setup
sh ops/linux/tradebot.sh verify-recovery
sh ops/linux/tradebot.sh preflight
sh ops/linux/tradebot.sh start
sh ops/linux/tradebot.sh status
```

`setup` apenas obtém a imagem pelo digest e verifica requisitos; não instala Docker.
`preflight` verifica público, TLS/clock/mercados/candles, UID, arquitetura e versão
Compose; falha bloqueia start. Não copia proxy/secretos. `start` exige os quatro
bancos/janela existentes, espera saúde funcional do bot e inicia um único observador.
Não faz deploy remoto nem habilita systemd. Em Codex, overlay é explicitamente
`--cloud`; **não usar esse overlay no PC/VPS direto**.

## Comandos de operação

Todos têm `--exchange okx` por padrão; Kraken é opção explícita/manual.

```sh
python3 scripts/paper_host.py status
python3 scripts/paper_host.py export
python3 scripts/paper_host.py stop
python3 scripts/paper_host.py backup
python3 scripts/paper_host.py verify-backup --bundle /caminho/complete-UTC
python3 scripts/paper_host.py verify-recovery
```

Stop só sinaliza observador criado pelo controller com PID/start-time verificados;
para observador em terminal usar Ctrl+C, para units usar systemctl. Nunca matar PID
desconhecido. Não há kill forçado, reset de risco, ordens reais ou remove-orphans.
Backup exige engine e observador parados; não para automaticamente. Retomar após
manutenção com start e verificar health, sem apagar T0/T1/peak/halt/cooldown.

Kraken preflight/status continuam disponíveis; start/backup prospectivos exigem
um diário Kraken próprio já autorizado. Não reutilizar o diário OKX. A alternativa
nativa pode ser iniciada manualmente pelo Compose Kraken após preflight; nova
janela Kraken exige protocolo/autorização distinta.

## Inicialização automática Linux — preparar, revisar, depois autorizar

No host definitivo, renderizar para diretório novo com usuário real UID1000 e
caminhos de executáveis descobertos nesse host:

```sh
python3 scripts/render_host_units.py --output /tmp/tradebot-units --checkout /opt/tradebot-ai --user usuario --group usuario
systemd-analyze verify /tmp/tradebot-units/*.service /tmp/tradebot-units/*.timer
```

WSL2/Docker Desktop: acrescentar `--external-docker` e usar o checkout em `/home`.
Esse modo verifica o daemon por `docker info --format` sem exigir docker.service
local. Não resolve o Desktop/Windows desligado. `--docker-binary`/`--python-binary`
permitem indicar caminhos revisados; o renderer não instala units.

Após revisão e **autorização para instalar no host**, administrador pode copiar
somente essas quatro units para `/etc/systemd/system`, fazer daemon-reload e
habilitar `tradebot-okx-paper.service`, `tradebot-paper-observer.service` e
`tradebot-paper-health.timer`. Não foi feito aqui. Observer depende do bot pronto;
guards recusam estado ausente antes de criar janela. Timer é independente do
observer, mas não detecta sozinho a perda do host inteiro.

Fontes para requisitos/instalação:
[WSL](https://learn.microsoft.com/windows/wsl/install),
[systemd no WSL](https://learn.microsoft.com/windows/wsl/systemd),
[Docker Desktop WSL2](https://docs.docker.com/desktop/features/wsl/),
[Docker Engine Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
São referências de implantação no computador; o Windows não foi validado na nuvem.
