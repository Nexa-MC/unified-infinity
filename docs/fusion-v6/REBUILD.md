# Rebuilding the v6 source snapshot

This archive preserves sources and dependency pins. A clean-network build was
not executed during packaging; the recorded build used an already populated
pinned dependency cache. Do not interpret source identity as byte-for-byte
reproducibility across arbitrary toolchains, Git metadata or installation policy.

1. Verify with `python3 source-workspace/verify-fusion-source.py`.
2. Install Java 21.0.12.1+1 and Gradle 8.11.1 from their official vendors into
   `.toolchains/jdk-21.0.12.1+1` and `.toolchains/gradle-8.11.1`, respectively.
   The checked-in wrapper properties retain Gradle distribution metadata;
   the executable wrapper JAR and toolchains are excluded from this source archive.
3. Restore compile/test dependencies using `docs/fusion-v6/DEPENDENCY-RESTORATION.md`
   and `docs/fusion-v6/dependency-restoration.json`. Verify every available
   SHA-256 before use. External binaries are prerequisites, not contents of
   the v6 source snapshot. Exact local paths matter to the historical scripts.
4. The source layout is already reconstructed. Do not replay old source patches
   over this candidate. Core build entrypoint from the checkpoint root:
   `python3 source-workspace/gradle-build.py --four-loader --heap-mib 768 fullJar check`
   This runs build/tests only. The wrapper does not launch a game.
5. Core version generation uses Git metadata for a dev build. No `.git` is
   shipped. Restore the public pinned Connector base commit
   `8b27f1ad042aae8037bcc522b321c03fcce1a12a` in a separate Git checkout and
   overlay these exact source files when reproducing its historical dev suffix.
   Confirm the resulting version and embedded source identity. Do not fabricate
   a successful artifact hash if version or other build inputs differ.
6. Full FML sources are at `source-workspace/fml-unified`; BOOT sources are at
   `source-workspace/admission-bootstrap`. The FML build compiles against the
   exact `provenance/compile-classpath-lock.json` files and includes BOOT sources.
   Its default installation policy is unapproved. A reviewed installation policy
   and newly pinned receipts are necessary before any separate runtime test.
7. Product source/build inputs are in `runtime-bundle`; its
   `client-branding.gradle` contains the source-built FML/core pin inputs and
   verification task wiring. Use final FML and core hashes recorded in the
   checkpoint evidence, never substitute the earlier component-test FML hash.
   Responsive preload build/test scripts are in `preload-ui`. Native tests are
   separate from headless tests and require a real display and bounded execution.

`tools/verify_fused_artifacts.py` checks actual rebuilt SERVICE/GAME/FML/PRODUCT
package boundaries without executing their code. Point it at newly built
artifacts and `source-workspace/connector-four-loader`; require its 655-source
check to pass before treating the rebuilt candidate as corresponding source.
Build success alone does not establish runtime acceptance. The published v6 acceptance is a separate recorded client run.

Historical test environment inheritance is a limitation of earlier runtime
evidence. The retained native launcher uses an explicit minimal child
environment, but this checkpoint makes no OS-sandbox or data-transmission claim.


## Installation policy and accepted identities

The raw FML build `bd51010d` is assembled with an explicit pinned installation
policy to produce runtime BOOT `6d431507`. Use the retained FML
`assemble_installation.py`, `validate_launch.py` and `launch_successor.py`
recipes with newly prepared local inputs; old absolute machine paths are not
portable. Do not point a fresh launch at an unreviewed policy or claim its
resulting hash equals the historical accepted artifact without checking it.

The product was compiled against its recorded earlier API-compatible core/FML
inputs; final combined acceptance binds PRODUCT `469118e4` to v6. Rebuilding
against changed dependency bytes may produce a different artifact and requires
a fresh identity and relevant checks. The earlier provider build is preserved
through source continuity and its accepted artifact pin, not a new reproducible
build claim.


## Supported command sequence

After restoring the external pins and toolchains described above, run from
the repository root. These commands do not start a game:

```sh
python3 source-workspace/verify-fusion-source.py
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 fullJar
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 check
```

The final v6 record ran the `fullJar` path and its required core/FART checks.
The second `check` command is a supported complete source-test target once
all fixtures are restored; a fresh execution of it is not claimed here.

For the product, use explicit local paths and the SHA-256 of your newly built
managed core. Set these shell variables to verified files in your own checkout
before invoking the command:

```sh
# CORE_JAR, CORE_SHA256, FML_JAR and CLIENT_MANIFEST are local verified inputs.
tools/java-env.sh gradle -p runtime-bundle --no-daemon --max-workers=1 \
  -Dorg.gradle.jvmargs=-Xmx512m \
  -PmanagedCoreJar="$CORE_JAR" -PmanagedCoreSha256="$CORE_SHA256" \
  -PunifiedFmlJar="$FML_JAR" -PclientClasspathManifest="$CLIENT_MANIFEST" \
  -PqslInventory=../docs/four-loader/quilt/bundled-initial.json \
  jar verifyBundle testClientBranding testInventoryUi testExclusionNotices testProductIsolation
```

Do not use the historical `runtimeDistribution` task for the source-owned
fusion installation: its older two-file mod layout is not the v6 loader
installation. Use the frozen FML installation/launch tools and normalized
recipe references, then create a new local reviewed policy and receipt.

Run all product Python checks only when the Java/Gradle toolchain is present:

```sh
_JAVA_OPTIONS='-Xmx512m -XX:ActiveProcessorCount=1' \
  python3 -m unittest discover -s runtime-bundle/tests -v
python3 -m unittest discover -s source-workspace/fml-unified/tests -v
python3 -m unittest discover -s four-loader/launch-support -p test_game_environment.py -v
```

The four managed-core pin tests intentionally run offline Gradle configuration
with synthetic manifest-only JARs. Binary-dependent QSL structural tests require
an explicitly prepared local candidate. A missing toolchain is a prerequisite
failure, not proof that a pin check passed. No runtime binaries belong in Git.
