# Fusion checkpoint dependency restoration notes

Status: supporting source/build documentation only. No download, Java, Gradle,
native harness, game, credential access or source modification was performed
while preparing this index. The pinned v6 client has scoped runtime acceptance. A fresh clean-network reconstruction has not been tested.

`dependency-restoration.json` records:

- All **116** exact local paths and SHA-256 values in the frozen FML compile
  lock, with Maven-layout coordinates. These are compile inputs, not bundled binaries
- All **169** fusion external dependency filename/hash pairs, each joined to an
  exact captured module coordinate and classifier in
  `source-workspace/provenance/unified-final-resolved-configurations.json`
- The **5** non-LWJGL compile inputs required by `preload-ui/build.sh`, the
  existing six-entry LWJGL compile/native lock, the **2** QSL inputs, and the
  Quilt Loader 0.30.1 ABI-test reference
- Official repository roots already present in retained build/research files,
  and the frozen Adapter userdev snapshot pins

The identity bound to this record is
`b468ee1cffa3d6e35a0f106ad55a02a8b43eb14267e900b18264712def7ffa94`.
Repository choices are candidates from configured official sources. Their
current availability was not checked. Exact artifact URLs are copied only for
the QSL/LWJGL records that already contain matching captured URLs and hashes.
There are no guessed direct URLs for generated Minecraft artifacts.

## Reconstruct the excluded inputs in a fresh authorized workspace

1. Preserve the checkpoint's relative layout. Provision official Java
   `21.0.12.1+1-LTS` and Gradle `8.11.1` separately at the toolchain paths recorded
   in the JSON, or deliberately adapt the build launcher. The checkpoint does
   not contain the Gradle wrapper JAR, so `./gradlew` alone is insufficient.

2. For every `external_maven_artifact`, use the listed coordinate and classifier
   with the indicated official repository candidates or the exact official
   installer manifest. Check SHA-256 before placing it at the recorded path.
   Do not silently accept another version or different bytes. Preserve both
   library versions where the FML lock records both.

3. Four FML entries are generated installer/NeoForm outputs:
   `net.minecraft:client:1.21.1-20240808.144430:{extra,slim,srg}` and
   `net.neoforged:neoforge:21.1.219:client`. These local coordinates identify
   derived inputs; they are not asserted to be published Maven releases.
   Recreate them with the pinned official NeoForge 21.1.219 installer and the
   official client preparation described in `tools/client-setup/README.md`.
   Verify the resulting bytes against the FML lock. Official installer,
   Minecraft inputs and assets are excluded from this source checkpoint; use
   the upstream manifests and hashes rather than invented artifact URLs.
   No game launch is needed merely to prepare official compile inputs.

4. Restore the captured Adapter userdev marker
   `1.2.1-20260813.224440-41` and implementation
   `1.2.1-20260813.224440-42` with the retained hashes and metadata. The source
   build declares `1.2.1-SNAPSHOT`; an unrestricted later resolution may choose
   different bytes. The 169 dependency index does not cover every build plugin
   or Gradle distribution artifact, and is not a portable Gradle cache.

5. Restore QSL base/lifecycle to their exact aliases:
   `docs/four-loader/quilt/upstream/qsl_base-alpha5.jar` and
   `docs/four-loader/quilt/upstream/lifecycle_events-alpha5.jar`.
   Restore Quilt Loader 0.30.1 as
   `docs/four-loader/quilt/upstream/loader-0.30.1.jar` for the compile/javap tests.
   The upstream Quilt loader is a test reference, not a second runtime engine.

6. The current Connector tree is `source-workspace/connector-four-loader`.
   Its supported build wrapper selects it using `--four-loader`; the default
   and `--unified` selectors refer to historical trees excluded from this
   checkpoint. Keep the recorded FML/admission sibling layout. Before any
   authorized build, verify all 116 FML input hashes and all relevant source
   hashes; after resolution, compare all 169 exact external artifacts and
   report any change. Do not weaken pins to make reconstruction pass.

   The source ZIP has no `.git`. The build reads `gradleutils.gitInfo["hash"]`
   when `PUBLISH_RELEASE_TYPE` is absent, so a plain extraction does not carry
   enough Git information to reproduce the recorded development version.
   Reconstruct an ordinary upstream Connector checkout at
   `8b27f1ad042aae8037bcc522b321c03fcce1a12a`, overlay the frozen source and
   preserve the sibling modules. Check the resulting version is
   `2.0.0-beta.17+1.21.1+infinity-source+dev-g8b27f1a`. No clone or Git operation
   was performed for this documentation. Setting `PUBLISH_RELEASE_TYPE` skips
   the Git branch but changes version/build semantics; it is not evidence of
   the same recorded build.

