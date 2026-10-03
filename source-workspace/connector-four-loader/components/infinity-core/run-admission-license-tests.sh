#!/usr/bin/env bash
# Original descriptor fixtures only; no Gradle, game, native graphics, network or runtime JAR rebuild.
set -euo pipefail
cd "$(dirname "$0")/../.."
java_bin="${JAVA_HOME:-../../.toolchains/jdk-21.0.12.1+1}/bin"
libs="${ADMISSION_TEST_LIBRARIES:-../../run/client-dev/libraries}"
classpath="$libs/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar:$libs/com/electronwill/night-config/core/3.8.3/core-3.8.3.jar:$libs/com/electronwill/night-config/toml/3.8.3/toml-3.8.3.jar"
out="${ADMISSION_LICENSE_TEST_OUTPUT:-build/admission-license-tests}"
mkdir -p "$out"
"$java_bin/javac" -J-Xmx128m -J-XX:ActiveProcessorCount=1 --release 21 -encoding UTF-8 -proc:none -cp "$classpath" -d "$out" \
  ../admission-bootstrap/src/main/java/org/sinytra/connector/infinity/inventory/{AdmissionInventory,AdmissionMetadata,InfrastructurePolicy,AuditedInfrastructureIds,TrustedPayloads}.java \
  components/infinity-core/src/test/java/org/sinytra/connector/infinity/inventory/AdmissionMetadataLicenseTest.java
"$java_bin/java" -Xmx96m -XX:ActiveProcessorCount=1 -ea -cp "$out:$classpath" org.sinytra.connector.infinity.inventory.AdmissionMetadataLicenseTest
