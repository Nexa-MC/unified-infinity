#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
JAVA="../../.toolchains/jdk-21.0.12.1+1/bin"
cache=../gradle-cache/caches/modules-2/files-2.1
ffloader=$(find "$cache/org.sinytra/forgified-fabric-loader" -name '*.jar' | head -1)
annotations=$(find "$cache/org.jetbrains/annotations/24.1.0" -name '*.jar' | head -1)
gson=$(find "$cache/com.google.code.gson/gson" -name '*.jar' | head -1)
slf4j=$(find "$cache/org.slf4j/slf4j-api" -name '*.jar' | head -1)
cp="$ffloader:$annotations:$gson:$slf4j"
mkdir -p four-loader/api-tests/classes four-loader/api-tests/test-classes
"$JAVA/javac" --release 21 -cp "$cp" -d four-loader/api-tests/classes $(find src/main/java/org/quiltmc src/main/java/org/sinytra/connector/quilt -name '*.java')
"$JAVA/javac" --release 21 -cp "four-loader/api-tests/classes:$cp" -d four-loader/api-tests/test-classes $(find four-loader/api-tests/src/net -name '*.java')
"$JAVA/javac" --release 21 -cp "four-loader/api-tests/test-classes:../../docs/four-loader/quilt/upstream/loader-0.30.1.jar:four-loader/api-tests/classes:$cp" -d four-loader/api-tests/test-classes $(find four-loader/api-tests/src/org -name '*.java')
"$JAVA/java" -ea -cp "four-loader/api-tests/test-classes:four-loader/api-tests/classes:$cp" org.sinytra.connector.quilt.QuiltApiTest | tee four-loader/api-tests/behavior-result.txt
python3 four-loader/api-tests/verify_api_abi.py
