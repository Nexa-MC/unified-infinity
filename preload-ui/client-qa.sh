#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${DISPLAY:-}" ]]; then
    echo 'Launch this script from the graphical cloud desktop terminal.' >&2
    exit 1
fi
# Uses the separately prepared, official ModDevGradle development launch.
# No launcher credentials, session tokens, synthetic events, or server connection.
exec python tools/client-setup/gradle_client.py --launch --offline runClient > logs/client-setup-runtime.log 2>&1
