# Actual ownership and initialization graph

All class names below are real classes inspected at the pinned baseline. References
prefixed `old/` mean `../research/upstream/`; `src/` means this folder's `sources/`.
Line numbers describe the captured source, not a moving branch.

## 1. Execution graph, in dependency/phase order

The graph describes phase constraints. SPI construction and service callbacks are
host-driven; do not infer one flat total order from source declaration order.

```text
ModLauncher / FML host bootstrap
  ├─ ConnectorLoaderService.onLoad
  │    └─ reorder existing launch plugins: mixin first,
  │       lenient runtime_enum_extender, connector_pre_launch, remaining plugins
  ├─ ConnectorLoaderService.initialize
  │    └─ wrap ImmediateWindowProvider.updateModuleReads; install thread factory
  │
  └─ FMLLoader.beginModScan → ModDiscoverer.discoverMods
       ├─ candidate locators findCandidates
       │    ├─ native NeoForge mod candidates (includes Unified host)
       │    └─ ConnectorEarlyLocatorBootstrap.findCandidates
       │         └─ dummy net.fabricmc.loader LIBRARY, version 999.999.999
       ├─ UniqueModListBuilder.buildUniqueList [initial native set]
       ├─ dependency locators, service-priority order
       │    ├─ JarInJarDependencyLocator.scanMods
       │    │    └─ JarSelector.detectAndSelect
       │    │         └─ Unified host → FFAPI aggregate → selected API modules
       │    └─ ConnectorLocator.scanMods [LOWEST_SYSTEM_PRIORITY]
       │         ├─ locateFabricMods(host-discovered files)
       │         │    ├─ snapshot native IDs, library module names, BOOT packages
       │         │    ├─ FabricModsDiscoverer.scanFabricMods
       │         │    ├─ JarTransformer.cacheTransformableJar
       │         │    │    └─ FabricJarReader.readModMetadata
       │         │    │         └─ ModMetadataParser + overrides → wrapped metadata
       │         │    ├─ discoverNestedJarsRecursive; parent-child graph
       │         │    ├─ shouldIgnoreMod / handleDuplicateMods
       │         │    ├─ DependencyResolver.resolveDependencies
       │         │    │    └─ ModResolver.resolve → ModSolver
       │         │    ├─ JarTransformer.transform(selected candidates, native libs)
       │         │    │    └─ JarTransformInstance.transformJar + upstream adapter
       │         │    ├─ MixinTransformSafeguard if failing selected mixins
       │         │    ├─ SplitPackageMerger.mergeSplitPackages
       │         │    └─ createConnectorModFile → host IModFile metadata
       │         ├─ pipeline.addModFile; record original paths; add generated mixins jar
       │         └─ finally: ForgeModPackageFilter; loadEmbeddedJars
       │              └─ native JarJar scan of Connector's runtime/mod jars
       ├─ UniqueModListBuilder.buildUniqueList [native + dependency results]
       └─ ModValidator.stage1Validation

FMLLoader.completeScan / ModValidator.stage2Validation
  ├─ language validation → ModSorter.sort → LoadingModList
  ├─ addAccessTransformers, addMixinConfigs, addEnumExtenders, background scan
  └─ host builds PLUGIN / GAME resources and module layers

ConnectorPreLaunchPlugin.initializeLaunch
  ├─ ConnectorEarlyLoader.init
  │    └─ LoadingModList → FabricLoaderImpl.addFmlMods [one-way API projection]
  ├─ FabricMixinBootstrap.init [decorate existing Mixin configs]
  └─ FabricASMFixer.injectMinecraftModuleReader

ImmediateWindowProvider.updateModuleReads wrapper
  ├─ ConnectorEarlyLoader.setup → FabricLoaderImpl.setup
  │    └─ setupLanguageAdapters; setupMods → EntrypointStorage
  ├─ define dummy target to initialize Mixin plugins safely
  └─ ConnectorEarlyLoader.preLaunch → invokeEntrypoints("preLaunch")

Host/game entrypoint boundary
  ├─ server: ServerMainMixin injects before ServerModLoader.load()
  ├─ client: MinecraftMixin injects in Minecraft constructor
  └─ datagen: DatagenModLoaderMixin selected begin boundary
       └─ ConnectorLoader.load
            ├─ NeoForgeRegistriesSetupAccessor.invokeModifyRegistries(null)
            └─ FabricLoader.invokeEntrypoints("main") + side entrypoint

FML native @Mod construction (FFAPI + Unified host + native mods)
  ├─ FFAPI generated GeneratedEntryPoint → API implementation onInitialize
  │    └─ register host event bridges / mixin-supplied hooks
  └─ RuntimeBundle constructor → check connector/fabric_api/forgified_fabric_api IDs
       [late diagnostic only; cannot own discovery or transformation]
```

