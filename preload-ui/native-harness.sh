#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
REDUCED=false
REPORT=native-harness
if [[ "${1:-}" == "--reduced-motion" ]]; then REDUCED=true; REPORT=native-harness-reduced-motion; fi
export XDG_CACHE_HOME="$PWD/build/cache"
mkdir -p "$XDG_CACHE_HOME"
printf 'NATIVE_HARNESS_DISPLAY=%s\n' "${DISPLAY:-unset}"
CP="$(cat build/classpath.txt)"
while IFS= read -r jar; do CP="$CP:$jar"; done < <(find "$ROOT/run/neoforge-native/libraries" -name '*.jar' -type f | sort)
for artifact in lwjgl lwjgl-glfw lwjgl-opengl; do CP="$CP:$PWD/.deps/$artifact-3.3.3-natives-linux.jar"; done
exec "$ROOT/.toolchains/jdk-21.0.12.1+1/bin/java" -Djava.awt.headless=false -Dunified.infinity.reducedMotion="$REDUCED" -Dunified.infinity.qaDirectory="$PWD/build/native-qa" -Dunified.infinity.progressFile="${PROGRESS_FILE:-$PWD/build/unconnected-progress.json}" -cp "$CP" dev.modcompat.preload.NativeHarness 2>&1 | tee "build/reports/$REPORT.log"
