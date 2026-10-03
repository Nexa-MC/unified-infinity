#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
JAVA_HOME="${JAVA_HOME:-$ROOT/.toolchains/jdk-21.0.12.1+1}"
LIB="$ROOT/run/neoforge-native/libraries"
DEPS=("$LIB/net/neoforged/fancymodloader/loader/4.0.42/loader-4.0.42.jar" "$LIB/net/neoforged/fancymodloader/earlydisplay/4.0.42/earlydisplay-4.0.42.jar" "$LIB/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar" "$LIB/org/slf4j/slf4j-api/2.0.9/slf4j-api-2.0.9.jar")
DEPS+=("$LIB/net/sf/jopt-simple/jopt-simple/5.0.4/jopt-simple-5.0.4.jar")
for artifact in lwjgl lwjgl-glfw lwjgl-opengl; do DEPS+=("$PWD/.deps/$artifact-3.3.3.jar"); done
for file in "${DEPS[@]}"; do [[ -f "$file" ]] || { echo "Missing compile-only dependency: $file; see README.md" >&2; exit 1; }; done
CP=$(IFS=:; echo "${DEPS[*]}")
mkdir -p build/classes build/test-classes build/libs build/reports build/cache
export XDG_CACHE_HOME="$PWD/build/cache"
find src/main/java -name '*.java' | sort > build/main-sources.txt
"$JAVA_HOME/bin/javac" --release 21 -encoding UTF-8 -Xlint:all -cp "$CP" -d build/classes @build/main-sources.txt
cp -R src/main/resources/. build/classes/
printf 'Manifest-Version: 1.0\nAutomatic-Module-Name: dev.modcompat.preload\nImplementation-Title: Unified Infinity Preload UI\nImplementation-Version: 0.1.0-dev\nFMLModType: LIBRARY\n\n' > build/MANIFEST.MF
"$JAVA_HOME/bin/jar" --date=2026-10-03T00:00:00Z --create --file build/libs/unified-infinity-preload-0.1.0-dev.jar --manifest build/MANIFEST.MF -C build/classes .
find src/test/java -name '*.java' | sort > build/test-sources.txt
"$JAVA_HOME/bin/javac" --release 21 -encoding UTF-8 -Xlint:all -cp "$CP:build/classes" -d build/test-classes @build/test-sources.txt
"$JAVA_HOME/bin/java" -Djava.awt.headless=true -cp "$CP:build/classes:build/test-classes" dev.modcompat.preload.PreloadTests | tee build/reports/headless-tests.txt
printf '%s' "$CP:build/classes:build/test-classes" > build/classpath.txt
sha256sum build/libs/*.jar > build/reports/artifact.sha256
