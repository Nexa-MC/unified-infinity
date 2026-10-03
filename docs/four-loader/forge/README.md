# Forge 52 / Minecraft 1.21.1 binary-adapter audit

Research date: 2026-10-03 UTC. **Research and static inspection only. No Forge
installation, mod launch, runtime change, or compatibility pass is recorded here.**

## Decision in brief

Use an explicitly scoped Forge-52 adapter within Unified's existing discovery,
transform/cache, and NeoForge/FML class-definition pipeline. Do not load a second
Forge runtime, event dispatcher, registry implementation, Mixin engine or game
classloader. The first meaningful target is one independently compiled Forge-only
probe covering its real constructor/context, event registration, a deferred block
and item, tick callback and world save/reopen.

Merely renaming `mods.toml` or `net.minecraftforge` is not that target. Exact
released sources show binary-incompatible constructors, registry return types,
event-bus return descriptors and tick-event structure. See [ABI-SLICE.md](ABI-SLICE.md)
for the concrete signatures and the bounded implementation order.

## Reproducible target

- Keep Minecraft **1.21.1**, Java **21**, NeoForge **21.1.219**, FancyModLoader
  **4.0.42** and NeoForged bus **8.0.5** fixed
- Use official recommended Forge **1.21.1-52.1.0** as the initial reference ABI and
  proposed native control. At capture, official promotions also list **52.1.16**
  as latest; this audit does not silently upgrade to it
- The exact 52.1.0 MDK pins Minecraft/official mappings to 1.21.1, Java 21,
  wrapper Gradle **8.12.1**, and ForgeGradle range **[6.0.24,6.2)**. That range is
  not a reproducible resolved ForgeGradle version. Resolve and lock a concrete
  plugin and its dependencies before building the own probe; do not change the
  accepted Unified core's existing Gradle 8.11.1 toolchain merely to match an MDK
- Reference Forge event bus: **net.minecraftforge:eventbus:6.2.27**. Reference
  loader artifacts are `fmlcore`, `fmlloader`, `javafmllanguage` at
  **1.21.1-52.1.0**. They are inspection/build inputs, not runtime dependencies to
  add wholesale to the NeoForge process

Primary release sources:

- https://files.minecraftforge.net/net/minecraftforge/forge/index_1.21.1.html
- https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json
- https://maven.minecraftforge.net/net/minecraftforge/forge/1.21.1-52.1.0/
- https://github.com/MinecraftForge/MinecraftForge/tree/1.21.1

`source-lock.json` hashes the successful static downloads. `inspection/` contains
selected files extracted from those exact release artifacts, and `javap` output
from them or the already-pinned NeoForge host. A moving branch is supplementary,
not the authority for ABI decisions.

Run `python docs/four-loader/forge/verify_research.py` to verify the pinned inputs
and captured inspection files. This reads static evidence only, verifies the
now-approved Clumps artifact against its frozen digest, and never loads mod classes.

## Actual game namespace, not an inference from loader name

The official 52.1.0 **production distribution uses Mojang names**:

1. Its MDK has `reobf = false` and explicitly describes official runtime mappings
2. Its install profile runs `DOWNLOAD_MOJMAPS`, renames vanilla into `MC_OFF`,
   and applies the Forge patch to that official-named result
3. Static disassembly of production `universal.jar`'s `DeferredRegister` invokes
   named Minecraft members such as `ResourceKey.createRegistryKey` and
   `ResourceLocation.fromNamespaceAndPath`
4. `universal-srg.jar` is a **different artifact**, used by the userdev config.
   `ForgeHooks.class` has 178 distinct SRG-shaped `m_..._`/`f_..._` constants in
   this artifact and zero in production `universal.jar`. This count is a useful
   cross-check, not a general namespace detector by itself
5. Even the downloaded official **52.0.1 MDK** disables reobfuscation. The official
   52.1.16 changelog traces the change to Forge **50.0.0 / Minecraft 1.20.6**

Therefore the pinned own-probe route is **Mojmap -> Mojmap plus Forge API
adaptation**. Do not reuse Connector's intermediary mapping under a Forge label.
Do not manufacture an unconditional SRG-to-Mojmap pass for normal Forge 52 mods.

For arbitrary candidate binaries, inspect actual member references and all Mixin
configs/refmaps. Nonstandard build mappings, old patterns in bundled libraries,
reflection strings and mixed namespace inputs require explicit evidence. An
SRG-profile route must be independently versioned, tested and keyed in the cache
if/when a real approved input needs it. The official MDK used here does **not**
include a Mixin/refmap fixture; no Mixin-refmap compatibility has been verified.
An own-Mixin fixture should be a subsequent, separate acceptance gate.

