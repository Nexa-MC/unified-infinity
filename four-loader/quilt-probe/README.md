# Native Quilt first-slice fixture

Target: Minecraft 1.21.1, Java 21; adapted host NeoForge 21.1.219.
Build: `python3 four-loader/quilt-probe/build.py` from repository root.
Compile-only official inputs are verified in `build.py` and the generated build report. The JAR contains only `quilt.mod.json`, not a synthetic Fabric descriptor. It contains no Fabric/NeoForge API references.

## Runtime protocol

Use the exact original `quilt_base` and `quilt_lifecycle_events` QSL 10.0.0-alpha.5+1.21.1 modules, and the fixture from `build/build-report.json`. On the unified host the Loader API is supplied by the host facade; never add the original Quilt Loader engine. A separate genuine Quilt control uses the original Quilt Loader 0.30.1 engine.

1. Fresh world: JVM property `unified.quiltProbe.phase=create`
2. Wait for `NATIVE_QUILT_PROBE PASS stage=ready_to_save ticks=5`
3. Issue ordinary server `save-all flush`, then `stop`
4. Independently read `world/data/unified_quilt_probe.dat`: its `data.marker` string must equal `native_quilt_qsl_alpha5_v1`
5. Reopen the same world with `unified.quiltProbe.phase=reopen`
6. Assert `stage=ready phase=reopen ... read_before_write=true`, then the five-tick sentinel again
7. Stop cleanly and compare original input JAR SHA-256 before/after both launches

Markers prove typed native `pre_launch`, `init`, `server_init`, method-reference order, original identity/group/version/source, one host classloader and item registry, QSL automatic event registration, real READY/tick/STOPPED callbacks, a vanilla-target Mixin, and actual Minecraft SavedData create/reopen. `ClientProbe` is side annotated and must not execute on dedicated server. The fixture does not claim to prove the full client lifecycle or all QSL modules.

Each negative fixture is independently built and hash pinned. Run it in place of the positive fixture, keeping the same module closure. Missing-dependency and too-new-loader-version cases must fail without `NATIVE_QUILT_PROBE CLASS_DEFINED`.

## Capability boundary

The host owns one candidate graph/resolver, FML admission path, game classloader and Mixin engine. Native metadata is parsed strictly in memory; full native AST and original source provenance accompany the host candidate projection. Original installed JARs are not modified.

Supported first profile: schema 1 JSON, explicit intermediary mapping namespace, default Java class/field/method entrypoints with native keys, simple mandatory and break dependencies with flat OR version alternatives, basic metadata, side-filtered Mixin configs and at most one AW. Unsupported JSON5, conditional/optional/group-qualified/compound dependency structures, custom language adapters, versioned provides and native nested mods fail before class execution. Side annotations support class/package/member stripping and nongeneric interface type-use; unsupported field/method type-use and generic stripped-interface signatures fail explicitly.

Only the two exact QSL hashes are treated as managed providers. Their original IDs, versions, bytecode inputs and licenses are retained. The transformed view suppresses QSL base bootstrap/test mixins so the unified host dispatches each native stage exactly once; original QSL EventRegistry and lifecycle implementations remain in use. The public inventory contains 30 actual available QSL modules, but only these two are selected for this slice.

## Validation status

A successful build or focused regression test is not a game-runtime pass. See the separate control/host launch reports for actual outcomes. No publication is performed by this fixture builder.
