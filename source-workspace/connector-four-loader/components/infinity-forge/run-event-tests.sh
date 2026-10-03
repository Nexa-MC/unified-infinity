#!/usr/bin/env bash
# Direct javac tests on the pinned native event owner; no Gradle or game launch.
set -euo pipefail
cd "$(dirname "$0")/../.."
java_bin="${JAVA_HOME:-../../.toolchains/jdk-21.0.12.1+1}/bin"
libs="${FORGE_FACADE_HOST_LIBRARIES:-../../run/neoforge-native/libraries}"
neo_dev="${FORGE_FACADE_NEO_DEV_JAR:-build/moddev/artifacts/neoforge-21.1.219.jar}"
bus="$libs/net/neoforged/bus/8.0.5/bus-8.0.5.jar"
fml="$libs/net/neoforged/fancymodloader/loader/4.0.42/loader-4.0.42.jar"
neo="$libs/net/neoforged/neoforge/21.1.219/neoforge-21.1.219-universal.jar"
if [[ ! -x "$java_bin/javac" ]]; then
  echo "Need a Java 21 JDK; set JAVA_HOME if needed" >&2
  exit 2
fi
for dependency in "$bus" "$fml" "$neo" "$neo_dev" "$libs/org/ow2/asm/asm/9.8/asm-9.8.jar"; do
  if [[ ! -f "$dependency" ]]; then
    echo "Missing pinned event-test dependency: $dependency" >&2
    echo "Set FORGE_FACADE_HOST_LIBRARIES and FORGE_FACADE_NEO_DEV_JAR if needed" >&2
    exit 2
  fi
done
out=build/forge-event-tests
mkdir -p "$out/classes" "$out/test-classes"
# The host tree also contains ASM 9.3 leftovers; 9.8 must resolve first.
asm=$(find "$libs/org/ow2/asm" -type f -path '*/9.8/*.jar' -print | sort | paste -sd:)
host=$(find "$libs" -type f -name '*.jar' -print | sort | paste -sd:)
classpath="$asm:$bus:$fml:$neo_dev:$neo:$host"
src=components/infinity-forge/src
"$java_bin/javac" --release 21 -proc:none -cp "$classpath" -d "$out/classes" \
  "$src/main/java/org/sinytra/connector/forge/loader/ForgeEventBridge.java"
"$java_bin/javac" --release 21 -proc:none -cp "$out/classes:$classpath" -d "$out/test-classes" \
  $(find "$src/test/java/org/sinytra/connector/forge/events" -name '*.java' | sort)
"$java_bin/java" -ea -cp "$out/test-classes:$out/classes:$classpath" \
  org.sinytra.connector.forge.events.ForgeEventBridgeTest
"$java_bin/java" -ea -cp "$out/test-classes:$out/classes:$classpath" \
  org.sinytra.connector.forge.events.ForgeNativePickupXpTest
