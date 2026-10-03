#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
JDK="${JAVA_HOME:-$PWD/.toolchains/jdk-21.0.12.1+1}"
mkdir -p integrated-loader/build/test-classes
UPSTREAM="$PWD/docs/research/upstream/connector-2.0.0-beta.17+1.21.1-full.jar"
"$JDK/bin/javac" -proc:none --release 21 -encoding UTF-8 \
  -cp "$UPSTREAM" \
  -d integrated-loader/build/test-classes \
  integrated-loader/src/main/java/org/sinytra/connector/infinity/BoundedBatch.java \
  integrated-loader/src/main/java/org/sinytra/connector/infinity/LoadingPolicy.java \
  integrated-loader/src/main/java/org/sinytra/connector/infinity/LoadProgress.java \
  integrated-loader/src/main/java/org/sinytra/connector/infinity/ResourceScope.java \
  integrated-loader/src/main/java/reloc/net/minecraftforge/fart/internal/AsyncHelper.java \
  integrated-loader/src/test/java/org/sinytra/connector/infinity/*.java \
  integrated-loader/src/test/java/reloc/net/minecraftforge/fart/internal/*.java
"$JDK/bin/java" -ea -cp "integrated-loader/build/test-classes:$UPSTREAM" org.sinytra.connector.infinity.LoadingCoreTest
"$JDK/bin/java" -ea -cp "integrated-loader/build/test-classes:$UPSTREAM" reloc.net.minecraftforge.fart.internal.DirectEntryTest