7. For the runtime bundle, prepare the official
   `run/client-dev/development-build/moddev/client-launch-inputs.json` through
   the retained `tools/client-setup/development` project, then build against
   the source-owned FML output. `runtime-bundle/client-branding.gradle` accepts
   explicit `clientClasspathManifest`, `unifiedFmlJar` and compile-only
   `admissionModelJar` overrides. The managed core must also be pinned with
   `managedCoreJar`/`managedCoreSha256`; selected QSL uses
   `docs/four-loader/quilt/bundled-initial.json`. The old official-Connector
   default is not the fusion installation recipe.

8. For preload compilation, materialize the five separately listed inputs at
   `run/neoforge-native/libraries/...`; the existing
   `preload-ui/fetch-dependencies.sh` supplies the checksum-locked LWJGL files.
   Preserve `/infinity-icon.png` as a bundled resource. Use a fresh candidate
   output directory rather than overwriting any accepted provider. The native
   responsiveness launcher additionally needs its environment-policy helper,
   exact candidate/core build outputs and a matching generated classpath file.
   Reconstructing those inputs is not proof of native or game acceptance.

## Evidence limits and source coverage

The 655-source fusion identity covers FML/admission and Connector component
sources; it does not include `runtime-bundle/` or `preload-ui/`. Separate product
compile/package receipts may extend the checkpoint's static evidence; preserve
their exact product and FML artifact hashes and distinguish those receipts from
the 655-source identity. Keep the preload candidate's evidence separate.
Historical baseline reports are separate; the v6 acceptance summary binds the actual ca776 provider and complete final artifact set.

A complete fresh root `check` also runs the Forge adapter, facade, event and
Clumps scripts, native Quilt/API checks, and component tests. In addition to the
indexed inputs, it needs:

- The exact production library tree at `run/neoforge-native/libraries`, or
  `FORGE_FACADE_HOST_LIBRARIES`; this is different from the client-dev FML lock
- The derived mapped NeoForge development JAR at
  `source-workspace/connector-four-loader/build/moddev/artifacts/neoforge-21.1.219.jar`,
  or `FORGE_FACADE_NEO_DEV_JAR`. It is not a guessed Maven download
- `BuildIdentity.java` generated by `:infinity-core:generateBuildIdentity`
- `four-loader/forge-probe/build/unified-forge-probe-0.1.0.jar`, built from the
  retained probe sources against four original Forge references, whose exact
  URLs/hashes are indexed under `additional_test_prerequisites`
- The probe recipe's historical clean Mojmap Minecraft input at
  `source-workspace/connector-combined/build/createCleanArtifact/minecraft-renamed.jar`.
  That generated artifact is excluded, and the probe recipe does not produce or
  digest-pin it itself. Recreate it through the official pipeline and record
  its actual hash. A bare source extraction does not satisfy this prerequisite
- Unmodified `Clumps-forge-1.21.1-19.0.0.1.jar`, SHA-256
  `e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19`,
  using the captured publisher URL in the JSON. This test binary is not bundled

The JSON explicitly records these missing generated/test-only prerequisites;
no complete clean-network `check` is claimed; scoped v6 game acceptance is recorded separately. Original source-replay
helpers reference
historical excluded trees and `source-workspace/upstream`/patch files; either
restore those exact source inputs or label those helpers historical.

The source checkpoint must preserve existing upstream licenses, source hashes
and modification notices. Source archives are not executable dependency JARs:
the retained FART, JarJarSelector and DevLaunch source archives were inspected
and contained no `.class` entries. No blanket project license is asserted.

Changes to a locked source/build input or resolved dependency require a new
identity and separate build/acceptance evidence. Repository resolution failure
is an unresolved reconstruction dependency, not permission to remove the pin.
