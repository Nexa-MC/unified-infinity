# Native Quilt adapter: implementable first slice

Observed 2026-10-03. Target Minecraft **1.21.1 / Java 21 / NeoForge 21.1.219**. Research only: no production source edits, new game launches, or third-party mod execution were performed by this audit.

## Decision

Implement a narrow native Quilt metadata and Loader-API adapter inside the current coordinated host. Reuse the current discovery pipeline, FFLoader candidate selection, transformation cache, FML admission and host Mixin engine. Prove a `quilt.mod.json`-only **own probe** first. Do not ship the Quilt Loader engine or start Knot, its plugins, its solver, its Mixin bootstrap or another game classloader.

The accepted c892 core recursively contains **zero `org/quiltmc/**/*.class` definitions**. Its discovery accepts `fabric.mod.json`, its parser expects Fabric JSON, and boot code invokes only Fabric entrypoint interfaces. Current Fabric tests, even for mods advertised as Quilt-compatible, prove no native Quilt loading.

## Compile/reference pins

- Quilt Loader **0.30.1**, last non-prerelease entry in the observed Maven list. Reference tag commit `b33861b30a815f327652015018d2d1262f12b63a`. Later `0.31.0-beta.4` exists; do not silently float to it.
  - Official binary: https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader/0.30.1/quilt-loader-0.30.1.jar
  - SHA-256 `a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb`
  - Sources: same directory, `quilt-loader-0.30.1-sources.jar`, SHA-256 `66d1b1214179306574b730f0841a63d9499d47d1ea16b912ef336f6a2c62a08a`
- Quilt Base API **10.0.0-alpha.5+1.21.1**, Maven coordinate `org.quiltmc.qsl.core:qsl_base:10.0.0-alpha.5+1.21.1`, upstream mod ID **`quilt_base`**
  - Official binary: https://maven.quiltmc.org/repository/release/org/quiltmc/qsl/core/qsl_base/10.0.0-alpha.5+1.21.1/qsl_base-10.0.0-alpha.5+1.21.1.jar
  - SHA-256 `7eb4ec613f901ef7232f9f84ee91be5576f00682f32ad9c9f7b1a679bcf82465`
  - Sources SHA-256 `8eeaa11ec49031c9c0fa1532d7b678de34a3d4cd79b70f4b61c4e56cff831d30`
- Optional second-stage lifecycle reference: `org.quiltmc.qsl.core:lifecycle_events:10.0.0-alpha.5+1.21.1`, mod ID **`quilt_lifecycle_events`**
  - SHA-256 `1a1f9b72c38e2475b471df1dcff7992d6ae4955e8a2cd8288bb3ba3986768aa4`
  - Requires `quilt_base >=10.0.0-alpha.5+1.21.1`, `quilt_loader >=0.25.0`, Minecraft `=1.21.1 OR =1.21`

These downloaded JARs are reference/compile-only inputs, **not permission to execute or add them wholesale to the managed profile**. Pin own source-built API implementation and its build identity separately. Keeping upstream API class names and mod IDs does not justify claiming complete Quilt Loader 0.30.1 behavior. An internal compatibility-provider version must be coupled to an enforced feature profile; never erase a `quilt_loader` dependency or accept every version.

## Exact entrypoint ABI

Loader:

```java
package org.quiltmc.loader.api.entrypoint;
public interface PreLaunchEntrypoint extends GameEntrypoint {
    void onPreLaunch(org.quiltmc.loader.api.ModContainer mod);
}
// Metadata key: pre_launch
```

QSL Base:

```java
org.quiltmc.qsl.base.api.entrypoint.ModInitializer
    void onInitialize(org.quiltmc.loader.api.ModContainer mod); // init
org.quiltmc.qsl.base.api.entrypoint.client.ClientModInitializer
    void onInitializeClient(org.quiltmc.loader.api.ModContainer mod); // client_init
org.quiltmc.qsl.base.api.entrypoint.server.DedicatedServerModInitializer
    void onInitializeServer(org.quiltmc.loader.api.ModContainer mod); // server_init
```

`org.quiltmc.loader.api.QuiltLoader` is a **static facade**, not Fabric's `getInstance()` interface. First-probe useful calls:

```java
static Optional<ModContainer> getModContainer(String id);
static Collection<ModContainer> getAllMods();
static boolean isModLoaded(String id);
static Path getGameDir();
static Path getConfigDir();
static boolean isDevelopmentEnvironment();
static MappingResolver getMappingResolver();
static <T> List<T> getEntrypoints(String key, Class<T> type);
static <T> List<EntrypointContainer<T>> getEntrypointContainers(String key, Class<T> type);
```

