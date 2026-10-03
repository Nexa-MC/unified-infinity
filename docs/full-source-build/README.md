# Unified Infinity complete-source build milestone

## Result

The untouched released Connector source and the modified combined source build both pass using Java 21, Gradle 8.11.1 and the official ModDevGradle binary-only Minecraft artifact pipeline. The combined build compiles complete Connector, FART and Adapter core source modules. It does not replace individual classes inside an existing upstream JAR.

Frozen candidate:

- `source-workspace/artifacts/unified-infinity-source-connector-adapter-fart-1.21.1.jar`
- SHA-256: `c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e`
- Complete source ZIP: `source-workspace/artifacts/unified-infinity-complete-connector-fart-adapter-sources.zip`
- Source ZIP SHA-256: `7b3b85e3334a48c1b61cc7aaafed605cd9d4525322554828ef80bee4a8b1a672`

Target is Minecraft **1.21.1 only**, NeoForge 21.1.219, Java 21. Fresh acceptance subsequently passed with the exact c892 core and 380221 managed host: dedicated-server Lithium create/save/reopen and actual client main menu with the unchanged parity probe. See docs/M5-FULL-SOURCE-ACCEPTANCE.md; the client test did not include Lithium or a world.

## What was verified

1. Official Connector tag `2.0.0-beta.17+1.21.1` and commit `8b27f1ad042aae8037bcc522b321c03fcce1a12a` match; the baseline checkout remains clean
2. Untouched complete Connector build passed; its source-built full JAR is SHA-256 `e15fdfa51ae1600e28267698dfbc015c69c5ca1caa19ea0402980e2581046ad1`
3. Combined complete-source build passed, including all 163 Adapter core Java sources (245 compiled classes), all 28 FART Java sources (64 compiled classes), and shared core (8 compiled classes including generated identity)
4. The 31 parameter regression tests performed 429 checks; postprocess regression performed 79 checks, for **508 checks, zero failures**, against the frozen combined JAR
5. The freshly source-built untouched baseline failed the expected original-Lithium annotation-count/ASM serialization negative control
6. Ten shared-core tests and direct-FART ordering, ownership, failure and cancellation tests passed
7. Forced offline rerun executed all 31 build tasks and produced **byte-identical JAR and source ZIP**; this demonstrates repeatability in the observed dependency cache, not cross-environment reproducibility
8. Four existing service descriptors are unchanged; all 1,300 class definitions across the candidate and its two actual JarJar libraries have unique owners; FabricLoaderImpl has one definition in the candidate
9. Outer manifest, nested Connector mod manifest and JarJar coordinate all use `2.0.0-beta.17+1.21.1+infinity-source+dev-g8b27f1a`; the mod descriptor resolves its version through `${file.jarVersion}`
10. Complete corresponding FART/Adapter source archives and licenses are embedded and match the compiled source trees
11. Four digest-pinned patches reconstructed a fresh ordinary source clone with **354 files matching exactly**

Original Lithium remains SHA-256 `92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa`. No third-party mod bytes were changed.

## Ownership and source layout

- `source-workspace/connector/`: untouched official same-pin source baseline
- `source-workspace/connector-combined/`: actual buildable ordinary Git clone with the reviewed source changes
- `components/infinity-core`: target-independent budgeting, bounded scheduling, resource ownership and progress; compiled/shaded once
- `components/infinity-host-neoforge`: managed lifetime/cache identity in the existing host path, compiled into Connector's existing module
- `components/infinity-mc-1.21.1`: pinned clean-bytecode lookup responsibility, compiled into the same host module
- `transformer/`: complete Connector transformer source, with the established bounded JAR/direct-entry changes
- `components/infinity-fart`: complete source from verified published FART 1.0.14 sources; only AsyncHelper changed, followed by existing upstream relocation
- `components/infinity-adapter`: complete source from verified published Adapter core 2.0.43+1.21.1 sources; exactly the three validated Lithium-fix sources changed

Host/version source roots are responsibility boundaries, not new loader engines. The original Connector locator remains the only Connector discovery provider. FML retains final admission/class definition, and the Fabric fork retains candidate selection. No second solver, Mixin engine, classloader, registry or event replay system was introduced. Not every upstream game-specific class has been migrated into a separate version module yet.

Historical `connector-unified/` and `connector-replay-check/` are retained preparation worktrees. Upstream GradleUtils/JGit cannot build those linked worktrees correctly; use the ordinary `connector-combined/` clone. `connector-final-replay/` is the successful final source-reconstruction check.

## Shared cache identity

The generated identity is:

`e6d0b0028e64c9cc6fbad7e36a5f2051aa21fe355245753292199c2951264dc6`

It hashes 316 source/build/pin inputs, every changed Connector/FART/Adapter/core source, 169 resolved external compile/runtime/shade dependency artifacts by actual bytes, and the Java runtime/compiler identity. It was independently recalculated from those inputs. The embedded `META-INF/unified-infinity/build-identity.json` records the input hashes.