Evidence: `old/connector-ConnectorLoaderService.java:44–100`; exact FML sources
`FML-ModDiscoverer.java`, `FML-FMLLoader.java:126–147`,
`FML-ModValidator.java:47–102`; `old/connector-ConnectorLocator.java:50–168,272–275`;
`src/Connector-ConnectorPreLaunchPlugin.java:25–33`;
`src/Connector-ConnectorEarlyLoader.java:105–154`;
`old/connector-ConnectorLoader.java:37–62`; captured boot mixins; and
`src/FFAPI-GeneratedEntryPoint.javap.txt`.

## 2. Ownership by decision

| Decision | Current authoritative implementation | What Unified may own | What it must not duplicate |
|---|---|---|---|
| Archive safety | Project bounded scanner, if used before execution | Byte-budget/integrity policy and diagnostics | A claim that inspection executes a sandbox or proves mod safety |
| Native metadata interpretation | FML readers / ModFile / ModInfo | Provenance and projection adapters | Independent TOML semantics that gate valid FML input |
| Fabric metadata interpretation | FabricJarReader → fork ModMetadataParser → ConnectorFabricModMetadata | Store raw and effective metadata, reasons for changes | Reparse/rewrite different policy in Python/core |
| Native nested libraries | JarInJarDependencyLocator → JarSelector | Record candidates, selected coordinate, range and origin | Flatten all embedded JARs into active mods |
| Fabric discovery | FabricModsDiscoverer and ConnectorLocator recursive discovery | One discovery transaction with stable artifact identities | A second recursive scanner feeding another classloader |
| Fabric candidate choice | Connector DependencyResolver → fork ModResolver/ModSolver | Sole orchestration and decision record | A second version/SAT implementation |
| Final host admission/order | FML second uniqueness pass, ModSorter, LoadingModList | Compare committed plan against host-final outcome | Treat provisional transform candidates as final loaded mods |
| Runtime classpath/definition | FML/ModLauncher module layers; Connector split-package adaptations | Submit once through host pipeline; record package owner | New URLClassLoader, Knot launcher, copied class definition path |
| Namespace map | Fork MappingResolverImpl / mappings.tsrg | Version adapter supplies immutable map identity | Independent reflection/refmap/name mapping |
| Mod transformation | JarTransformer/JarTransformInstance; Sinytra Adapter | Schedule each chosen input once; bounded workers; cache identity | Second bytecode pipeline with competing order |
| Mixin application | Host-selected Sponge Mixin; Connector decorates/adapts | Verify config ownership and order | Embed or bootstrap another Mixin engine |
| Registry storage/freezing | Minecraft/NeoForge, with pinned Connector/FFAPI hooks | Version-specific lifecycle contract and assertions | Shadow registry, independent freeze schedule |
| Fabric entrypoints | Connector phase hooks + fork EntrypointStorage | Exactly-once state and trace at those existing hooks | Invoke entrypoints from late RuntimeBundle constructor |
| API event callbacks | FFAPI event implementations and source-specific hooks | Trace and contract tests | Generic universal event bus replaying the same events |

## 3. Candidate decisions are not interchangeable

### Native JarJar

`JarInJarDependencyLocator.scanMods:39–54` delegates to
`JarSelector.detectAndSelect`, reading nested metadata and using the host's file
reader. `loadModFileFrom:58–66` creates a `jij:` filesystem with a parent discovery
attribute. Its resolution identifies Maven group/artifact plus included/requested
versions. That is not the same identity as a logical Fabric mod ID.

### Fabric candidate solver

`DependencyResolver.resolveDependencies:49–76` passes Fabric candidates, FML
metadata projections, Java, Fabric-loader API and MixinExtras builtins to the fork
`ModResolver.resolve`. Recursive candidates preserve parent links and mark nested
paths separately (`101–118`). `ModResolver` delegates selection to `ModSolver`,
then returns selected candidates; the Connector caller only transforms returned
Fabric candidates for the current side.

Important existing compatibility policies that must be recorded, not silently
reimplemented:

- Native same-ID mods and disabled mods are filtered before transformation
- Loom-generated libraries are compared with already present module names
- Some library conflicts are compared by Maven artifact version
- Placeholder native mod versions are lowered to `0.0`
- Global aliases are added to the fork API, alias-related dependency ranges widened,
  aliased `breaks` dropped, and `fabricloader` constraints removed by the wrapper
- Native metadata `provides` is retained; absent explicit aliases, underscored native
  IDs may be exposed as hyphenated Fabric aliases
- FabricLoader's synthetic candidate advertises its major/minor with a wildcard
  patch version, rather than strict equality with the actual API artifact

Sources: `old/connector-ConnectorLocator.java:183–268`;
`old/connector-DependencyResolver.java:49–145`;
`src/Connector-ConnectorTransformerEnvironment.java:97–100`;
`src/ForgifiedFabricLoader-FMLModMetadata.java:65–89`.

### Final FML reconciliation

