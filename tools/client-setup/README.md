# Isolated official client development baseline

Pinned stack: Minecraft 1.21.1, NeoForge 21.1.219 / FML 4.0.42,
NeoForm 1.21.1-20240808.144430, Java 21.0.12.1+1, Gradle 8.11.1,
official ModDevGradle 2.0.143. No game launch is part of preparation.

## Supported development launch

From repository root, after preparation succeeds:

```sh
DISPLAY=:0 python tools/client-setup/gradle_client.py --launch --offline runClient
```

Run this command in the **cloud native desktop terminal through CUA**. The
separate `exec_command` environment does not expose the desktop's X11 socket;
setting `DISPLAY=:0` there alone cannot launch a visible window.

This delegates launch argument generation and the `forgeclientdev` target to
NeoForge's official ModDevGradle plugin. It does not invent a username, UUID,
access token, or login. NeoForge's documentation explicitly describes its
unauthenticated development player. Do not connect this test client to servers.
No user account credentials or Minecraft Launcher data are read or copied.
A normal production launcher session is a separate workflow and requires the
user's legitimate account; the installed production JSON is not fed fake auth.

- Game directory: `run/client-dev/development-game`
- Custom provider setting: `config/fml.toml`, `earlyWindowProvider="unifiedinfinity"`
- Generated launch arguments/classpath: `run/client-dev/development-build/moddev/`
- Real loader progress: `run/client-dev/development-game/compat-progress.json`
- Opt-in QA captures: `preload-ui/reports/client-qa-next` (owned by the UI worker)
- Source scheduler: `unified.infinity.maxWorkers=4`; client heap 512 MiB to 2 GiB

The current profile starts with no progress snapshot. Before an intentional
repeat run, archive the preceding run's generated snapshot and captures so
that only real stages from that run appear. Do not synthesize stage events.

The original four-JAR parity profile put the source-derived Connector,
internally bundled host/API implementation, parity probe, and window provider
directly in `mods/`. The current mixed profile below replaces the parity probe
with three approved real mods. Do not add duplicate provider copies to the module or runtime paths;
pinned FML 4.0.42 discovers ImmediateWindowProvider service JARs in `mods/` early.

## Reproduce preparation

```sh
python tools/client-setup/install_official.py
python tools/client-setup/prepare_distribution.py
python tools/client-setup/gradle_client.py prepareClientLaunch
python tools/client-setup/gradle_client.py --launch runClient --dry-run
```

`install_official.py` runs the unmodified installer. It copies only checksum-
verified immutable dependencies from the separate native baseline. The parent
setup already seeded the official client manifest and client JAR; their hashes
must match the locked first-party manifest. No `--skip-hash-check` is used.
The separate `prepare_distribution.py` checks official hashes and sizes for
Linux libraries, log config, asset index, and all 3,888 unique asset objects.
All download and runtime data stay below `run/client-dev`. Distribution files
are never included in source/Library checkpoints.

The Gradle wrapper uses a profile-private cache and derives proxy JVM options
from the current tool process. An inherited `GRADLE_OPTS` pointing to an old
proxy is explicitly replaced. `NFRT_ASSET_ROOT` shares the already verified
asset store, avoiding a second asset collection. The no-recompilation option
is an official ModDevGradle pipeline setting, not a custom bytecode shortcut.

## Evidence

- `logs/client-setup-installer.log`: official installer exit 0, client patched
- `logs/client-setup-distribution.json`: resource counts and bytes
- `logs/client-setup-prepare-client.log`: official preparation task success
- `logs/client-setup-create-artifacts.log`: full run dependency preparation
- `logs/client-setup-launch-dry-run.log`: generated launch task graph, no launch
- `logs/client-setup-runtime-offline-verify.log`: actual 97-entry runClient runtime resolution, including DevLaunch, verified offline

`prepareClientRun` alone does not resolve the runtime-only DevLaunch artifact.
The custom `prepareClientLaunch` task resolves the official runClient task's
exact classpath provider and writes `client-launch-inputs.json` without invoking
the JavaExec task. Always use this full preparation task before an offline run.
- `run/client-dev/client-layout.json`: production baseline classpath/native paths

## Primary sources

- https://docs.neoforged.net/docs/1.21.1/gettingstarted/
- https://github.com/neoforged/ModDevGradle
- https://maven.neoforged.net/releases/net/neoforged/neoforge/21.1.219/
- https://github.com/neoforged/NeoFormRuntime/blob/main/src/main/java/net/neoforged/neoform/runtime/cli/DownloadAssetsCommand.java

## Connector clean development artifact

