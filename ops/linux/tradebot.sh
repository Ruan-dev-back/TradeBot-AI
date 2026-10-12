#!/bin/sh
# No dependency installation or shell evaluation of trading arguments.
set -eu
TRADEBOT_CHECKOUT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec python3 "$TRADEBOT_CHECKOUT/scripts/paper_host.py" "$@"