`ModContainer` has `metadata()`, `rootPath()`, default `getPath(String)`, `getSourcePaths(): List<List<Path>>`, `getSourceType(): BasicSourceType`, and `getClassLoader()`. A native admitted candidate reports `NORMAL_QUILT`; builtin API providers report `BUILTIN`. Its source paths describe the **original source**, while rootPath exposes the admitted resource view. Return the existing host game classloader, never allocate a new one.

`ModMetadata` requires `id()`, `group()`, `version(): Version`, `name()`, `description()`, `licenses()`, `contributors()`, `getContactInfo(String)`, `contactInfo()`, `depends()`, `breaks()`, `icon(int)`, `containsValue(String)`, `value(String): LoaderValue`, and `values()`. `Version.raw()` preserves the original version string. A lossy `getId/getVersion` wrapper alone is not ABI compatibility. Preserve the original Quilt metadata alongside the Fabric candidate projection; separate host/JPMS-safe module names from upstream IDs.

`EntrypointContainer<T>` supplies `getEntrypoint()` and `getProvider()` (Quilt container). `EntrypointUtil.invoke(name, type, BiConsumer<T, ModContainer>)` must call each entrypoint with its own provider; its `Consumer` and `invokeContainer` overloads are also public API. Implement entrypoint exception aggregation without losing mod/source context.

`LanguageAdapter.create(ModContainer, String, Class<T>)` uses **Quilt** ModContainer. The default adapter supports class construction, static field references and method references (`Class::member`); FFLoader's generic default reflection is reusable for class-based probes but a Quilt custom adapter is not a Fabric adapter. Reject custom adapters initially rather than casting them incorrectly.

## Native metadata and bounded dependency profile

Read `quilt.mod.json` with required `schema_version: 1` and `quilt_loader` object containing `group`, `id`, `version`. Quilt metadata is not a renamed Fabric document.

The upstream reader recognizes JSON5 by a `.json5` filename, but `StandardQuiltPlugin` permits it only in an opted-in development environment and **rejects it in production**. Explicitly reject/report `quilt.mod.json5` in this production profile rather than silently classifying the JAR as not a mod. Preserve parse-location errors and reject trailing data; do not apply a permissive format rewrite.

- `quilt_loader.entrypoints`: key -> single string, `{adapter,value}`, or an array of these. Keep native keys unchanged
- `quilt_loader.language_adapters`: adapter-name -> implementation class
- `quilt_loader.jars`: array of nested-path **strings**, unlike Fabric's `{file:...}` objects
- `quilt_loader.depends` / `breaks`: arrays of dependency strings/objects; object fields include `id`, `versions`, `reason`, `optional`, `unless`
- Top-level `depends` elements are jointly required; an array **inside** a `depends` element means alternatives (`Any`). An array inside a `breaks` element means a conjunction (`All`). Do not flatten these into mandatory Fabric dependencies
- Version ranges have string/array and explicit `{any:[...]}` / `{all:[...]}` forms; preserve SemVer/non-SemVer semantics. Notice the plural field `versions`
- Group-qualified dependency IDs (`group:id`), versioned `provides`, `unless`, and `load_type` (`always`, `if_possible`, `if_required`) carry semantics absent from a flat Fabric metadata projection
- `quilt_loader.provides`: strings or objects with ID/group and independently specified version. Fabric `Collection<String> getProvides()` cannot represent that independent version
- `mixin`: root string, object `{config, environment}`, or array; Quilt uses `dedicated_server` for its server environment
- `minecraft.environment`: `*`, `client`, or `dedicated_server`
- `access_widener`: root string **or array**. Current Connector `getClassTweaker()` supports one resource, so initially accept at most one or reject with exact feature diagnosis
- Retain other root metadata/custom values such as `modmenu` and `quilt_loom`; do not assume injected interfaces or custom metadata imply runtime support

**Initial own probe:** explicit intermediary mappings, top-level root mod, default Java entrypoints, flat mandatory dependencies for `minecraft =1.21.1`, `java >=21`, and the managed Quilt API providers, no `provides`, custom adapters, nested JARs, conditional dependencies or load-type overrides. Parse known but unsupported features and fail closed before class definition. Preserve the full AST now, extend same solver integration later. Do not introduce a second independent solver or quietly loosen dependencies.

## Mapping and Mixin boundaries

