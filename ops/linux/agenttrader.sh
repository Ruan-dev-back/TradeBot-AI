#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:-}" in
  start) docker compose -f docker-compose.agenttrader.yml up -d ;;
  stop) docker compose -f docker-compose.agenttrader.yml stop ;;
  status) docker compose -f docker-compose.agenttrader.yml ps ;;
  logs) docker compose -f docker-compose.agenttrader.yml logs --tail 100 ;;
  dashboard) printf '%s\n' 'FreqUI: http://127.0.0.1:8081 | usuario: agenttrader' 'A senha local gerada fica em user_data/agenttrader-v1/runtime.json, campo api_server.password. Nao compartilhe esse arquivo.' ;;
  test) python3 -m unittest discover -s tests -p 'test_agenttrader_v1*.py' -v ;;
  preflight|compare|export) python3 scripts/agenttrader_v1.py "$1" ;;
  *) printf '%s\n' 'Usage: agenttrader.sh start|stop|status|logs|dashboard|test|preflight|compare|export'; exit 2 ;;
esac
