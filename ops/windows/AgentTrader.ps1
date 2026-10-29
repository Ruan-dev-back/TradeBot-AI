param([Parameter(Mandatory=$true)][ValidateSet('start','stop','status','logs','dashboard','preflight','compare','export','test')][string]$Action)
$ErrorActionPreference='Stop'
$Repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $Repo
switch ($Action) {
  'start' { docker compose -f docker-compose.agenttrader.yml up -d }
  'stop' { docker compose -f docker-compose.agenttrader.yml stop }
  'status' { docker compose -f docker-compose.agenttrader.yml ps }
  'logs' { docker compose -f docker-compose.agenttrader.yml logs --tail 100 }
  'dashboard' {
    Write-Host 'FreqUI: http://127.0.0.1:8081 | usuario: agenttrader'
    Write-Host 'A senha local gerada fica em user_data/agenttrader-v1/runtime.json, campo api_server.password. Nao compartilhe esse arquivo.'
    Start-Process 'http://127.0.0.1:8081'
  }
  'test' { python -m unittest discover -s tests -p 'test_agenttrader_v1*.py' -v }
  default { python scripts/agenttrader_v1.py $Action }
}
if ($LASTEXITCODE) { exit $LASTEXITCODE }