`ManagedConnectorTransformerEnvironment.getJarCacheVersion()` appends this one identity. Both `JarTransformer` mapped-mod caching and `BytecodeFixerUpperFrontend` generated-adapter caching use that environment method. The identity replaces the old overlay-only scope.

## Rebuild

### Source package prerequisites and reconstruction

This publication supplies every digest-pinned `source-lock.json` input at its
expected `source-workspace/upstream/` or `patches/` location, and the focused test
sources under `source-workspace/regression-tests/`. The complete source ZIP is
an immutable corresponding-source record, not a standalone checkout: it omits
upstream `gradle.properties` and wrapper files. Obtain those from the exact
ordinary upstream clone before applying the reviewed patches:

```sh
git clone --no-checkout https://github.com/Sinytra/Connector.git source-workspace/connector
git -C source-workspace/connector checkout --detach 8b27f1ad042aae8037bcc522b321c03fcce1a12a
python3 source-workspace/verify-source-package.py
python3 source-workspace/prepare-unified.py connector-combined
python3 source-workspace/verify-source-package.py --reconstructed source-workspace/connector-combined
```

`prepare-unified.py` refuses to overwrite an existing target and verifies all
source-input hashes. It performs no game launch or upload. A fresh clone requires
network access to official upstream sources; dependency resolution also requires
separately acquired third-party artifacts.

Install Java 21.0.12.1+1 at `.toolchains/jdk-21.0.12.1+1/` and Gradle 8.11.1 at
`.toolchains/gradle-8.11.1/`, or use equivalent local directory links. These tools
are not bundled. The existing Linux wrapper assumes a normal system Java trust
store. Prepared Minecraft/NeoForge runtime libraries and the original Lithium JAR
are required only for the focused regression and runtime fixtures; acquire them
through the official tooling and pinned URLs in component documentation rather
than from this source repository. Do not substitute unverified artifact bytes.

From the project root, after reconstruction and toolchain preparation:

```sh
python3 source-workspace/gradle-build.py fullJar --stacktrace
python3 source-workspace/gradle-build.py --unified fullJar --stacktrace
python3 source-workspace/run-source-regressions.py
python3 source-workspace/verify-source-artifact.py
```

The wrapper sets `CI=true`, uses the approved project Java/Gradle installations, enforces two workers/two visible processors and a 2 GiB inherited JVM cap, isolates Gradle/JGit/home writes, derives current proxy settings and preserves normal TLS verification. It rejects game-launch/publish/upload/release task names.

`CI=true` is the [documented ModDevGradle 2.0.136+ binary-only pipeline](https://github.com/neoforged/ModDevGradle#disabling-decompilation-and-recompilation); pinned 2.0.140 supports it. It avoids Minecraft decompile/recompile while compiling all Connector/FART/Adapter source. The prior Vineflower 2 GiB heap failure is resolved by this official path; no heap or toolchain upgrade was made.

For a fresh source reconstruction using the existing untouched checkout and digest-pinned inputs:

```sh
python3 source-workspace/prepare-unified.py connector-new-source-check
```

This never overwrites an existing tree. The four patches and upstream source/license hashes are pinned in `source-workspace/source-lock.json`. They are the maintained change set; preparation scratch scripts are historical helpers, not an alternative runtime implementation.

## Provenance and remaining limits

Evidence is in `source-workspace/provenance/`, especially:

- `final-summary.json`, `baseline-build-success.json`
- `combined-artifact-verification.json`, `nested-ownership-verification.json`
- `regression-results.json`, `final-build-identity.json`
- `final-patch-replay-verification.json`
- `unified-final-resolved-configurations.json`
- `adapter-source-integration.json`, `adapter-userdev-snapshot.json`

Raw logs are `logs/full-source-*`; the final build is `full-source-combined-final-09.log`, forced repeat is `full-source-combined-reproducibility-10.log`, and focused test logs are `full-source-regression-*`.

This is a complete Connector + FART + **Adapter core** source milestone, not a complete all-dependency source distribution. Forgified Fabric Loader, FFAPI, Adapter runtime 1.0.0+1.21.1 and NeoForge/FML/Minecraft host dependencies remain pinned upstream artifacts. The complete deployed host/API/provider inventory is a separate runtime acceptance check.

The released build declares mutable Adapter userdev `1.2.1-SNAPSHOT`: marker resolved to `1.2.1-20260813.224440-41`, implementation to `1.2.1-20260813.224440-42`. Captured metadata and actual hashes are retained. Observed artifact manifests are not a full dependency lock; a future network resolution may differ and must produce a changed cache/build identity. That original build record performed no publication or account action. This
source publication preserves that historical evidence; see `../PUBLICATION-M5.md`
for the subsequent package validation and attribution correction.
