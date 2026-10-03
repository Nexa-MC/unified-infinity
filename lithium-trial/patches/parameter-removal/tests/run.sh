#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$ROOT"
TESTS=lithium-trial/patches/parameter-removal/tests
PATCH=lithium-trial/patches/parameter-removal/classes
BASE=integrated-loader/build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar
LITHIUM=docs/real-mod-trial/lithium-fabric-0.15.4+mc1.21.1.jar
JAVA=.toolchains/jdk-21.0.12.1+1/bin
mkdir -p "$TESTS/build/classes"
# Prioritize the deployment's ASM 9.8 over duplicate transitive ASM 9.3 jars.
ASM=$(find run/lithium-unified/libraries/org/ow2/asm -path '*/9.8/*.jar' -print | sort | paste -sd: -)
LIBS=$(find run/lithium-unified/libraries -name '*.jar' -print | sort | paste -sd: -)
CP="$PATCH:$BASE:$ASM:$LIBS"
mkdir -p "$TESTS/build/recompiled-patch-classes"
"$JAVA/javac" -g -encoding UTF-8 -proc:none -cp "$CP" -d "$TESTS/build/recompiled-patch-classes" \
  lithium-trial/patches/parameter-removal/src/org/sinytra/adapter/transform/param/RemoveParameterTransformer.java
cmp "$PATCH/org/sinytra/adapter/transform/param/RemoveParameterTransformer.class" \
  "$TESTS/build/recompiled-patch-classes/org/sinytra/adapter/transform/param/RemoveParameterTransformer.class"
echo 'PASS: supplied compiled patch is byte-identical to fresh source compilation with javac -g'
"$JAVA/javac" -encoding UTF-8 -proc:none -Xlint:all -cp "$CP" -d "$TESTS/build/classes" \
  "$TESTS/src/org/sinytra/adapter/transform/param/RemoveParameterTransformerRegression.java"
echo "Java: $("$JAVA/java" -version 2>&1 | head -1)"
sha256sum "$BASE" "$LITHIUM" "$PATCH/org/sinytra/adapter/transform/param/RemoveParameterTransformer.class"
echo 'Running patched regression suite'
"$JAVA/java" -Dlog4j2.configurationFile="$TESTS/log4j2.xml" -ea \
  -cp "$TESTS/build/classes:$CP" \
  org.sinytra.adapter.transform.param.RemoveParameterTransformerRegression "$LITHIUM"
echo 'Running unpatched negative control (failure is required)'
set +e
"$JAVA/java" -Dlog4j2.configurationFile="$TESTS/log4j2.xml" -ea \
  -cp "$TESTS/build/classes:$BASE:$ASM:$LIBS" \
  org.sinytra.adapter.transform.param.RemoveParameterTransformerRegression "$LITHIUM" --lithium-only \
  > "$TESTS/build/unpatched-negative-control.log" 2>&1
NEGATIVE_EXIT=$?
set -e
cat "$TESTS/build/unpatched-negative-control.log"
if [[ $NEGATIVE_EXIT -eq 0 ]]; then
  echo 'ERROR: unpatched negative control unexpectedly passed' >&2
  exit 1
fi
grep -F 'Lithium after removal invisible count: expected 7, actual 9' "$TESTS/build/unpatched-negative-control.log" >/dev/null
grep -F 'Lithium ASM serialization failed: java.lang.ArrayIndexOutOfBoundsException' "$TESTS/build/unpatched-negative-control.log" >/dev/null
echo "PASS: unpatched negative control failed for the expected stale annotation count (exit $NEGATIVE_EXIT)"
