# Explicit FFAPI-refreshed candidate profile

The historical default remains unchanged. Opt in only with the consumer-relative profile `work/network-pair-cold-glue/profiles/ffapi-20261023.json` and proof path `work/emi-render-integration/refreshed-build-8f53/proof.json`.

This profile binds exact current branch commit `2b8a56143f58bc55767cfe23fb67b86111f5c4a0`, the authorized 42-module / 46-artifact FFAPI input refresh, unchanged runtime aggregate, generated source identity `8f53a44cf220eaddca79cf68be6b4c76cae74f7a9f3bc5982ac7d9719b211170`, 670 source records and 169 dependency records. Historical core identity 54e5 and repaired-FML equivalence reference ce4b remain separate.

Preparation validates source/profile bytes and dependency records, not the presence of all restored binaries. Immutable FML/Forge source support is staged before its init scripts are validated. Actual execution requires all dependency bytes, original regression inputs and the existing diagnostic GitHub Actions guard. No local environment impersonation is supported.

A new session captures actual core, PRODUCT and repaired-FML commands under the existing bounded runner, one worker/CPU and 512 MiB JVM heap. Every receipt must bind the same profile/session/input set, exact role-specific command recipe/digest, pinned Gradle/JDK paths, explicit environment/cwd, successful actual log, mandatory non-skipped task records, and output bytes. Missing full root check, the original Forge fixture, failed/partial logs, stale receipts or mixed profiles fail closed.

The four tuple hashes in `observedOutputReference` are previously observed outputs from partial actual builds. They are structural reproduction references, not a full-build acceptance stamp. The final proof cannot be created from those references alone: actual complete receipts, generated identity, PRODUCT closure verification, class/package ownership checks, 195-source FML provenance and exact cache-only repair comparison, plus original Forge fixture proof are all mandatory.

Shared `validate_full_build` returns canonical consumer-relative `inputPins`, rehashed for assembly/seal binding. The closure includes selected profile/proof, source and dependency files, scripts/init files, receipts/logs, tuple/bundle, FML source/reference files and dependency inputs, fixture evidence, and original PRODUCT/regression inputs. Pair/driver/seal retain their additional source/probe/graphics and runtime checks. `runtimeAcceptance` stays false; a full build is not a client/server/network runtime pass.

Focused tests use synthetic temporary inputs and mocked outer routing only where stated; they do not write a real candidate acceptance proof or launch Java. Run `python -m unittest test_refreshed_candidate` with the migrated modules first and exact current-HEAD baseline modules second on PYTHONPATH.
