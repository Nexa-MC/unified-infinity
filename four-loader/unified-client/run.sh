#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
attempt="${1:?Pass a fresh approved client attempt number}"
[[ "$attempt" =~ ^[0-9]+$ ]] || exit 2
exec python four-loader/unified-client/direct_launch.py --launch --runtime-slot-approved --attempt "$attempt"
