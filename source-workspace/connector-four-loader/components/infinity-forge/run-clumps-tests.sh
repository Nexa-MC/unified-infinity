#!/usr/bin/env bash
# Static-byte adaptation + transformed event payload checks, no Minecraft process.
set -euo pipefail
cd "$(dirname "$0")/../.."
java_bin="${JAVA_HOME:-../../.toolchains/jdk-21.0.12.1+1}/bin"
libs="${FORGE_FACADE_HOST_LIBRARIES:-../../run/neoforge-native/libraries}"
neo_dev="${FORGE_FACADE_NEO_DEV_JAR:-build/moddev/artifacts/neoforge-21.1.219.jar}"
out=build/forge-clumps-tests
mkdir -p "$out/classes"
classpath=$(find "$libs" -type f -name '*.jar' -print | sort | paste -sd:)
asm=$(find "$libs/org/ow2/asm" -type f -path '*/9.8/*.jar' -print | sort | paste -sd:)
classpath="$asm:$neo_dev:$classpath"
src=components/infinity-forge/src
identity=components/infinity-core/build/generated/sources/infinity/java/org/sinytra/connector/infinity/BuildIdentity.java
"$java_bin/javac" --release 21 -proc:none -cp "$classpath" -d "$out/classes" "$identity" \
  "$src/main/java/org/sinytra/connector/forge/transform/Forge52Symbols.java" \
  "$src/main/java/org/sinytra/connector/forge/loader/ForgeEventBridge.java" \
  "$src/main/java/org/sinytra/connector/forge/discovery/Forge52Metadata.java" \
  "$src/main/java/org/sinytra/connector/forge/discovery/Forge52Resources.java" \
  "$src/main/java/org/sinytra/connector/forge/discovery/Forge52JarAdapter.java" \
  "$src/test/java/org/sinytra/connector/forge/discovery/ForgeClumpsTransformTest.java"
"$java_bin/java" --add-opens=java.base/java.lang.invoke=ALL-UNNAMED --add-opens=java.base/java.util.jar=ALL-UNNAMED -ea -cp "$out/classes:$classpath" \
  org.sinytra.connector.forge.discovery.ForgeClumpsTransformTest \
  ../../docs/four-loader/forge/upstream/Clumps-forge-1.21.1-19.0.0.1.jar
