# Minimal meaningful source integration

## 0. Fix the current false authority immediately

The existing Python planner is useful bounded inspection. It is not equivalent to
FML + JarJar + Connector + the fork ModResolver.

Confirmed conflicting behavior in `compat_admission/core.py` as audited:

- `scan_bytes:350–351` rejects all NeoForge JarJar input, including our working host
- All nested Fabric JARs are appended to `self.mods`, then considered active providers
  if side matches; candidate selection/optional nested origins are not modeled
- `resolve` treats duplicate IDs/providers as unconditional errors, whereas real
  loaders select some library/mod candidates and reject other ambiguity cases
- `neoforge` ignores native `[[mods]].provides`; the runtime uses it for API aliases
- The custom Python version matcher implements a restricted dialect, not the exact
  runtime parser/solver and override policy
- `exactly one descriptor` rejects dual-metadata jars that runtime reader precedence
  may handle; an unsupported inspection case is not proof runtime cannot load it
- A user-supplied API inventory carries `provided_inventory_only` and cannot prove
  executable implementations or replace actual selected FFAPI modules

### Correct report model

Separate three things explicitly:

1. **Artifact preflight:** passed / blocked / incomplete; resource-safety limits,
   file identity and metadata observations only
2. **Resolution:** deferred_to_runtime / resolved / failed, with authority and
   evidence stage; the static scanner does not produce runtime `resolved`
3. **Compatibility evidence:** unverified / exercised behavior, keyed to exact
   runtime/mod hashes and side; neither of the above implies compatibility

A limitation in the scanner is not a security failure. Valid JarJar may be recorded
as `deferred_to_runtime`; enumerate declarations safely when implemented, preserving
parent/coordinate/range/included version without selecting a winner. If nested
bytes cannot yet be fully inspected, mark coverage `incomplete`. Do not quietly
label the entire archive security-checked while skipping unbounded nested content.
Unsafe paths, overlapping ZIP members, expansion-budget violations and changing
inputs may still block preflight. Unknown metadata/range dialects should be explicit
unsupported/incomplete observations, not a claim about the host loader.

Keep strict metadata diagnostics as lint facts if desired, but separate `blocking`
and `authority` from severity. Static API-profile restrictions (e.g. forbidding a
standalone API aggregate in a pinned managed profile) should be labeled **profile
policy**, not general incompatibility. Enforce that policy at the actual selected
runtime snapshot if it matters for execution; do not accept a fabricated inventory.

Minimum immediate regression tests:

- Current valid Unified host and nested FFAPI do not fail solely for JarJar support
- A normal parent with two competing nested versions is unresolved until runtime,
  not duplicate-rejected by static inventory
- Security checks still reject malicious/budget-exceeding nested archives
- Native underscore IDs + explicit hyphenated `provides` are preserved as evidence
- Partial scans cannot return full-inspection success
- CLI exit/report semantics distinguish hard artifact block from incomplete/deferred
  inspection (version the JSON contract rather than silently changing old meaning)

The exact historical rejection is in `current-preflight-host.json`.

## 1. First actual runtime source patch

### Change the real path, keeping one SPI identity

Patch the pinned upstream `ConnectorLocator` and `JarTransformer`, retaining their
upstream package/class/service identity initially. Do not ship both old and new
providers. Have `ConnectorLocator.scanMods` use one coordinator for its existing
stages; move stage state and work ownership into that coordinator so it cannot be
bypassed by a second local scanner/resolver. Leave NeoForge/FML host providers in
place.

A useful initial state machine:

```text
NEW → HOST_SNAPSHOT → DISCOVERED → SELECTED → TRANSFORMED → VALIDATED
    → SUBMITTED_TO_HOST → HOST_FINAL_OBSERVED → ENTRYPOINTS_OBSERVED
any stage → FAILED (retain original exception, stage, artifact provenance)
```

`SUBMITTED_TO_HOST` is not `LOADED`. FML's second uniqueness pass and validation
still run after Connector returns. A coordinator scoped only to the locator can
truthfully stop at `SUBMITTED_TO_HOST`; the post-discovery hook may later attach
host-final evidence. Do not manufacture later milestones from progress percentages.

The narrow source patch is meaningful only if it changes actual ownership:

