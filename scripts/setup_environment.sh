#!/bin/sh
# Prepara a imagem de pesquisa sem instalar Docker, Compose ou pacotes no host.
set -eu
TRADEBOT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TRADEBOT_ROOT"
if ! command -v docker >/dev/null 2>&1; then
    echo 'Docker indisponível; instalação requer autorização.' >&2
    exit 1
fi
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.paper.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.audit.yml run --rm freqtrade test
