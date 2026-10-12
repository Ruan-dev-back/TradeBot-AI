# Checklist de implantação e recuperação — execução no host pendente

## Antes de autorizar instalação ou migração

- Escolher PC Windows/WSL2 ou Linux/VPS; confirmar x86_64, região elegível, energia,
  rede, recursos, versões e responsável. Não contratar VPS para contornar geobloqueio.
- Autorizar separadamente dependências, conta/grupo Docker, units/tarefa agendada,
  armazenamento externo, receptor e contatos humanos. Nenhum cadastro foi feito.
- Identificar usuário UID1000 compatível com ftuser; revisar dono/permissões dos
  arquivos. Não chmod777, chown global, container user alternativo ou daemon TCP.
- Revisar commit/source.bundle confiável, digest da imagem, assinatura/pacotes
  oficiais e LF. Conferir baseline/holdout/config/risk sem ler preços reservados.

## Transferência

- Registrar último snapshot/UTC, ordens/posições/risco e T0/T1.
- Parar escritores da origem; snapshot completo de quatro bancos, integrity_check,
  cadeia, reconciliação e SHA. Preservar source.bundle e manifest; não copiar SQLite
  aberto. Um export do journal sozinho não é migração completa.
- Restaurar apenas em destino sem estado; conferir receipt e mesmas datas/IDs,
  peak/halt/cooldown. Origem parada quando destino começar; não duplicar operadores.
- Não restaurar heartbeat/status antigo como saudável. Relatar lacuna real no
  primeiro registro do destino. Não apagar/extender a janela se falhar cobertura.

## Aceite de operação no host definitivo

- setup/preflight/verify-recovery passando; API oficial/TLS/clock/candles válidos.
- Bot/observer funcionais, SQLite íntegros; P&L/fees/ordens vêm do estado nativo,
  fixtures são identificadas. No signal significa zero operações, sem forçar entradas.
- Renderizar/verificar units com caminhos/usuário reais. Validar startup após boot,
  login/logoff e restart; LinuxDocker nativo versus Desktop/WSL externo registrados.
- Timer local e receptor em outro host testados; ausência de heartbeat, API/gaps,
  SQLite/observer/drawdown produzem incidente e ACK humano real autorizado.
- Medir outage/reboot/restore, RPO/RTO e retenção/cópia externa. Monitorar disco/logs
  e a própria infraestrutura do receptor. Manutenção continua na cobertura UTC.
- Completar168h com critérios originais; relatar elapsed e cobertura separadamente.
  Testes desta nuvem não são sete dias, nem deploy ou prova de rentabilidade.

## Gates permanentes

dry_run=true, spot/sem alavancagem, sem chaves privadas, sem API de controle/painel,
cap10%/risco nominal0,5%/stop5%/DD/cooldown publicados, OKX principal e Kraken
alternativa manual independente. Nenhuma alteração de sinal ou parâmetro,
holdout fechado, ML bloqueado e nenhuma promessa de lucro.