- exactly one discovery transaction and one authoritative candidate result
- same selected artifacts feed transforms, generated-jar handling and host submission
- one bounded transformation scheduler, with no competing executor or transform pass
- failures prevent normal submission while upstream error-display cleanup still runs
- explicit candidate/success/cache-hit/error counters are produced from that same work
- later consumers read the immutable snapshot instead of independently rescanning

A progress facade that merely watches two independent loaders would fail this gate.

### Preserve existing execution contracts

1. Pass the host-discovered file snapshot to the existing Connector environment.
2. Preserve native-ID exclusion, generated libraries, aliases/overrides, nested parent
   links and ModResolver semantics exactly in this first patch.
3. Use upstream `JarTransformer` implementation for real work. A bounded executor
   can replace `newFixedThreadPool(paths.size())`; do not expose concurrent whole
   transactions because the Mixin bytecode provider/ClassInfo cache is global.
4. Ensure cancellation drains/stops workers before clearing global bytecode state.
   Preserve interrupt status and report failure; upstream currently catches
   `InterruptedException` and returns an empty list, which must not be interpreted
   as a successful empty selection.
5. Retain `MixinTransformSafeguard` and prior-error abort before committing outputs.
6. Preserve the generated adapter mixin JAR and split-package merge/filters.
7. Preserve `finally` loading of Connector's embedded mod/runtime and package
   filtering so useful errors still reach FML's error UI.
8. Preserve early SPI placement: no constructor-time JarJar extraction.
9. Include a source/patch digest in `TransformerUtil.getCached` version input, along
   with existing upstream invalidation data. The same identity must also reach
   `BytecodeFixerUpperFrontend` generated-adapter caching via the environment. Stale upstream cache reuse is not a
   valid warm-start result for changed transformation behavior.
10. Keep atomic snapshot writing off the mutable decision path. An optional UI
    cannot own admission or invalidate successfully selected candidate identities.

### Minimum snapshot fields

- stage, monotonically increasing sequence, run/session identity, environment/side
- upstream artifact and source-fork identities (do not masquerade as original bytes)
- original input digest, origin/parent chain, effective mod ID/version/aliases
- selected/excluded/deferred status and responsible owner/reason
- raw-vs-effective dependency changes (aliases and ignored loader constraints)
- transformation input/output digest, cache hit/miss + fingerprint, audit status
- generated mixin artifact, submission identity, later host-final mod/module identity
- structured failure category, original cause and responsible stage

Avoid storing credentials or unrelated machine information. Paths intended for
portable reports can be relative to the run profile.

## 2. Factoring: core, loader SPI, game adapter, upstream components

### Core (`infinity-core`, target-independent)

Own immutable artifact/provenance records, candidate decision trace, stage state
machine, policy identity, diagnostics taxonomy, exactly-once work tokens,
resource budgets and bounded scheduling interfaces. Core must not import
Minecraft classes, FML classes, Mixin implementation internals or FFAPI types.
It must not implement another Fabric/Maven version solver. Core's contracts say
which adapter owns a decision and what evidence has been obtained.

### NeoForge loader integration (`infinity-host-neoforge`, FML 4.0.42 contract)

Own `IModFileCandidateLocator`/`IDependencyLocator` integration, host discovery
snapshot, candidate-to-IModFile projection, resource/module-layer handoff, diagnostic
translation, provider enumeration and host-final outcome observation. Reuse exact
FML JarJar and host validation; never create a second game classloader. Private
field accesses to ModLauncher/SecureJar live here or in explicit pinned upstream
patches, not generic core.

### Minecraft version adapter (`infinity-mc-1.21.1`)

Own mapping resource identity and namespaces, clean/patched bytecode providers,
NeoForm/host pin, registry phase hooks, class/member descriptors used by transforms,
side-specific bootstrap injection points, and Mixin adaptation compatibility tests.
A future game version requires another validated adapter. Renaming a JAR is not a
version adapter.

### Reused upstream implementation modules

- Connector Fabric discovery/metadata translation, remapping, split-package handling
- Forgified Fabric Loader metadata/API/entrypoint/mapping support and actual resolver
- Sinytra Adapter transformation logic
- FFAPI implementations, preserving public packages, logical aliases, resources,
  configuration names and original authorship
