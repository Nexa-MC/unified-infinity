#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd); cd "$ROOT"
P=lithium-trial/patches/postprocess-tests
BASE=integrated-loader/build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar
PATCH=lithium-trial/patches/parameter-removal/classes
JAVA=.toolchains/jdk-21.0.12.1+1/bin
ASM=$(find run/lithium-unified/libraries/org/ow2/asm -path '*/9.8/*.jar' | sort | paste -sd: -)
LIBS=$(find run/lithium-unified/libraries -name '*.jar' | sort | paste -sd: -)
CP=$PATCH:$BASE:run/lithium-unified/libraries/com/google/guava/guava/32.1.2-jre/guava-32.1.2-jre.jar:$ASM:$LIBS
mkdir -p "$P/classes"
"$JAVA/javac" -proc:none -cp "$CP" -d "$P/classes" "$P/PostprocessRegression.java"
"$JAVA/java" -Dlog4j2.configurationFile=lithium-trial/patches/parameter-removal/tests/log4j2.xml -cp "$P/classes:$CP" PostprocessRegression run/lithium-unified/libraries/net/neoforged/neoforge/21.1.219/neoforge-21.1.219-server.jar
