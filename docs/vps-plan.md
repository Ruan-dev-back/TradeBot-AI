# Plano VPS 24/7, sem deploy

Nenhuma VPS foi contratada, nenhuma credencial foi criada e nenhum serviço
systemd foi instalado. O template em `infra/tradebot-okx-paper.service` é para
revisão posterior. Os bots desta tarefa estão apenas na máquina de desenvolvimento;
processos não têm garantia de sobreviver à publicação/restauração do ambiente.

## Recursos e custos recorrentes

Para um paper spot de três pares de 1h: começar com 2 GiB RAM, Linux x86_64, SSD 40 GiB
ou mais e 1–2 vCPU; preferir 2 vCPU para margem operacional. Não executar a pesquisa
pesada junto do operador. Nesta máquina foram observados cerca de 259 MiB por bot,
em snapshot sem posição, sem demonstrar consumo de pico ou disponibilidade.

Preços oficiais consultados em 11/10/2026, horário de Brasília. Valores de tabela
não são contrato; confirmar região, impostos, câmbio, elegibilidade e SKU antes
de comprar. Fontes e hashes em `docs/okx/evidence/public-sources.json`.

| Opção | Recursos publicados | Base mensal | Extras e observações |
|---|---|---:|---|
| DigitalOcean Basic |1 vCPU,2 GiB,50 GiB SSD,2 TB transferência |US$12 | Backup semanal 20%:US$2,40; totalUS$14,40 sem armazenamento externo |
| DigitalOcean Basic |2 vCPU,2 GiB,60 GiB SSD,3 TB transferência |US$18 | Backup semanalUS$3,60; totalUS$21,60; opção inicial com mais margem CPU |
| DigitalOcean Basic |2 vCPU,4 GiB,80 GiB SSD,4 TB transferência |US$24 | Backup semanalUS$4,80; totalUS$28,80; útil para duas sessões fictícias independentes |
| Hetzner CPX02, NBG 1/FSN 1/HEL 1 |1 core informado no JSON público; RAM/SSD do SKU devem ser confirmados |€5,99 | IPv 4€0,50/mês: base€6,49. Backup e armazenamento externo cotar separadamente; não presumir equivalência ao plano 2 GiB |
| Hetzner CPX12, Europa |1 core informado no JSON público; RAM/SSD confirmar |€11,49 | IPv 4€0,50: base€11,99. Preço varia por localidade/moeda; backup adicional não verificado nesta cotação |

DigitalOcean Spaces publica US$5/mês para 250 GiB e 1 TiB de transferência. Como
armazenamento externo opcional, somaUS$5 às opções DO:US$19,40/26,60/33,80,
antes de impostos/câmbio/excedentes. Não confundir backup do disco com snapshot
consistente dos bancos. Retenção, alertas e eventuais serviços externos podem
adicionar custos. Domínio/painel não são necessários; não expor o bot na web.
Vultr retornou 403 no site de preços; não foi inventada uma cotação alternativa.