- One host-selected Mixin engine, ASM and other host-managed infrastructure

Keep source pins and a small readable patch stack rather than copying broad trees
into generic core or inventing a second loader API. The same source build can
ultimately emit one managed distribution without implying that all code was newly
written or that multiple binary packages are architecturally forbidden.

## 3. Dormant components and safe consolidation

Binary evidence identifies:

- Connector shades 193 `net/fabricmc/loader/...` classes and no Knot launcher
- FFAPI aggregate carries 43 nested JARs; one is the standalone FFLoader
  `2.5.68+0.18.4+1.21.1` (3,539,919 bytes)
- That nested loader has `FabricLoaderHackyInjector` as a language-loader provider
- Connector's shadow configuration removes that language-loader service; its own
  early provider supplies the dummy loader module and its own init path
- `FabricLoaderHackyInjector` would inject `FabricLoaderBootstrap`, whose
  `initializeLaunch` also calls `FabricLoaderImpl.addFmlMods`

This is a real competing bootstrap **if activated**, not proof it is active today.
The code is not automatically safe to delete: reflection, resource lookup and
third-party references make a class-name inventory insufficient for reachability.

Next source-build cleanup after the first pipeline patch is stable:

1. Build FFAPI in a managed profile that depends on the selected loader API at
   compile time but does not `include`/JarJar the older standalone loader; its build
   currently contains that `include` plus `runtimeOnly` dependency
2. Keep the official-byte baseline profile for differential regression
3. Assert one definition owner of `FabricLoaderImpl`, `MappingResolverImpl`,
   metadata resolver and bootstrap service in all effective module layers
4. Retain the dummy guard initially against third-party bundled copies; removal
   requires an explicit selected-provider policy with tests, not just removing
   our own duplicate nested JAR
5. Preserve logical API modules and their generated native entrypoints; do not
   flatten them into a constructor that repeats `onInitialize`
6. Build a reachability/resource/service/reflection inventory before considering
   further removal of dormant bootstrap classes; do not run blind shrinkers

This step changes FFAPI artifact bytes and must have new provenance, not the
unchanged-upstream claim or original hash. It is useful cleanup, but only becomes
architectural consolidation together with the one-owner runtime pipeline.

## 4. Acceptance matrix

No one synthetic probe is sufficient. Keep the same input hashes and separate worlds.

| Area | Required evidence |
|---|---|
| Provider ownership | Enumerate exactly one Connector locator/service/coremod; one selected FabricLoader singleton/code source; one Mixin engine |
| Candidate semantics | Root and nested versions, duplicate roots, nested library override, native `provides`, global alias, environment exclusion, missing dep, cycles, disabled mods |
| Native final validation | Report host-final failures even if Fabric selection/transform succeeded; native ordering constraints still enforced |
| API conflict policy | Standalone native Fabric API, older/newer FFAPI, nested API copies; report the actual selected owner and explicit managed-profile restriction |
| Transformation | Cold output, warm hit, patch-digest invalidation, failed mixin, failed transform, interrupted workers, generated adapter JAR |
| Classpath | Same class origin, no package split regression, no second game loader, no early target class definition |
| Entry points | Each third-party main/side/preLaunch fires once; each native FFAPI GeneratedEntryPoint initializes once; a failure is attributed correctly |
| Registries | Native/Fabric custom item/block registration, IDs before/after freeze, add callback exactly once, save/reopen identity |
| Events | Server start/stop, tick, world/chunk unload, save and resource reload; phase order, count, thread and error behavior |
| Mixed mods | Native-only, Fabric-only, native+Fabric pair, independently passing pair versus native control |
| Client | Separate client launch, rendering hooks, client initialization, network join; dedicated server is not evidence for this row |
| Upstream upgrades | Source diff/patch rebase, service ABI/private-field tests, changed mapping/cache identity, full matrix rerun |

Pass criteria for the first source patch: binary/source provenance reproducible;
unchanged unaffected entries verified; original services still singular; old/native
probe behavior and failure diagnostics preserved; scheduler/cancellation/cache tests
pass; real cold + warm server runs prove the patched classes are the ones executed.
A runtime progress file alone cannot establish any of those results.
