# Implemented native Quilt first slice

Target: Minecraft 1.21.1 / Java 21 / NeoForge 21.1.219. Source tree: `source-workspace/connector-four-loader`. Accepted `connector-combined` and prior artifacts are unchanged.

## Architecture

- Native `quilt.mod.json` enters the existing Connector discovery, one FFLoader candidate graph/resolver and final FML admission. No second Quilt engine, solver, game classloader or Mixin bootstrap is bundled.
- Strict schema-1 JSON parsing rejects duplicate keys, trailing input and unsupported JSON5, adapters, nested or conditional dependency shapes, aliases/provides and unsupported ranges. Original complete metadata AST, ID/group/raw version and input provenance survive independently from host module naming.
- Native pre_launch, init, client_init and server_init retain their exact upstream keys and `ModContainer` argument signatures. Entry points are views of FFLoader's existing store, with once-only dispatch and contextual errors. Default Java method references remain ordered.
- 37 supplied Quilt Loader 0.30.1 public API types match upstream signatures/descriptors. This is a bounded compatibility API provider, not complete Quilt Loader behavior. Global dirs, non-SemVer ordering, plugin/GUI/config APIs and independent builtin resource roots remain explicitly unsupported.
- Only original QSL `quilt_base` and `quilt_lifecycle_events` 10.0.0-alpha.5+1.21.1 are selected. Official Maven currently contains 30 real modules; the other 28 are not implicitly compatible or tested.
- Original QSL installed/bundled JAR bytes, IDs, versions and attribution are retained. The derived transformation view suppresses base bootstrap/test mixins and lets the existing host own initialization exactly once. Original QSL EventRegistry and lifecycle event implementations remain in use.
- Quilt side preprocessing handles package/class/member and non-generic interface side annotations; unsupported wrong-side field/method type-use and generic interface signatures fail explicitly. Declared Mixin environment filtering is retained; native inputs do not receive Fabric's unlisted-config glob activation. At most one AW is supported.

## Host embedding contract

The optional host embeds the two original payloads plus `META-INF/unified-infinity/bundled-qsl.json`. Its standard NeoForge JarJar metadata includes FFAPI only. The original native QSL modules must not be independently admitted as generic JarJar libraries.

`ManagedQuiltModules` accepts only the exact two pinned modules from the inventory, verifies their original bytes, materializes a hash-addressed unchanged input copy, retains `[outer host archive, relative embedded payload]` source provenance, and feeds them into existing candidate discovery. Duplicate modules, changed bytes/paths/versions and unsupported inventories fail.

Final native FML metadata retains raw versions including `+`; normalizing them to `_` breaks exact host dependencies. Java 21 module versions accept these raw values. Existing Fabric normalization remains unchanged.

## Build and focused evidence

Current full source artifact: `connector-2.0.0-beta.17+1.21.1+infinity-source+dev-g8b27f1a-full.jar`

SHA-256: `26b599fc1c033614c427062b209ae8d7a48a3e75bca51e78f1c79ff8299f4cde`

- `python3 source-workspace/gradle-build.py --four-loader fullJar check`: PASS, `logs/four-loader/full-build-order-forge-event.log`
- Native metadata/side/resolver: 44 assertions, including actual same-FFLoader resolver rejection of missing dependencies and too-new quilt_loader
- Quilt API host views: 66 assertions; 37 supplied upstream public type descriptor comparisons
- Managed embedding: 20 assertions, including actual FML ModFile identification and exact QSL version matching, original extraction/provenance, warm behavior, corrupt cache recovery and negative pin/path/payload cases
- Recursive core audit: 38 Quilt API classfiles including an anonymous implementation; zero `org/quiltmc/loader/impl` engine classfiles; zero duplicate QSL implementation/API classes in the core
- The root aggregate also passes existing loading-core/FART tests and the separate Forge adapter/facade focused suites

Dedicated standalone embedding test: `bash four-loader/managed-qsl-tests/run.sh`. It consumes the optional host candidate to validate its real embedded payloads without executing them.

## Runtime proof is separate

Project-owned probe source is `four-loader/quilt-probe`; its current exact JAR/hash and negative controls are recorded in `build/build-report.json`. It is compiled against the official Quilt/QSL ABIs and contains only native Quilt metadata, with no Fabric/NeoForge API references.

The fixture asserts provider/resource/source/classloader identity; prelaunch/init/side/method-reference ordering; real item registry; QSL auto-listener/READY/tick/STOPPED; a vanilla-target Mixin sentinel; actual SavedData create/save/reopen with read-before-write checks. Its Mixin class is isolated in a dedicated subpackage. It uses the official non-null `SAVED_DATA_COMMAND_STORAGE` type because genuine vanilla 1.21.1 rejects a null SavedData factory type on reopen. No cross-version data migration is claimed.

Focused tests and successful compilation do not prove a game launch. Genuine Quilt and Unified launch reports are separate; preserve failed control attempts rather than presenting them as passes. No real third-party mod execution follows from these results.


## Verified first native/Unified server acceptance

The unchanged original probe SHA-256 `f420e2021563d25931f1783f5a5744943dfbafc7557ae5c52ff2090331066b04` passes a fresh create/save/reopen pair on genuine Quilt and the Unified host with original QSL embedded internally. All eight stages fire exactly once, including automatic READY before manual READY, real registry identity, five QSL/Mixin ticks and unchanged SavedData read before writing. All original input JAR hashes remain unchanged, and the second Unified launch uses the warm transform cache. Both final Unified launches bind loopback with LAN advertising disabled before startup.

The canonical selected native provider order is retained from the existing resolver. Native init explicitly prioritizes the exact managed base bootstrap provider in the same entrypoint view/dispatcher; there is no new registry, solver or callback store. Within-provider entrypoint array order remains stable.

Acceptance summary: `four-loader/quilt-unified-control/ordered-control-summary.json`.
Genuine control: `four-loader/quilt-native-control/native-control-summary.json`.
The previous 201910d6 pair is retained as a negative ordering observation and is superseded for semantic ordering acceptance. Generated missing-dependency and loader-version fixtures have static solver coverage; full process negative-control execution remains separate future work.