Use `quilt_loader.intermediate_mappings: "net.fabricmc:intermediary"` explicitly. Quilt's 0.30.1 parser defaults an omitted field to `org.quiltmc:hashed` **but then rejects hashed mappings itself**. It also recognizes experimental Mojang mappings only when its resolver exposes them. Thus do not equate Quilt Mappings source names with hashed runtime bytecode or claim generic hashed support.

Current `JarTransformer.SOURCE_NAMESPACE` is `intermediary`. The existing remapper, refmap remapper and Adapter patch path can handle an intermediary-native Quilt mod's **Minecraft references**, once its metadata is correctly admitted. This does not implement Quilt API references. Bridge Quilt MappingResolver to the **same** FFLoader mapping owner for the six matching API methods; report actual runtime namespace, not a fictitious intermediary namespace.

Quilt's native bootstrap uses `#modid:config` and its Knot Mixin service understands the prefix. The host Mixin service does not gain that behavior by parsing Quilt JSON. Do not call `QuiltMixinBootstrap.init()`. Feed adapted owned config paths into existing FML Mixin metadata, detect resource-name collisions, and use one engine. Initial probe uses a unique config filename. Preserve environment filtering; current FabricJarReader additionally scans unlisted mixin-like filenames, which must not accidentally activate a Quilt config excluded by environment.

The current `EnvironmentStripperTransformer` only recognizes Fabric `@Environment`, `@EnvironmentInterface`, `@EnvironmentInterfaces`. Add proper Quilt side annotation semantics for `@ClientOnly` / `@DedicatedServerOnly` before admitting probes that depend on stripping; otherwise reject them. Entry point side filtering alone does not prevent client-only references elsewhere from linking on a server.

Quilt side annotations have CLASS retention, apply to types, TYPE_USE, fields, methods, constructors and packages, and expose `stripLambdas() default true`. Type-use on an implemented interface can remove the interface; methods must be annotated separately. This is wider than matching two annotation descriptor strings on fields/methods.

## Exact insertion map

All paths below are relative to `source-workspace/connector-combined/` unless stated otherwise.

1. `src/main/java/org/sinytra/connector/locator/FabricModsDiscoverer.java:92-105`: currently checks only `fabric.mod.json`. Add native Quilt recognition through the same locator and retain a format discriminator. Define dual-descriptor precedence explicitly; initially reject ambiguous dual/native descriptors rather than double admit
2. `transformer/.../jar/FabricJarReader.java:27-58`: directly opens Fabric metadata and calls Fabric parser. Dispatch to a dedicated Quilt reader; return a common internal metadata carrier with original Quilt AST and Fabric `LoaderModMetadata` projection. Do not mutate input JARs or insert fake Fabric metadata
3. `src/main/.../locator/ConnectorLocator.java:178-193`: recursive nested traversal uses `getJars()`. Future Quilt string paths can project here; retain archive safety limits, parent-child provenance and digest validation. No alternate recursive scanner
4. `src/main/.../locator/DependencyResolver.java:49-76,101-119`: creates `ModCandidateImpl` and calls the existing `ModResolver.resolve` once. Supply the exact representable Quilt constraints and explicitly owned API providers. Unsupported constraints fail before this call. Eventually extend this one candidate/solver model, not a parallel Quilt resolution pass
5. `src/main/.../locator/FabricModMetadataParser.java`: existing in-memory FML metadata path can remain final host admission. Carry original identity independently from Connector's current dash-to-underscore/JPMS normalization
6. FFLoader source in `docs/integration-audit/sources/ForgifiedFabricLoader-FabricLoaderImpl.java:232-276`: setupMods already iterates arbitrary entrypoint keys and stores generic typed entrypoints. Retain this single storage; Quilt facade adapts containers and errors, not a second registry of independently instantiated entrypoints
7. `src/main/.../ConnectorEarlyLoader.java:145-158`: add `pre_launch` dispatch once after setup alongside existing Fabric `preLaunch`, using Quilt `ModContainer`. Ensure prelaunch cannot execute twice across existing hooks
8. `src/mod/java/org/sinytra/connector/mod/ConnectorLoader.java:37-62`: current coordinated early initialization calls registry modification, Fabric common initializer, then side initializer. It is the smallest candidate orchestration point for **initial** Quilt init dispatch. However upstream QSL init occurs immediately before vanilla builtin-registry freeze, client_init before GameOptions construction, and server_init in dedicated Main after EULA. Preserve ordering with explicit stage contracts and own-probe assertions rather than claiming this existing position is automatically equivalent
9. Existing `src/mod/.../mixin/boot/MinecraftMixin.java` calls ConnectorLoader at client constructor's Thread.currentThread; `ServerMainMixin.java` calls it before NeoForge ServerModLoader.load. Existing registry mixins defer vanilla freeze. Use these established host boundaries with one coordinated dispatch owner; do not run upstream QSL bootstrap mixins **and** own callbacks, which would double initialize
10. `transformer/.../jar/JarTransformInstance.java:79-112`, `.../patch/EnvironmentStripperTransformer.java`, and `src/main/.../service/FabricMixinBootstrap.java`: same transform/side/mixin ownership, with native metadata-aware extension. Include parser/API/source pins in build identity and cache key

