#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
java=.toolchains/jdk-21.0.12.1+1/bin
core=source-workspace/connector-four-loader
mkdir -p four-loader/managed-qsl-tests/build
cp="$core/build/classes/java/main:$core/transformer/build/classes/java/main:$core/components/infinity-core/build/classes/java/main"
for jar in $(find run/neoforge-native/libraries -name '*.jar' | sort); do cp="$cp:$jar"; done
cp="$cp:$(find source-workspace/gradle-cache/caches/modules-2/files-2.1/org.sinytra/forgified-fabric-loader -name '*.jar' | head -1)"
"$java/javac" --release 21 -proc:none -cp "$cp" -d four-loader/managed-qsl-tests/build four-loader/managed-qsl-tests/src/org/sinytra/connector/locator/ManagedQslTest.java
"$java/java" --add-opens=java.base/java.lang.invoke=ALL-UNNAMED -ea -cp "four-loader/managed-qsl-tests/build:$cp" org.sinytra.connector.locator.ManagedQslTest runtime-bundle/build-quilt-candidate/libs/unified-infinity-0.1.0-dev.jar
