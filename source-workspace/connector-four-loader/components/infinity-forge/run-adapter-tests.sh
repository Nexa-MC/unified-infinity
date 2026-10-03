#!/usr/bin/env bash
# Static ASM/metadata/cache tests against the pinned production host libraries.
# No Gradle daemon or Minecraft process is started.
set -euo pipefail
cd "$(dirname "$0")/../.."
java_bin="${JAVA_HOME:-../../.toolchains/jdk-21.0.12.1+1}/bin"
libs="${FORGE_FACADE_HOST_LIBRARIES:-../../run/neoforge-native/libraries}"
out=build/forge-adapter-tests
mkdir -p "$out/classes"
asm=$(find "$libs/org/ow2/asm" -type f -path "*/9.8/*.jar" -print | sort | paste -sd:)
classpath=$(find "$libs" -type f -name '*.jar' -print | sort | paste -sd:)
classpath="$asm:$classpath"
src=components/infinity-forge/src
identity=components/infinity-core/build/generated/sources/infinity/java/org/sinytra/connector/infinity/BuildIdentity.java
"$java_bin/javac" --release 21 -proc:none -cp "$classpath" -d "$out/classes" "$identity" \
  "$src/main/java/org/sinytra/connector/forge/transform/Forge52Symbols.java" \
  "$src/main/java/org/sinytra/connector/forge/discovery/Forge52Metadata.java" \
  "$src/main/java/org/sinytra/connector/forge/discovery/Forge52Resources.java" \
  "$src/main/java/org/sinytra/connector/forge/discovery/Forge52JarAdapter.java" \
  "$src/test/java/org/sinytra/connector/forge/discovery/ForgeAdapterTest.java"
"$java_bin/java" -ea -cp "$out/classes:$classpath" \
  org.sinytra.connector.forge.discovery.ForgeAdapterTest \
  ../../four-loader/forge-probe/build/unified-forge-probe-0.1.0.jar