`FML-UniqueModListBuilder.buildUniqueList` groups by module/first ID, selects newest
versions in some cases, then detects remaining logical-ID and library conflicts.
`ModValidator.stage2Validation` and `ModSorter.sort` apply the host's dependency
and ordering rules. The fork's `FMLModMetadata.getDependencies()` returns an empty
set: the Fabric solver is not a replacement for validating native dependencies.
Therefore a report produced immediately after Connector's solver is **provisional**.

## 4. Classpath and transformation are already coupled

`ConnectorTransformerEnvironment.getRuntimeClassProvider` exposes native library
bytes through `EarlyJSCoremodTransformer`, while `getCleanClassLookup` supplies
clean version-specific Minecraft bytes. Both are needed for accurate adaptation.

`JarTransformInstance.transformJar` performs (in builder order): signature stripping;
field-to-method/class-tweaker and reflection/class analysis transforms; namespace
renaming; Mixin patch adaptation; accessor redirects; refmap rewrite; optional
access-widener transform. It finalizes mixin configs/refmaps after writing the JAR.
Generated library metadata takes a distinct non-remapping branch.

The runtime namespace is `mojang` (`ForgifiedFabricLoader-LoaderUtil.java:28`),
source is `intermediary` (`old/connector-JarTransformer.java:38–39`). The resolver
loads `/mappings.tsrg`; map bytes and target host/NeoForm identities belong in a
version-adapter/cache fingerprint, not scattered filename heuristics.

`JarTransformer.transformJars` temporarily replaces the host Mixin plugin's bytecode
provider, then clears stale Mixin ClassInfo cache entries in `cleanupEnvironment`.
Do not run multiple independent transform transactions concurrently against that
global state. Parallelism inside one controlled transaction still needs upstream
shared-state validation; a bounded pool alone does not establish thread safety.

`SplitPackageMerger` and `ForgeModPackageFilter` modify package visibility before
module construction. They are not cosmetic deduplication and must remain part of
the versioned host adapter until equivalent behavior is tested. Filtering uses
private `SecureJar`/union-filesystem fields; upstream version bumps can break it.

## 5. Mixin engine and lifecycle ownership

- FML selects the Sponge Mixin implementation (`baseline-lock.json` records
  `net.fabricmc:sponge-mixin:0.15.2+mixin.0.8.7`)
- Connector's loader service makes the host `mixin` launch plugin first and its
  `connector_pre_launch` plugin after it
- `FabricMixinBootstrap.init` decorates already-known configs with compatibility
  settings; it is not a second call to initialize a separate engine
- Connector's adapter transforms Fabric mixin bytecode and refmaps on cached copies
  before FML class definition
- `ConnectorPreLaunchPlugin` widens non-private Minecraft members after Mixin;
  moving it earlier/later changes the access contract

Registry order is version-specific. Connector suppresses vanilla registry freeze
calls (`BuiltInRegistriesMixin`) and suppresses one NeoForge listener registration
(`NeoForgeRegistriesSetupMixin`, ordinal 1). `ConnectorLoader.load` manually invokes
`modifyRegistries` before Fabric initializers. This is not permission for a new core
to unfreeze/re-freeze registries independently. Exact-once/phase assertions and
mixed-mod tests are needed before changing any of those hooks.

## 6. Event bridges: one source for each callback

Real example from the baseline lifecycle API:

```text
FML @Mod construction
 → org.sinytra.fabric.lifecycle_events.generated.GeneratedEntryPoint(IEventBus)
 → LifecycleEventsImpl.onInitialize()
 → NeoForge.EVENT_BUS.addListener(ServerStartedEvent, ...)

NeoForge ServerStartedEvent
 → registered FFAPI listener
 → ServerLifecycleEvents.SERVER_STARTED.invoker().onServerStarted(server)
 → ArrayBackedEvent ordered registered listener array
```

The same implementation bridges chunk/world load/unload, server start/stop, tick,
tags and equipment change. Other callbacks use direct mixins instead:
`MinecraftServerMixin.reloadResources` and `saveAllChunks` invoke reload/save
callbacks. A blanket re-post of all NeoForge events or all lifecycle phases would
create duplicate/wrong-order callbacks.

`ArrayBackedEvent.register` and `addPhaseOrdering` maintain the callback array and
phase topological ordering. Keep this implementation for Fabric API semantics;
a core event bus must not substitute its own cancellation, ordering, or threading.

Registry API example:
`FabricRegistryInit.objectAddedEvent` creates one event per Registry with
`computeIfAbsent` and attaches one native `AddCallback`. `addRegistry` temporarily
unfreezes the registry-of-registries only when needed and restores its freeze state.
These are API implementations, distinct from the host lifecycle's global registry
construction/freeze schedule.

Evidence: `src/FFAPI-GeneratedEntryPoint.javap.txt`;
`src/ForgifiedFabricAPI-LifecycleEventsImpl.java:39–129`;
`src/ForgifiedFabricAPI-MinecraftServerMixin.java:37–65`;
`src/ForgifiedFabricAPI-ArrayBackedEvent.java:31–123`;
`src/ForgifiedFabricAPI-FabricRegistryInit.java`.
