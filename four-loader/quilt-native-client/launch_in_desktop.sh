#!/usr/bin/env bash
# Run only after the parent assigns both the game-runtime and cloud desktop slot.
set -uo pipefail
cd "$(dirname "$0")/../.."
attempt="${1:?Pass a new client attempt number}"
[[ "$attempt" =~ ^[0-9]+$ ]] || exit 2
out="four-loader/quilt-native-client/logs/client-$attempt"
[[ ! -e "$out" ]] || { echo "Evidence already exists: $out"; exit 2; }
mkdir "$out"
date --iso-8601=seconds > "$out/start-time.txt"
free -m > "$out/memory-before.txt"
cat /sys/fs/cgroup/memory.events > "$out/cgroup-events-before.txt"
python four-loader/quilt-native-client/gradle_client.py --offline prepareClientLaunch > "$out/offline-prepare.log" 2>&1 || exit "$?"
cp run/quilt-native-client/client-launch-inputs.json "$out/prepared-launch-inputs.json"
cp run/quilt-native-client/seed-report.json "$out/original-inputs.json"
python four-loader/quilt-native-client/verify_profile.py --runtime > "$out/prelaunch-verification.json" || exit "$?"
python four-loader/quilt-native-client/gradle_client.py --launch --runtime-slot-approved --offline runClient > "$out/launch.log" 2>&1
status=$?
printf '%s\n' "$status" > "$out/exit-status.txt"
free -m > "$out/memory-after.txt"
cat /sys/fs/cgroup/memory.events > "$out/cgroup-events-after.txt"
if [[ -f run/quilt-native-client/game/logs/latest.log ]]; then cp run/quilt-native-client/game/logs/latest.log "$out/game-latest.log"; fi
python four-loader/quilt-native-client/verify_profile.py --runtime > "$out/postlaunch-verification.json"
printf 'Native Quilt client exited: %s\n' "$status"
exit "$status"