Fontes: [DO Droplets](https://www.digitalocean.com/pricing/droplets),
[DO Spaces](https://www.digitalocean.com/pricing/spaces-object-storage),
[Hetzner](https://www.hetzner.com/cloud/) e
[JSON do calculador oficial](https://www.hetzner.com/_resources/app/data/bench/cloud_data.json).
A fonte Hetzner capturada informa preço/CPU/IPv 4, sem RAM/SSD; confirmar esses
campos é condição para recomendar um SKU. Custos de egress além da franquia e
câmbio BRL não foram estimados sem necessidade/volume acordados.

A região deve respeitar os termos e a jurisdição do usuário e da exchange. Não
escolher VPS de outra região para contornar uma recusa geográfica. O sucesso da
API pública nesta nuvem não comprova elegibilidade de uma conta ou de nova VPS.

## Implantação posterior, sujeita à autorização

1. Aprovar provedor, região elegível, recursos e teto de gasto; contratar somente
   depois da autorização. Confirmar acesso oficial OKX e Kraken nessa VPS.
2. Linux atualizado, Docker/Compose, NTP UTC, firewall sem portas do bot; acesso
   administrativo restrito. Não criar chaves de exchange nem configurar modo real.
3. Checkout do commit aprovado em `/opt/tradebot-ai`, imagem pelo digest fixado,
   testes e JSON/Compose validados. Preservar a baseline e o holdout fechado.
4. Config/estratégias/docs somente leitura; diretórios runtime graváveis pelo
   usuário padrão da imagem (`ftuser`). Conferir UID/GID com a imagem antes de
   ajustar permissões; não trocar o usuário Docker arbitrariamente.
5. Inicializar apenas o perfil escolhido. OKX primária; Kraken alternativa manual,
   com seu próprio banco/carteira. Não migrar posições automaticamente entre
   exchanges nem compartilhar SQLite, regras de fee ou histórico de pesquisa.
6. Revisar o template systemd, adaptar caminho e habilitá-lo apenas após autorização.
   `restart: unless-stopped` cobre saída do processo; healthcheck exige candles,
   observação de risco e SQLite. `unhealthy` sozinho não reinicia o container.
7. Registrar commit/digest, último candle, estado/decisões, trades/ordens/taxas e
   restore drill. Testar reboot do host e perda temporária de API em ambiente de
   paper; não declarar 24/7 antes do período monitorado e dos critérios abaixo.

## Monitoramento e resposta

Monitor externo ao host: heartbeat no máximo 60 s, candles fechados dentro da janela
permitida (último open entre 1 h e 2 h 05), risk observation<=30s, quotes públicos com idade<=30s (polling 20s), Docker health e restart
count. Alertar também sobre DD>=3%, halt 6%, disco>80%, erros de SQLite, API/TLS,
clock drift>30 s e backup vencido. O CLI `paper_status.py --exchange okx` fornece
estado e flags; halt pode coexistir com liveness saudável e deve gerar alerta.
Não alterar limites para eliminar alertas.

Alertas externos são proposta; canal, destinatário e credenciais de infraestrutura
serão definidos com autorização, sem mensagens enviadas nesta tarefa. Monitorar
também de fora da VPS para detectar a queda do próprio host. Guardar logs rotativos
por 30 dias como política inicial, ajustando orçamento; incluir taxas e motivos de
rejeição, sem secretos ou valores de proxy.

Falha de API/dados: entradas bloqueadas, preservar posições/bancos, limitar retries,
alertar e voltar somente após dados válidos. Não trocar o endpoint para burlar
geobloqueio. Reinício: reconciliar ordens fictícias e wallet nativos; confirmar
peak/cooldown/halt antes de entradas. Não apagar bancos ou resetar halt para
reativar. Stop/gaps/desconexão podem superar o risco nominal.

## Backup e restauração

RPO inicial 24 h; RTO alvo 30 min, a medir em exercício. Backup diário após parada
controlada do perfil, sem apagar bancos. O helper `scripts/backup_paper.py` adquire
exclusivamente o lock do engine e recusa backup se ele estiver ativo; snapshots
nativos+risco usam a API SQLite backup e PRAGMA quick_check, com SHA 256/manifesto.
Isso foi testado com bancos sintéticos; não foi enviado backup para serviço externo.

Fluxo futuro do agendador: parar o perfil, fazer snapshot, verificar manifesto,
reiniciar em bloco de recuperação inclusive se o backup falhar, executar saúde e
alertar sobre falha. Interrupção deve ser medida. Para OKX, o comando local de
snapshot depois da parada é `python 3 scripts/backup_paper.py --exchange okx`.
Retenção inicial 7 diários +4 semanais, cópia externa com criptografia do provedor
e credenciais de infraestrutura a provisionar somente com autorização. Não usar
cópia de SQLite aberto como se os dois arquivos formassem um snapshot atômico.

Restore drill em diretório isolado: verificar hashes e exchange do manifesto,
PRAGMA integrity_check, restaurar os dois bancos e seus caminhos do mesmo perfil,
conferir posições/ordens e policy SHA, manter halt/cooldown, iniciar dry-run e testar
saúde. A recuperação sintética testou preservação de posição e estado; restauração
real de VPS permanece pendente. Shutdown gracioso cancela ordens pendentes conforme
`cancel_open_orders_on_exit=true`; isso difere de recuperação após crash.

## Critérios de aceite operacional

Antes de afirmar funcionamento 24/7: observação de pelo menos 7 dias do perfil
escolhido, monitor externo/alertas verificados, reboot e outage drills aprovados,
backup/restore medidos e logs sem erros persistentes. Esse período mede operação,
não valida lucratividade ou segurança para dinheiro real. ML e operações reais
seguem bloqueados pelos gates quantitativos; nenhuma hospedagem altera isso.