The pinned Connector dev branch requires `connector.clean.path`. The Gradle
project exports NFRT's official `vanillaDeobfuscated` result through
`createMinecraftArtifacts.additionalResults` to
`development-build/moddev/artifacts/minecraft-1.21.1-clean.jar` and supplies it
as that JVM property. This is the clean named Minecraft input before NeoForge
binary patching, not the already modified NeoForge game JAR. No Connector
source change or invented artifact-discovery fallback is necessary.

## Actual launch validation

After runtime-classpath caching and clean-artifact configuration, the UI worker
visually verified the real Minecraft 1.21.1 / NeoForge 21.1.219 main menu with
49 mods. Source commit completion, the real GAME overlay, context handoff,
resource reload, and renderer cleanup passed. No further launch is automatic.
The current source/provider hashes and exact generated inputs are locked in
`logs/client-setup-baseline-lock.json`; visual evidence belongs to the UI worker.

The subsequent full-source acceptance run uses core SHA-256
`c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e`
and host SHA-256
`3802215d427501040a432a54e1304e50bbd6758a4610efeea46b0a479641b61e`.
Its previous Connector cache was archived before the cold launch. The same
parity probe 0.2.0 and four direct JARs reached the branded 49-mod main menu,
then exited normally. Exact evidence is in
`preload-ui/reports/client-attempts/05-source-built-client/acceptance.json`.
This is main-menu acceptance, without world, multiplayer, or Lithium client testing.

The profile-local `development-game/profile-mods.lock.json` freezes the exact
JAR names and SHA-256 hashes. Both `prepareClientLaunch` and `runClient`
validate it; preparation also includes the resolved mod records in
`client-launch-inputs.json`. An intentional artifact change requires updating
the profile lock and baseline lock together after verifying the new bytes.

## Current mixed-mod client profile

Attempt `06-mixed-pack-client` uses six direct, byte-pinned JARs: the unchanged
source core, host, and window provider from attempt 05; Fabric Lithium 0.15.4;
Fabric Chunky 1.4.23; and NeoForge Farmer's Delight 1.3.4. It has no parity-probe
JAR and does not substitute the native NeoForge Lithium/Chunky controls.

`stage_mixed_profile.py --stage` performs the explicit one-time transition,
checking approved hashes before writing. It renames the complete preceding
game directory, including its Connector cache, to
`run/client-dev/archived-05-source-built-client-game`. Previous QA output,
baseline lock, and generated launch arguments are preserved in
`preload-ui/reports/client-attempts/06-mixed-pack-client/previous-profile/`.
Existing common configuration and display options are copied into the fresh
game directory; no save, cache, or progress snapshot is carried forward.

Offline `prepareClientLaunch` passed with the official 97-entry runtime. Exact
staged inputs and preparation evidence live under attempt 06. Preparation
does not launch Minecraft. Actual acceptance must be separately coordinated
with the server tests and the available cloud GUI; this remains an isolated
official development-player flow with no account credentials or external
game-server connection.

Actual attempt 06 passed: the cold transformations completed, the custom
window and GAME overlay lifecycle finished, and scoped CUA confirmed the
branded main menu with 51 mods. Quit Game exited with status 0. Full evidence
is `preload-ui/reports/client-attempts/06-mixed-pack-client/acceptance.json`.
An initial command-namespace display failure is preserved separately and is
not counted as a mod-compatibility failure.

## Local mixed-world acceptance

The subsequently authorized attempt `07-mixed-pack-world` passed with the
same six byte-identical JARs. A fresh default-terrain creative world named
`infinity-mixed-acceptance` (seed `2026100301`) was created in the isolated
profile. To bound cloud rendering, its profile uses render/simulation distance
6 and a 60 FPS cap; the preceding options are preserved with the evidence.

Actual CUA interaction exercised Farmer's Delight creative inventory entries,
the placed cooking-pot model and container, its recipe-book screen, and a
tomato transferred into input slot 0. Save and Quit to Title completed; the
same world was selected and reopened, where the same pot and tomato were
visibly present. Both integrated-server cycles saved all dimensions. Final
Quit Game returned exit 0. No multiplayer or LAN flow was entered.

`verify_world_save.py` independently decodes actual `level.dat` and region NBT
using the existing bounded read-only decoder. It verifies the world identity,
seed, player cooking-pot inventory, and the cooking pot at `(-66,64,-206)` with
one tomato in slot 0. It passed against the first and reopened saves, including
their archived copies. This client test did not complete a heated recipe.

The authoritative record, before/after save archives, native F2 screenshots,
logs, and verification reports are under
`preload-ui/reports/client-attempts/07-mixed-pack-world/acceptance.json`.
Attempt 06 remains frozen as separate main-menu acceptance evidence.
