# Reconstructing the accepted four-loader source

This package is complete source correspondence for the accepted core; it is not a
standalone installer or a promise of a fresh-machine bit-identical build. No heavy
build or game run was repeated during publication.

## Source-only verification

```sh
python3 source-workspace/verify-four-loader-source.py
```

This checks all 390 source/build records, recovered helper digests, and published
host/provider source correspondence without Java, Gradle, network or game execution.
The earlier M5 source package and its verifier remain available separately.

## Ordinary upstream Git context

The build uses upstream GradleUtils/JGit to form its version. Prepare an ordinary
clone at Connector commit `8b27f1ad042aae8037bcc522b321c03fcce1a12a`; do not build the
loose source snapshot as if it had that Git context. For example:

```sh
git clone --no-checkout https://github.com/Sinytra/Connector.git source-workspace/connector-four-loader-rebuild
git -C source-workspace/connector-four-loader-rebuild checkout --detach 8b27f1ad042aae8037bcc522b321c03fcce1a12a
python3 -c "import shutil; shutil.copytree('source-workspace/connector-four-loader', 'source-workspace/connector-four-loader-rebuild', dirs_exist_ok=True)"
python3 source-workspace/verify-four-loader-source.py --source-root source-workspace/connector-four-loader-rebuild
```

Use a fresh destination. The overlay supplies the accepted Java, build, properties,
resources and component license files while the pinned clone supplies unchanged
upstream Git context/resources. The verifier rejects changed/missing identity files
and unexpected Java sources. Do not substitute the historical core26b patch for the
accepted source snapshot. Its nine recovered test helpers are already included.

## Tools and external inputs

- Java21 (recorded compiler/runtime 21.0.12.1+1-LTS) and installed Gradle8.11.1
- Official pinned NeoForge/FML/ModDevGradle dependencies and their resolved source/build
  inputs; the 169 accepted dependency digests are retained in the accepted identity
- Exact QSL10.0.0-alpha.5+1.21.1 base/lifecycle inputs at the paths referenced by the
  accepted build. Coordinates and checksums are in `quilt/bundled-initial.json`,
  `quilt/fetch-provenance.json` and `quilt/qsl-availability.json`
- The unchanged official mod JARs needed by a chosen test/control, obtained separately
  from the recorded publishers and verified against its lock. They are not distributed
- Original product/provider artwork remains at its existing M5-verified paths

The core uses ModDevGradle's official binary-only pipeline with `CI=true`. After
preparation, an installed Gradle can target the reconstructed directory, for example:

```sh
CI=true "$GRADLE_HOME/bin/gradle" --no-daemon --max-workers=2 --no-parallel -p source-workspace/connector-four-loader-rebuild fullJar check
```

Honor the recorded resource caps and prerequisite checks. This command is a
reconstruction recipe, not a publication-time successful-build claim. Adapter userdev
still declares a mutable snapshot; observed digest evidence does not freeze a future
network resolution. Changed dependency bytes must produce a new identity and regression.
The supplied original wrapper also supports `--four-loader` when the selected source
location has been prepared with its expected ordinary Git context and tool layout.

## Controls and limitations

Harnesses are research fixtures with explicit pinned input and saved-world checks.
Some already accepted shared hopper/mixed-pack helpers are included only because
the accepted combined-control lock identifies their exact bytes. Recreate dependency
profiles and regenerate preparation locks before an intentional new run. Read each
control's scope; a project-owned Quilt server probe is not the real OP Tab client.

Historical launcher processes inherited their environment. Do not treat these
fixtures as an OS sandbox, credential-isolation mechanism, general mod-security
analysis or proof of no transmission. Environment hardening and successor UI/policy
work are separate and are not silently mixed into this accepted source publication.
