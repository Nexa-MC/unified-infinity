#!/usr/bin/env bash
# One bounded pure JVM, no Gradle, game, artifact rebuild or network. Run in an isolated test memory budget.
set -euo pipefail
cd "$(dirname "$0")/../.."
java_bin="${JAVA_HOME:-../../.toolchains/jdk-21.0.12.1+1}/bin"
out="${ADMISSION_TEST_OUTPUT:-build/admission-model-tests}"
mkdir -p "$out"
"$java_bin/javac" -J-Xmx128m -J-XX:ActiveProcessorCount=1 --release 21 -encoding UTF-8 -proc:none -d "$out" \
  ../admission-bootstrap/src/main/java/org/sinytra/connector/infinity/inventory/{AdmissionInventory,InventoryReconciler,InventoryDisplay,InfrastructurePolicy,AuditedInfrastructureIds,TrustedPayloads}.java \
  components/infinity-core/src/test/java/org/sinytra/connector/infinity/inventory/AdmissionInventoryTest.java
"$java_bin/java" -Xmx96m -XX:ActiveProcessorCount=1 -ea -cp "$out" org.sinytra.connector.infinity.inventory.AdmissionInventoryTest
