# Consumer-local four-role assembly

`pair_assembly.py` is an in-process, pure-Python adapter around the frozen `work/network-pair-assembly-local1/assemble_pairs.py` (SHA-256 `e3a54d562339ebdb090231e4b50e6d2055139deb06983109d715e8edcc6a75f1`). It does not start Java, Gradle, a game, or a network request. It does not edit frozen source artifacts.

## APIs

`prepare(repo_root, consumer_root)` restores the exact 27 required text inputs, four corresponding license files, frozen assembly/source metadata, and one additional required import helper. The existing consumer root is required. Existing identical source/config files are accepted; differing files are refused. Its return status is `PAIR_SOURCE_CONFIG_READY_NO_LAUNCH`. The receipt is at `consumer_root/work/network-pair-cold-assembly/source-preparation.json`.

The additional helper is `work/api1/four-loader/launch-support/game_environment.py`, imported at module load by the unchanged `common.py`. Its 3,049 bytes and SHA-256 `46e0fec38191d7b521fa6ae2c415c04285d04d1b545787054ab2a41ab67892e8` come from the already pinned accepted-v6 reconstruction archive. No new source archive is needed.

`assemble(repo_root, consumer_root, output=None, *, offline_identity_reference, eula_reference)` performs source preparation, validates fresh consumer runtime/build/probe evidence, invokes the unchanged `prepare_profiles.py` for both groups, and runs the recorded consumer derivative of `assemble_pairs.py`. The authorization references must be the existing user authorization references; the adapter does not invent or infer new approval. Default assembly output is `consumer_root/work/network-pair-assembled-cold`. An explicit output must also be within the consumer and must not exist. Existing prepared fixture/output/derivative files are refused rather than silently rerun.

CLI:

    python pair_assembly.py prepare --repo-root /source/mod-compat-runtime --consumer-root /fresh/consumer
    python pair_assembly.py assemble --repo-root /source/mod-compat-runtime --consumer-root /fresh/consumer --offline-identity-reference '<existing reference>' --eula-reference '<existing acceptance reference>'

## Required fresh consumer evidence

- `work/api1/run/api1-unified-client-build/official-client-launch-seal.json`
- `work/api1/ci/runtime-restore/native-server-closure.json`
- `work/api1/ci/runtime-restore/runtime-result.json`
- `work/emi-render-integration/cold-built-tuple-artifacts.json`
- `work/emi-render-integration/cold-fml-base-build-receipt.json`
- `work/emi-render-integration/cold-build-result.json` and its successful core/product build receipts and exact logs
- `work/api1/ci/nonce-probe/result.json`, the exact compiled `network-control-probe-0.1.0.jar`, three successful compile/test phase logs, and 95 exact client compile inputs
- `work/api1/four-loader/network-control-probe`, with the unchanged `65cf1c852d6e07226fcd7d2f66df8d202f3a6e70cd4d8f963c6dc40b28554909` source manifest
- The four pinned original mod filenames in `complex-mod-research`: Sophisticated Core, Sophisticated Backpacks, NeoForge EMI, and Fabric EMI

The runtime result must bind the current consumer client seal and native-server closure. All 95 native server files must match the frozen official dependency identities, independently of their new paths. Java and all four rebuilt tuple binary pins remain exact. The fresh FML base receipt must bind the new core build receipt. The probe result must bind this consumer's own artifact and runtime result. A historical successful receipt copied to a new filename is not sufficient.

## Preserved behavior and derivative changes

Fresh fixture preparation uses the original probe source/archive checks, exactly three approved originals plus the own probe, the APILocal identity, loopback ports 25631 and 25632, single-player whitelist, empty ops, disabled status/query/RCON, and the complete accepted NeoForge server config.

The frozen assembly copies the complete side-appropriate accepted configs, both server defaults before world creation, and the complete server-properties basis. Unified-only Connector/Indigo settings remain in their proper profiles. The frozen source-owned FML assembler and validator produce the separate client/server installation policies, verify the one FML owner, and retain exactly 46 embedded API archive records / 47 logical API IDs. Native server target remains `forgeserver`; client target remains `forgeclientdev`. All commands keep the pinned Java executable, 1,280 MiB heap, and two processors.

Five explicit source substitutions affect six occurrences: new input-lock hash, fresh tuple path, fresh FML base-receipt path, fresh native-server closure path (two occurrences), and fresh profile-preparation root. No Java/dependency pin, helper implementation, config content, class ownership rule, launch guard, or API count is relaxed. `derivation.json` records the exact replacements, source/derivative hashes, and new input-lock pin.

The new input lock contains unchanged helper/config pins plus the actual current consumer runtime, tuple, probe, build, and profile receipts. The frozen original input lock remains preserved under `frozen-source/`; its old completed receipt pins are not reused as fresh evidence.

## Output schema

The return value and `work/network-pair-cold-assembly/pair-assembly-result.json` have:

- `schema: 1`
- `status: COLD_FOUR_ROLE_ASSEMBLY_READY_GAME_UNRUN`
- `consumerRoot`, `assemblyRoot`, and `assemblyResult` file pin
- `roleCount: 4`
- `groups.native-neoforge` and `groups.unified`, each with its port, `roles.server` / `roles.client` launch-seal pins, and source-fixture pin
- `profiles`, `derivation`, and `inputLock` pins
- `requiredTextFiles: 27`
- `jvmStarted: false`, `gameLaunched: false`, `networkAcceptance: false`
- `remaining`, inherited from the frozen source assembly

Each role launch seal contains the consumer-local working directory, command, complete role file pins, three original mod paths, probe path, accepted config provenance, and the Unified assembly validation result where applicable. The adapter performs a final rehash and checks exactly four ordinary files in every user-mod directory before returning.

## Verification and limit

`pair-assembly-validation.json` records 11 glue checks plus all 11 unchanged frozen command-transformation regressions executed against the consumer derivative. Source preparation and the transitive helper import passed. Changed configs, nonconsumer destinations, missing authorization references, modified derivative shape, and absent fresh consumer receipts were rejected. No fake runtime/build receipt was generated to make a full assembly test pass.

Full four-role assembly has not run because the required cold consumer runtime/build/probe results do not exist in this source-only execution. Actual runner graphics identity, aggregate memory gate, reviewed supervisor control-file lifecycle handling, game connection and same-nonce acceptance remain separate downstream requirements.