## Probe and acceptance sequence

### Q0: loader-only native identity and prelaunch

Own JAR contains **only quilt.mod.json**, a uniquely named resource and own Java class implementing Quilt PreLaunchEntrypoint. It records once-only execution, exact raw ID/group/version, resource readback, original input SHA/path, source type, provider and entrypoint classloader identity, and lookup through QuiltLoader. Missing/unsupported dependency negative control must fail before its class static initializer. Input JAR SHA unchanged before/after cold and warm launches. Native Quilt reference launch is a later approved differential control, not already verified.

### Q1: native QSL init and host transformation

Extend own JAR with QSL `init`, `client_init`, `server_init` implementations compiled against upstream ABI; deploy only the explicitly implemented internal base API slice. Verify common once, correct side once, wrong side never loaded, before-freeze content registration, and a vanilla-target Mixin sentinel actually executes through the existing host engine. Add one access-widener case separately, plus a method-reference entrypoint. Record actual Minecraft object behavior, not just logs declaring “loaded.”

### Q2: bounded event contract

Implement QSL event API semantics needed by own probe, then one lifecycle bridge. QSL Event is not a type alias for Fabric Event: it has listener phases, automatic `events`/`client_events`/`server_events` entrypoint registration, and phase ordering. `ServerLifecycleEvents.READY` callback is `readyServer(MinecraftServer)`; it runs after world initialization before first tick. Lifecycle contains STARTING, READY, STOPPING, STOPPED, tick and world events. Choose one host hook per event, verify order/counts and create/save/reopen; do not add generic event replay. First stage need not claim these events.

### Q3: approved official native mods

Use exact static shortlist in `candidates/`. Approve individual binaries and dependency closure before execution. OP Tab is a compact actual native initializer candidate but is client-only in practice despite missing metadata side guard; no dedicated-server claim. Other candidates add larger surfaces. Do not confuse a Fabric JAR with Modrinth Quilt label with native support.

Every stage reruns Fabric Lithium+Chunky and native NeoForge Farmer's Delight controls. Keep source/version/API capability claims separate from runtime pass claims. No cross-version or universal Quilt claim follows from this slice.

## Current upstream availability

Official Maven QSL **10.0.0-alpha.5+1.21.1** resolves **30 nonempty module JARs** through 11 POMs. `qsl-availability.json` records every exact URL, SHA-256/SHA-512, class count and native metadata. This is stronger current evidence than the 2024 [two-module transition announcement](https://quiltmc.org/en/blog/2024-07-03-qfapi-moving-forward/), which must not be applied as today's complete Maven inventory. All downloaded module metadata accepts 1.21.1/1.21; artifact presence does not establish runtime correctness or host compatibility.

QFAPI release metadata and Maven list do **not** show a published 1.21.1 aggregate; the latest relevant published line is **11.0.0-alpha.3+0.102.0-1.21**, bundled with QSL10.0.0-alpha.1. A current **source branch** named1.21.1 exists (`1869b119d88199e2d03146048de043dfaae5297f`) but is not proof of a published release. The qsl Modrinth query specifically for1.21.1 returned an empty array. Do not package the older full QFAPI aggregate on top of FFAPI: duplicate Fabric APIs, event providers and modules would violate single ownership. Adapt required QSL-facing APIs into the managed graph, retaining upstream IDs.

## Evidence

- `audit-lock.json`: reference pins, source-file hashes, accepted core digest and zero Quilt-class result
- `fetch-provenance.json`: official metadata/source/download URLs and digests; failed guessed branch/spec/artifact URLs are recorded honestly
- `qsl-availability.json`, `inspect_qsl_availability.py`: complete current alpha5 module static inventory
- `upstream/loader-0.30.1-sources/`: actual published source API/parser/Mixin implementations, not guessed signatures
- `upstream/qsl-alpha5-sources/`: published base/lifecycle/etc source and bootstrap timing
- `candidates/`: official candidate metadata, unchanged downloads and static details

All downloaded code remains research data. No source publication is implied or performed.
