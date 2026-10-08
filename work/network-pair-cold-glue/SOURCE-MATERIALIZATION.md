# Exact render source reconstruction

`source_materialize.py` reconstructs the source/config build inputs in a new consumer project root. It does not execute the copied scripts, download dependencies, start Java or Gradle, install a game, or modify an existing project.

Python API: `materialize(repo_root, consumer_root)` (also exported as `prepare`). `repo_root` is the existing `mod-compat-runtime` project. `consumer_root` must not exist and its parent must exist. `inspect_inputs(repo_root)` checks the four source archive pins without writing. `verify_sources(consumer_root)` rehashes the complete selected source/config inventory and the 670 candidate source records.

CLI:

    python source_materialize.py --repo-root /path/to/mod-compat-runtime --consumer-root /path/to/new-consumer

The consumer contains:

- `work/api1/source-workspace/connector-four-loader`: exact render Connector/core source
- `work/api1/source-workspace/fml-unified` and `admission-bootstrap`: sibling source layout required by the exact build; FML owns the production loader and includes 184 Java source files
- `work/api1/runtime-bundle`: unchanged PRODUCT source, notices, tests, and build configuration
- `work/api1/tools/client-setup`: recovered official client preparation source
- `work/emi-render-integration`: original source checkpoint metadata and render build helpers, retained as historical input
- `portable-bootstrap`: original bounded preparation/restoration helpers and exact locks
- `source-materialization.json`: reconstruction evidence, external dependency requirements, and code adapter needs

The pinned manifest selects 801 source/config files from exactly four source-only archives. It checks archive size and SHA-256 before use, exact archive membership, member sizes/hashes, traversal, symlinks, duplicate entries/destinations, source-only nested archives, and total expansion bounds. It validates all input payloads before creating the output root. Existing output roots are refused even when empty. A failed filesystem write may leave a partial fresh root for diagnosis; it is never a successful reconstruction.

The `loader-sources/` archive prefix is mapped to sibling projects in `source-workspace`, not nested under Connector. Core and FML source bytes remain unchanged. MIT, LGPL, Apache, upstream notices, modification records, and source provenance remain with their source. The recovered `gradle.properties` contains historical 3 GiB/default parallel settings; builds must use the existing bounded invocation override, not invoke Gradle directly.

## What is established

All 670 source records exactly match candidate identity `54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6`. All 169 dependency identity records and the compiler runtime `21.0.12.1+1-LTS` are preserved. Every dependency hash has group/name/version/artifact metadata in the preserved strict-verification XML. Of the 169 dependencies, 99 also appear in the source-only restoration locks; the other 70 require Gradle resolution under strict verification. FML has a separate 116-file compile lock. The exact full identity cannot be recomputed until all 169 external binary byte streams and the pinned JDK runtime are available.

The render archive alone omitted PRODUCT source, Connector `gradle.properties`, verification metadata, and FML assembly helper scripts. The accepted-v6 reconstruction source archive provides the exact unchanged PRODUCT/helper/config files. The API1 bootstrap archive supplies restoration locks and strict verification metadata. No API1 source overlay is applied to the exact render core.

## Remaining inputs and adapter work

The generated report lists the exact dependency filenames/hashes/coordinates, original restoration lock records, FML compile paths/hashes, and generated official inputs. These binary inputs are not bundled or copied here. The runtime preparation stage must restore the official toolchains, NeoForge libraries, generated client/server artifacts, QSL/FFAPI originals, pinned SNAPSHOT metadata, and exact regression fixture originals. Gradle plugin and dependency POM/module metadata must also resolve through the existing strict-verification configuration.

The driver must rebind the unchanged render `run_bounded.py` module's `ROOT` to the consumer `work/api1` while retaining its `HERE` beside the exact render init script. The render `build_product.py` executes on import and reads historical absolute paths; it must not be imported/executed directly against those receipts. The driver must form new consumer-local artifact and classpath receipts after fresh verified builds, then reuse the existing explicit PRODUCT arguments. The exact server-extra regression fixture must also be available at the unchanged init script's consumer-local expected path; its byte pin must not be relaxed.

Original build receipts copied from the source checkpoint are historical evidence, never evidence that a consumer build ran. Runtime assembly, runner graphics/memory, same-nonce nativeNF/Unified connections, GUI acceptance, and game validation remain separate stages.

## Verification

`source-validation.json` records 18 pure-Python checks, including a full fresh reconstruction, changed-source detection, existing-output preservation, unsafe path/archive rejection, source-only binary checks, and final original archive rehashes. No Java, Gradle, network, game, Git, or remote operation was run. The fresh smoke reconstruction at `/tmp/network-pair-cold-source-check1` is temporary local test output, not a distributed artifact or runtime proof.
