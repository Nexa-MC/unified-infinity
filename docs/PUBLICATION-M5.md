# M5 source publication validation

This is a curated source/evidence publication of the accepted M5 checkpoint.
It includes the unchanged complete corresponding-source ZIP, pinned patches,
upstream source/license inputs, host branding sources, provider sources/artwork,
focused regression fixtures and machine-readable acceptance summaries.

## Fresh checks on the exported source

- 99 admission tests, five archive-verifier tests and 16 registry harness tests passed
- 22 standalone API tests and its example passed; the Fabric comparison compiled
- Ten loading-core tests and direct-FART ownership/order/failure/cancellation tests passed
- 32 preload headless assertions and ten branding text contracts passed
- The exported Adapter regression tests compiled and passed 429 parameter checks
  and 79 postprocess checks against the existing hash-verified M5 core; the
  original unmodified baseline reproduced the expected failing negative control
- Eight reconstruction inputs passed their pinned digests; an ordinary clone at
  the pinned upstream commit plus four patches recreated all 331 non-directory
  files in the complete source archive and all 316 source/build identity inputs

Detailed results and scope are in `publication-validation-m5.json`.
These checks are not a new Minecraft runtime acceptance or a fresh full Gradle
compilation. The original M5 runtime/build records are retained separately.

## Packaging and attribution corrections

The checkpoint stored required upstream inputs and regression fixtures in other
component directories. This export additionally supplies them at the locations
expected by `prepare-unified.py` and `run-source-regressions.py`. Build instructions
now explicitly require the pinned upstream clone, its `gradle.properties`, the
unbundled toolchains and prepared official runtime fixtures.

The host notice previously called the companion Connector an unchanged official
JAR. It now accurately identifies the complete modified Connector/FART/Adapter
core, preserves component licensing, and adds Adapter attribution. The top-level
notice does not assign a blanket license to the mixed-license project.

This notice correction does not change the recorded immutable test artifacts:
core `c8921d6a...`, host `3802215d...`, provider `7b549d37...`. Rebuilding the host
with the corrected resource can change its binary digest. Such a new binary needs
its own pin and regression; it must not be substituted into the recorded result.

## Deliberately omitted

Captured Minecraft screens/video, raw launch/runtime logs, user accounts, private
workflow metadata, game binaries/assets, test worlds, dependency caches and
installed toolchains are excluded. Original/derived product artwork is retained.
Acceptance JSON may reference omitted logs/images and retains test-world file
hashes as evidence; the underlying media and world files are not distributed.

Historical M4/Lithium experiment documentation is explicitly marked historical.
Later hopper and mixed-pack experiments are outside this snapshot. The complete
source ZIP covers Connector, FART and Adapter core, not every runtime dependency.
Future dependency resolution can differ because Adapter userdev still declares a
mutable snapshot. Repetition in one observed cache is not a fresh-machine
bitwise-reproducibility guarantee.
