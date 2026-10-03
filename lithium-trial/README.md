# First real mod trial: unchanged Lithium Fabric 0.15.4 / Minecraft 1.21.1

> Historical intermediate evidence. The accepted complete-source profile is documented in ../docs/M5-FULL-SOURCE-ACCEPTANCE.md. Referenced historical binaries, raw logs and worlds are not included.

## Result

Native Fabric passes create, save, and reopen. The frozen Unified core fails.
A local source-class experiment fixing three Adapter classes then passes the same
create/save/reopen checks. This is a server smoke/parity result for this one binary,
not a performance result or a general compatibility guarantee.

- Original official Fabric JAR remains unchanged: SHA-256
  `92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa`
- Frozen source-fork core remains unchanged: SHA-256
  `9a6e896e7742fb920469266808c409c76ac0ab84e0d82f7ac4b5ecbe9ee11eb1`
- Trial host is the copied, pinned `f09e465bf467cc5649fa1c66cbe6600bea030d92d9e8d977d7132e9f377b7696`
- Final experimental core:
  `patches/final/unified-infinity-connector-lithium-adapter-experiment.jar`
  SHA-256 `6acb0706519701e6816221a739e8f6d11d0bf280369ba87764b63f8345ef679c`
- Exact files, hashes and world proof: `parity-summary.json`, `artifact-manifest.json`

Native profile: Fabric Loader 0.19.3, Fabric API 0.116.7+1.21.1, Java 21.
Unified profile: NeoForge 21.1.219, the host's nested FFAPI, Java 21.
Only Lithium plus their respective loader/API infrastructure were installed.
No probe mods were added. The native profile binds `127.0.0.1:25568`, Unified
`127.0.0.1:25569`; online mode stays on, RCON/query stay off. No player login,
account token, external game server, or public listener was used. Standard
launcher/server service requests are not evidence of external multiplayer use.

## Observed compatibility defects and repairs

1. Parameter metadata removal: Adapter removed the first two parameters from a
   nine-parameter handler, and moved its six MixinExtras `@Local` annotations
   correctly, but left the explicit annotable parameter count at nine. ASM's
   serializer then indexed past the seven-element array. The source fix removes
   the actual offset-adjusted parameter and decrements matching explicit counts;
   it preserves implicit counts and rejects ambiguous reduced-count layouts.
   Before: descriptor/array/count 9/9/9. After: 7/7/7, with ordinals 0–5 retained
   at indices 1–6. It does not pad arrays or discard surviving annotations.
2. Redirect lookup and receiver type: `LevelReader.getFluidState` is inherited
   through interfaces, which the original redirect postprocessor failed to find.
   Also, the `BlockState.getBlock` invocation was incorrectly assigned the
   declaring superclass (`BlockStateBase`) as its handler's receiver. The fix
   resolves inherited non-private/non-static methods while retaining the exact
   symbolic receiver type used by the invocation.
3. Callback type after a split target: the hopper handler was moved from a
   boolean-returning target to void `markAndNotifyBlock`, but retained
   `CallbackInfoReturnable`. The handler neither uses its callback nor declares
   itself cancellable. Only that provably unused, non-cancellable case is changed
   to `CallbackInfo`; used/cancellable cases remain unchanged and unsupported
   adaptations are not claimed fixed.

The first defect is a transformation/ASM metadata failure; the latter defects
are adaptation/ABI failures. None is attributed to an error in the original mod.

## Evidence

- Native runs: `../logs/lithium-native-{1,2}.{log,json}`
- Frozen Unified failure: `../logs/lithium-unified-1.{log,json}`
- Exact metadata diagnostic: `../logs/lithium-unified-1-diagnostic.log`
- Resolver diagnostic: `../logs/lithium-unified-1-biome-diagnostic-valid.log`
- Final clean-artifact runs: `../logs/lithium-unified-{1,2}-final.{log,json}`
- Final unit suite: `../logs/lithium-final-unit.log`
- Immutable-base negative control: `../logs/lithium-parameter-unit.log`
- Active safeguard audit: `../logs/lithium-final-patch-audit.txt`

