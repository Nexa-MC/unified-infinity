#!/usr/bin/env bash
# Compile and exercise the facades against the exact installed host libraries.
# This runner neither starts Gradle nor launches Minecraft.
set -euo pipefail
cd "$(dirname "$0")/../.."
java_bin="${JAVA_HOME:-../../.toolchains/jdk-21.0.12.1+1}/bin"
libs="${FORGE_FACADE_HOST_LIBRARIES:-../../run/neoforge-native/libraries}"
neo_dev="${FORGE_FACADE_NEO_DEV_JAR:-build/moddev/artifacts/neoforge-21.1.219.jar}"
if [[ ! -x "$java_bin/javac" || ! -d "$libs" || ! -f "$neo_dev" ]]; then
  echo "Need a Java 21 JDK, exact host libraries, and Neo 21.1.219 mapped dev artifact" >&2
  echo "Set JAVA_HOME, FORGE_FACADE_HOST_LIBRARIES and FORGE_FACADE_NEO_DEV_JAR if needed" >&2
  exit 2
fi
out=build/forge-facade-tests
mkdir -p "$out/classes" "$out/fixture-classes" "$out/test-classes"
classpath=$(find "$libs" -type f -name '*.jar' -print | sort | paste -sd:)
src=components/infinity-forge/src
"$java_bin/javac" --release 21 -proc:none -cp "$classpath" -d "$out/classes" \
  $(find "$src/main/java/org/sinytra/connector/forge/loader" -name '*.java' | sort)
"$java_bin/javac" --release 21 -proc:none -cp "$neo_dev:$classpath" -d "$out/classes" \
  $(find "$src/mod/java/org/sinytra/connector/forge/runtime" -name '*.java' | sort)
tests="$src/test/java/org/sinytra/connector/forge"
"$java_bin/javac" --release 21 -proc:none -cp "$out/classes:$classpath" -d "$out/fixture-classes" \
  "$tests/loader/fixture/ForgeEntrypoints.java"
printf 'Manifest-Version: 1.0\nAutomatic-Module-Name: forge.facade.fixtures\n' > "$out/MANIFEST.MF"
"$java_bin/jar" cfm "$out/fixtures.jar" "$out/MANIFEST.MF" -C "$out/fixture-classes" .
"$java_bin/javac" --release 21 -proc:none -cp "$out/classes:$neo_dev:$classpath" -d "$out/test-classes" \
  "$tests/loader/ForgeLoaderFacadeTest.java" "$tests/runtime/ForgeRegistryFacadeTest.java"
"$java_bin/java" -ea -cp "$out/test-classes:$out/classes:$classpath" \
  org.sinytra.connector.forge.loader.ForgeLoaderFacadeTest "$out/fixtures.jar"
"$java_bin/java" -ea -cp "$out/test-classes:$out/classes:$neo_dev:$classpath" \
  org.sinytra.connector.forge.runtime.ForgeRegistryFacadeTest
