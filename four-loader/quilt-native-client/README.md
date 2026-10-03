# PASS: native Quilt OP Tab client acceptance

Attempt3 passed actual main menu,19-entry creative Op Tab, OP Sword enchantments, save/reopen, independent saved-NBT verification, and graceful exit0. See `native-client-acceptance.json` and `logs/client-3/`. Original approved JARs remain unchanged; runtime named outputs are official Loom derivatives, individually pinned. Audio and multiplayer were not tested.

# Genuine Quilt OP Tab client control

Runtime attempts 1 and 2 reached genuine Quilt cold remapping, then exited137 before any game window. Original inputs remained byte-identical. Attempt2 captured shared hierarchical cgroup memory pressure (oom_kill16→21); exact killer attribution is not established. No OP Tab UI/world acceptance is claimed yet.

Current mode prepares the exact original closure through official Quilt Loom before the game, then replays its sealed official IDE-style DevLaunchInjector configuration after Gradle exits. No mod bytecode is hand-edited.

## Pinned, isolated inputs

- Minecraft 1.21.1; existing Java 21.0.12.1+1 and Gradle 8.11.1
- Official Quilt Loom 1.8.5, published Gradle plugin API requirement 8.10
- Genuine Quilt Loader 0.30.1, SHA256 `a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb`
- Yarn 1.21.1+build.3 v2 for the normal supported development runtime
- Original OP Tab 2.0.0V1.21.1+1.21, SHA256 `6121446645d4521ddb5deae40e506fb02a7d4f06c0ce049fabc6ecaed548c296`
- Original QSL base and lifecycle 10.0.0-alpha.5+1.21.1
- Original Fabric API 0.116.7+1.21.1, SHA256 `08018cc48c97415a38016a00dbd5a2c7a460ba6b7a051690a8cb3dbb5e8482a4`

The four original mod JARs are preserved unchanged in `run/quilt-native-client/original-mods`. Their48 nested Fabric API modules are extracted byte-identically into `original-nested-mods`; all52 files are normal official Loom modRuntimeOnly inputs. The game mods directory is intentionally empty to prevent duplicate original/named admission. The official Fabric API Maven POM adds a GameTest module absent from the approved aggregate; that broader POM closure is not used.
Their complete direct/nested static inventory has 52 unique IDs and is captured
in `provenance/mod-closure.json`. OP Tab uses native QSL `init` but calls
FabricItemGroup, supplied by original Fabric API. It declares no client-side
guard although its code is client-specific: this is a client-only acceptance.
Original Quilt handles discovery, dependency solving, transformation and its
own Mixin bootstrap. No Unified/Connector/NeoForge classes belong on this runtime.

`seed_verified.py` reads the established official client resources and independently
checks the Mojang manifest hashes before copying them to the profile-private
Loom cache. All 3,888 asset objects are SHA1-verified. No prior profile, world,
option, account, launcher credential, or asset-store file is overwritten.

## Supported developer flow

The project uses official Quilt Loom `runClient`, its generated launch.cfg,
DevLaunchInjector, and genuine Quilt KnotClient. No account arguments are
supplied. Quilt's own unchanged MinecraftGameProvider supplies its ordinary
development fallback; no production launcher JSON or account token is fabricated.
No external game-server join, LAN flow, or account sign-in is in scope.

The official Loom source establishes that original mods found in `mods/` are
eligible for Quilt's runtime remapping; classpath mods are exempt. Consequently
the original OP Tab and API bytes remain on disk. The first two attempts used genuine Quilt
runtime remapping; the current mode delegates intermediary-to-named remapping to
official Loom and explicitly records original and derived hashes. The unchanged
genuine Quilt engine handles runtime discovery, side filtering and Mixin loading.

Preparation commands (no game launch):

```sh
python four-loader/quilt-native-client/seed_verified.py
python four-loader/quilt-native-client/gradle_client.py prepareClientLaunch
python four-loader/quilt-native-client/gradle_client.py --offline prepareClientLaunch
python four-loader/quilt-native-client/verify_profile.py --runtime
```

The command-namespace sandbox rejects Loom's unconditional Unix-domain-socket
capability probe with `Operation not permitted`, even with the approved escalated
preparation command. This occurs before game launch. Use the allocated cloud
native terminal for this official preparation; do not patch the plugin or
disable loader checksum checks. The separate Minecraft JVM still requires
runtime + desktop-slot assignment before `--launch --runtime-slot-approved --offline runClient`.

## Vendor provenance and discrepancy

Quilt meta's 0.30.1 checksum fields hash checksum-text rather than Loader bytes.
The exact metadata and correct official Maven SHA256 sidecar are preserved
under `provenance/`, with the original verification in the sibling native-server
control. Loader bytes must match the official sidecar, never the known-wrong
meta hash. Fabric API and Loom sources were independently matched to their
official Maven SHA256 sidecars in `sidecar-checks.json`.

Primary upstream sources:

- https://github.com/QuiltMC/quilt-template-mod/tree/1.21
- https://maven.quiltmc.org/repository/release/org/quiltmc/loom/1.8.5/
- https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/0.30.1/
- https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/0.116.7+1.21.1/

These are development preparation and static-closure evidence, not proof that
the real OP Tab menu or creative world has passed. Actual visual/create/save/
reopen results need separate recorded acceptance after the assigned launch.

## Resource-bounded direct development launch

Standalone Loom preparation uses768MiB and2 processors, and must exit before
the client starts. The captured official client config is256MiB initial/1536MiB
maximum heap and2 processors. The direct launcher checks original sources,
all derived runtime bytes, exact52-mod identity closure, genuine Loader digest,
exact generated properties, main class, arguments and actual Loom classpath
argfile. Only representation changes: the temporary @classpath file is replaced
by the identical -classpath value used by an IDE. No auth/session argument is added.
It refuses to start while any Gradle JVM is visible and records local plus
hierarchical cgroup counters and limits before/after the exact child PID.

After native-terminal preparation succeeds and runtime is assigned:

```sh
python four-loader/quilt-native-client/direct_launch.py --launch --runtime-slot-approved --attempt 3
```