## Existing source ownership and insertion points

Accepted actual source tree: `source-workspace/connector-combined/`. Historical
`integrated-loader/` individual-class overlays are not the edit target.

Accepted core SHA-256:
`c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e`

Accepted host SHA-256:
`3802215d427501040a432a54e1304e50bbd6758a4610efeea46b0a479641b61e`

- One `ConnectorLocator` currently orchestrates Fabric discovery, resolution,
  transform, split-package handling and host submission. Its methods are
  Fabric-specific, so passing Forge metadata to `FabricJarReader` is invalid
- `components/infinity-core` owns bounded scheduling/resources/progress;
  `components/infinity-host-neoforge` owns the managed transform environment;
  `components/infinity-mc-1.21.1` owns clean game class lookup;
  `transformer/`, `components/infinity-fart`, and `components/infinity-adapter`
  contain the complete already-integrated source implementations
- FML performs candidate discovery, final uniqueness/dependency validation,
  language loading, module layers and class definition. The final host outcome
  remains authoritative; a preflight graph is not proof of loaded compatibility
- Host `JarModsDotTomlModFileReader` reads only
  `META-INF/neoforge.mods.toml`. The FML fallback explicitly categorizes
  `META-INF/mods.toml` as `MINECRAFT_FORGE` incompatibility. A Forge-aware reader
  must participate in the host reader transaction before that fallback, retain
  origin and avoid rediscovering the same input through a second scanner
- Forge language handling belongs in a host language adapter/provider or
  deliberate generated native-entrypoint mechanism, not a late runtime-bundle
  constructor. Preserve host lifecycle and its one module layer
- Use the existing source build/cache identity, adding the Forge adapter source,
  source ABI level, namespace evidence, transform rule set and dependency plan.
  Original JARs remain unchanged; derived cache outputs retain origin hashes

The reader/provider integration must be designed together with the parent's
four-loader transaction changes. No runtime integration is made by this audit.

## Admission differences that need explicit policy

| Forge 52 input | Current host | Required treatment |
|---|---|---|
| `META-INF/mods.toml` | `META-INF/neoforge.mods.toml` | Read original metadata once; project effective host metadata with provenance |
| `modLoader="javafml"`, `loaderVersion="[52,)"` | Built-in JavaFML 4.0.42 | Validate against supported Forge ABI, not Neo loader number; do not broaden to any version |
| required `forge` dependency/range | native `neoforge` ID/version | Explicit supported adapter-capability check; do not claim Neo version 21.1.219 satisfies Forge 52 |
| `mandatory=true/false` | `type=required/optional/...` | Translate mandatory and optional semantics; blindly copying makes false optional dependencies required because Neo defaults to REQUIRED |
| `@net.minecraftforge.fml.common.Mod` | `@net.neoforged.fml.common.Mod` scanner | Adapt annotation ownership or use a specific Forge language provider; preserve one initializer |
| `Mod.EventBusSubscriber` nested annotation, `Bus.FORGE` | separate `EventBusSubscriber`, `Bus.GAME` | Explicit annotation/type/enum-member translation and side filtering, if admitted |
| metadata/manifests for ATs, services, JarJar, module opens | host-specific processing | Inspect and gate; no indiscriminate stripping or service discovery |

The first own probe can deliberately avoid JarJar, access transformers,
coremods, reflection, automatic event subscribers, custom language adapters and
Mixins. Such absence narrows the proven surface; it does not make those features
compatible. Ambiguous dual-loader metadata must get an explicit decision, not a
filename guess.

## What this would and would not prove

After the planned controls pass, the claim is an unchanged **own Forge 52 probe**
loaded through Unified on the fixed NeoForge host, with the listed API slice and
save/reopen behavior. A third-party mod pass needs a separately approved exact
artifact and observable behavior. A later pack failure must first be reproduced
with each mod alone/native before attributing it to an interaction.

Unsupported until separately implemented/tested: Forge registries beyond the
listed block/item surface, custom registries, capabilities and invalidation,
network handshake/protocols, config scopes/events, custom event posting,
cancellation/results/generic event typing, client render extensions, missing
Forge game patches, coremods, ATs, Mixins and cross-loader mod APIs. The two
projects patch different Minecraft behavior even where Java class names match.

See [CANDIDATES.md](CANDIDATES.md) for the now-approved exact Clumps test artifact,
its verified API surface and the recorded approval boundary.