Both final cycles reach readiness, receive a save acknowledgement, record all
three dimensions saved, and exit zero. The first creates scoreboard objective
`lithium_trial` and sets `UnifiedInfinityTrial` to `1211154`. The second only
reads that value; it never recreates the objective or sets the value. Its complete
pre-run world-file manifest exactly equals the first run's post-save manifest.
Within each profile, `scoreboard.dat` stays byte-identical across reopen while
`level.dat` changes normally after time/save updates.

NeoForge normalizes the display version to `0.15.4_mc1.21.1`; the exact original
Fabric file hashes and actual Lithium configuration logger are both checked.
The safeguard stayed enabled; its final audit reports seven adapted candidates
successful and zero failed. Seven is not an executed-Mixin count. No claim is made
that all 238 configured server/common Mixins executed.

An intermediate diagnostic shell continued after a compile error and began the
preceding artifact. It was interrupted with exit 130 before any world existed,
and is explicitly excluded: `../logs/lithium-unified-1-biome-diagnostic-aborted.json`.
Later launches are fail-closed, forward termination to the child JVM, and reject
cached failed-audit restarts. The safeguard configuration was never disabled.

## Tests and reproducibility

- 31 removal regression tests / 429 assertions: real Lithium annotation metadata,
  actual transformer apply path, ASM roundtrip, both visibility channels, offset
  semantics, first/middle/last/removal-to-zero, wide local slots, implicit counts,
  unsupported-layout rejection before mutation, and unchanged fixtures
- 79 postprocessor assertions: real host hierarchy, interface/class receiver
  identity, static/private/missing rejection, and 16 callback safety combinations
- The immutable-base negative control reproduces the original ASM exception
- Both suites reran against the exact final non-diagnostic artifact: 508 assertions
- `python3 lithium-trial/patches/build_final.py` produced byte-identical output
  twice; commands/results are in `../logs/lithium-final-build-{1,2}.json`

Only three Adapter classes plus the existing managed environment cache-version
method differ from the pinned core. All other original entry payloads and service
descriptors are verified unchanged. Diagnostic transformer classes are not in the
final patch. This is a source-class patch build, not a complete upstream build.

The shared `getJarCacheVersion` suffix is derived from the base core hash, Adapter
module coordinate, upstream source archive hash, patched source paths/hashes,
managed cache template hash, and compiler identity. Both mapped mod JAR caching
and generated BFU adapter caching consume that method; bytecode and input evidence
are retained in `../logs/lithium-final-cache-{bytecode,input}.txt`.

## Sources and licensing

- Official mod release: https://modrinth.com/mod/lithium/version/mc1.21.1-0.15.4-fabric
- Pinned Adapter source artifact:
  https://maven.sinytra.org/org/sinytra/adapter/core/2.0.43+1.21.1/core-2.0.43+1.21.1-sources.jar
- Adapter upstream: https://github.com/Sinytra/Adapter
- Adapter license: https://raw.githubusercontent.com/Sinytra/Adapter/1.21.x/LICENSE

Adapter is MIT licensed; its copyright/license, complete pinned source artifact,
modified source files, and detailed provenance are included in the final
experimental JAR. The original Lithium binary and metadata are not modified.

## Integration and limits

Use `patches/final/adapter-source.patch` and `patches/final/src/` for review. The
root frozen core/full-source workspace was not edited or published by this task.
The root host output changed during unrelated work; the trial intentionally kept
its previously copied host hash. Integrating these fixes or adopting the newer
host requires a separate regression run against that exact combined build.

No players joined. Client rendering, multiplayer gameplay, extensive game
mechanics, arbitrary modsets, disabled experimental Lithium options, and
performance were not validated. Concurrent builds make elapsed times unsuitable
for comparison.
