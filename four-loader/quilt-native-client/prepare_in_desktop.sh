#!/usr/bin/env bash
# Execute only in the cloud desktop terminal. No Minecraft JVM is launched.
set -euo pipefail
cd "$(dirname "$0")/../.."
attempt="${1:?Pass a new preparation attempt number}"
[[ "$attempt" =~ ^[0-9]+$ ]] || exit 2
out="four-loader/quilt-native-client/logs/desktop-preparation-$attempt"
[[ ! -e "$out" ]] || { echo "Evidence already exists: $out"; exit 2; }
mkdir "$out"
python four-loader/quilt-native-client/gradle_client.py prepareClientLaunch --stacktrace > "$out/online.log" 2>&1
python four-loader/quilt-native-client/gradle_client.py --offline prepareClientLaunch --stacktrace > "$out/offline.log" 2>&1
python four-loader/quilt-native-client/verify_profile.py --runtime > "$out/verification.json"
python four-loader/quilt-native-client/direct_launch.py --seal > "$out/direct-launch-seal.log"
printf 'Native Quilt client preparation verified offline; no game launch.\n' | tee "$out/complete.txt"
