# Forge 52.1.0 Mojmap vertical slice

This component is an implemented, bounded adapter. The unchanged own Forge-only
Item probe passed create/save/reopen on the frozen bda743b2 core and 9a6239e4 host;
see repository docs/four-loader/forge/IMPLEMENTED-SLICE.md for exact evidence. It is **not full Forge
compatibility** and imports no Forge runtime. Runtime acceptance must be recorded
separately for each unchanged original mod and exact core/host artifact.

## Single-owner integration

- `ForgeModFileReader` joins native FML's reader transaction. Original Forge-only
  `META-INF/mods.toml` candidates become derived cache artifacts before FML's
  incompatible-Forge fallback. Native NeoForge descriptors retain native reader
  precedence. A Forge-only candidate with Fabric/Quilt metadata is rejected as
  ambiguous. The existing Fabric/Quilt scanner does not resubmit Forge inputs
- `Forge52Metadata` retains the original descriptor verbatim and records its
  projection. Source `javafml` loader range is checked against Forge 52.1.0;
  effective language is `unified_forge_52` implementation 1.0.0. A Forge
  dependency maps to the real `unified_forge52_adapter` capability mod, retaining
  its original range/order/side. `mandatory=false` becomes host `optional`, never
  required. Host FML still owns final uniqueness, dependency sorting and feature
  validation
- `ForgeModLanguageLoader` creates a host `ModContainer` subclass in the existing
  game module layer. It implements Forge's context-constructor-first / zeroarg
  fallback contract with one construction attempt and attributable exceptions
- The mod lifecycle bus is a native host bus with the host marker and per-phase
  dispatch support. Native common-setup and queued-work objects are used directly
- Game-layer registry facades delegate to the actual NeoForge DeferredRegister
  and DeferredHolder. They preserve stable Supplier facade identity, key/id,
  presence and Forge's premature-get NullPointerException. Only BLOCK/ITEM keys
  and the corresponding ForgeRegistries identity views are exposed
- Native global ServerStarted and explicit ServerTickEvent.Post objects are used
  directly. The exact Post `haveTime()Z` member becomes native `hasTime()Z`

No second classloader, lifecycle engine, global bus, Mixin engine, registry, Forge
implementation, or new freeze schedule is introduced.

## Admission and cache

`Forge52Symbols` is an exact type/member allowlist. It covers descriptors,
annotations, generic signatures, constant method types, method handles and lambda
bootstrap arguments. Unsupported Forge types/members, direct Forge API
subclasses/interfaces, reflective Forge class strings and SRG Minecraft members
fail clearly. Descriptive javac Forge InnerClasses records are omitted rather than
pretending the incompatible TickEvent base hierarchy exists on NeoForge.

The cache key includes immutable original SHA-256, complete generated source
BuildIdentity/cache suffix, rule hash, exact game/host/FML/bus/Forge ABI profile and
side. Outputs are committed with an atomic move, checked against SHA-256 receipts
before reuse, and rebuilt on corruption. Failed transforms do not produce valid
cache entries. Original JARs remain unchanged. The derived JAR embeds an audit at
`META-INF/unified-infinity/forge52-audit.json` and keeps the exact original TOML.

ZIP paths/duplicates, entry count, metadata size, class size and total uncompressed
size are bounded before admission. This first slice rejects signed JARs rather
than silently invalidating signatures, nested JARs, multi-release/module-info,
services, ATs, coremods and Mixin metadata. Native descriptor precedence is not a
claim that a dual-packaged native NeoForge mod passed Forge adaptation.

## Verification

Run from the Connector root:

- `bash components/infinity-forge/run-adapter-tests.sh`: static metadata, ASM,
  genuine Forge probe transformation, immutable input, provenance and cache tests
- `bash components/infinity-forge/run-facade-tests.sh`: exact pinned host ABI,
  constructor/context, host lifecycle queue and registry facade contract tests
- Root `compileJava`, `compileModJava`, `fullJar` and `check` build the integrated
  candidate. Game launches are coordinated externally and are never part of these
  scripts

The static fixture is the independently compiled original Forge-only probe with
SHA-256 `3a016e8b8340c7c10b6490f15bb7452c1555363035c7373f4d81ccfacfde15fe`.
Its verified native Forge create/reopen control is separate evidence. A derived
static artifact alone is not a Unified runtime pass.

## Subsequent Clumps event slice

The source now also rewrites Forge boolean post to a static bridge that invokes
its supplied native host bus once and returns final native cancellation. Plain
custom Event subclasses and exact native PickupXp are supported without a new
bus or dispatcher. Validated same-JAR service descriptors and direct-Mojmap
manifest Mixin configs are preserved and projected to native FML registration.
The exact original Clumps artifact passes static transformation, transformed
payload checks and actual native/Unified six-to-one orb merging, XP72 conservation
and saved-world reopen on the frozen26b core. See repository
docs/four-loader/forge/CLUMPS-RUNTIME-ACCEPTANCE.md for exact pins and limits.

## Deferred surfaces

General Forge cancellation annotations/results/phase contracts, base TickEvent
fields/listeners, generic listeners, automatic subscribers,
capabilities, network/config/client extensions, arbitrary registries, service
providers outside the validated same-JAR shape and Forge-specific game patches are unsupported here. They require
separate semantic implementations and immutable-input runtime tests. Clumps 19.0.0.1 has a bounded merge/persistence runtime pass; player pickup and
Mending gameplay remain untested.
