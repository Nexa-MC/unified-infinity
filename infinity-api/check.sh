#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")" && pwd)
JAVA_HOME=${JAVA_HOME:-"$ROOT/../.toolchains/jdk-21.0.12.1+1"}
JAVA="$JAVA_HOME/bin/java"
JAVAC="$JAVA_HOME/bin/javac"
JAR="$JAVA_HOME/bin/jar"
rm -rf "$ROOT/build/main" "$ROOT/build/test" "$ROOT/build/examples" "$ROOT/build/benchmark" "$ROOT/build/fabric-example"
mkdir -p "$ROOT/build/main" "$ROOT/build/test" "$ROOT/build/examples" "$ROOT/build/benchmark" "$ROOT/reports"
find "$ROOT/src/main/java" -name '*.java' -print | sort > "$ROOT/build/main-sources.txt"
find "$ROOT/src/test/java" -name '*.java' -print | sort > "$ROOT/build/test-sources.txt"
find "$ROOT/src/benchmark/java" -name '*.java' -print | sort > "$ROOT/build/benchmark-sources.txt"
"$JAVAC" --release 21 -Xlint:all -Werror -d "$ROOT/build/main" @"$ROOT/build/main-sources.txt"
"$JAVAC" --release 21 -Xlint:all,-try -Werror -cp "$ROOT/build/main" -d "$ROOT/build/test" @"$ROOT/build/test-sources.txt"
"$JAVAC" --release 21 -Xlint:all -Werror -cp "$ROOT/build/main" -d "$ROOT/build/examples" "$ROOT/examples/infinity/InfinityTickExample.java"
"$JAVAC" --release 21 -Xlint:all -Werror -cp "$ROOT/build/main" -d "$ROOT/build/benchmark" @"$ROOT/build/benchmark-sources.txt"
"$JAR" --create --file "$ROOT/build/infinity-api-candidate.jar" -C "$ROOT/build/main" .
"$JAVA_HOME/bin/jdeps" -s "$ROOT/build/infinity-api-candidate.jar" | tee "$ROOT/reports/runtime-dependencies.txt"
"$JAVA" -ea -cp "$ROOT/build/main:$ROOT/build/test" dev.unified.infinity.api.EventTests | tee "$ROOT/reports/tests.txt"
"$JAVA" -ea -cp "$ROOT/build/main:$ROOT/build/examples" dev.unified.infinity.examples.InfinityTickExample | tee "$ROOT/reports/example.txt"

FABRIC_BASE="$ROOT/../docs/research/upstream/fabric-api-base-native-0.4.42+6573ed8c19.jar"
if [[ -f "$FABRIC_BASE" ]]; then
  mkdir -p "$ROOT/build/fabric-example"
  "$JAVAC" --release 21 -Xlint:all -Werror -cp "$FABRIC_BASE" -d "$ROOT/build/fabric-example" "$ROOT/examples/fabric/EquivalentFabricTick.java"
  printf 'PASS: Fabric comparison compiled against pinned upstream API base; NOT executed in Minecraft\n' | tee "$ROOT/reports/fabric-comparison.txt"
  sha256sum "$FABRIC_BASE" >> "$ROOT/reports/fabric-comparison.txt"
else
  printf 'SKIP: pinned upstream Fabric API base JAR unavailable; comparison was NOT compiled\n' | tee "$ROOT/reports/fabric-comparison.txt"
fi

if [[ "${1:-}" == "--benchmark" ]]; then
  "$JAVA" -Xms128m -Xmx128m -cp "$ROOT/build/main:$ROOT/build/benchmark" dev.unified.infinity.bench.DispatchBenchmark | tee "$ROOT/reports/dispatch-benchmark.txt"
fi
sha256sum "$ROOT/build/infinity-api-candidate.jar" | tee "$ROOT/reports/jar.sha256"
