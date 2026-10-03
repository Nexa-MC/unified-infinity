# Combined four-loader server regression

Combined server create/save/reopen PASS; see Runtime acceptance below. All files here are new;
existing lane controllers, core, probes, accepted worlds and archives are unchanged.

## Exact composition

- Source-built core `98d86a92e91a20df980cc95abc8ced4972476edff7ec982d08c88e3d4e8579fd`
- Freshly matched internal-QSL host `746ca5e3fcaf64ae7b67836535d8aa0bcb5d1cb4fe37161cc811784cca5adbd4`
- Existing provider `7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99`
- Original Fabric Lithium 0.15.4 + Chunky 1.4.23
- Original native NeoForge Farmer's Delight 1.3.4
- Original Forge Clumps 19.0.0.1 and unchanged own Forge Clumps comparison fixture
- Unchanged own native Quilt probe 0.1.0+native

`common.py` contains every exact original archive hash. The host supplies pinned
original internal QSL base/lifecycle plus FFAPI; no external QSL or second loader
engine is installed. The harness invokes one NeoForge21.1.219 / FML4.0.42 process,
using the existing shared admission, registry, game classloader and Mixin path.
Startup evidence requires one host Mixin service and exactly one preparation of
each original Forge archive. Quilt's original probe checks host classloader,
unique native container and registry identity.

## What must pass together

Wait for server-ready plus BOTH original probes' ready-to-save markers. Their
controllers are not started independently, and no premature freeze/save/stop can
bypass natural Clumps entity ticks or Quilt's five-tick lifecycle/Mixin sentinel.

The original mixed-pack harness's methods perform bounded nine-target Chunky
pregeneration at (2048,2048), radius16, then freeze and exact game-time steps:
create 8+260; reopen 8+32. FD hopper transfer/cooking, five inventory snapshots
per observation, block identities, lit stove, persistent contents and no pending
Chunky task are retained. Independent saved region decoding requires all nine
targets full and canonical block/biome digests equal the accepted native baseline.

Clumps retains its full ordered eight-stage create / six-stage reopen contract,
six-to-one natural merge, exact histogram and 72 XP, and persistent survivor UUID.
Quilt retains eight exact-once lifecycle stages, native ordering, original source
SHA, native API/registry/Mixin checks and read-before-write SavedData reopen.
Their unchanged independent NBT verifiers are reused directly. Additionally,
persisted forced chunk [0], Clumps platform and unchanged Quilt SavedData bytes
are checked. Inputs, runtime files, parsers and fixture sources are hash-guarded;
the saved-world manifest must be identical before reopen.

## Coexistence decisions

- Clumps arena is y99–103; mixed-pack structures are y199–206. They do not overlap
- Both use chunk0,0. Mixed-pack's `forceload add` is intercepted as a strict
  `forceload query`; the controller cannot silently repair lost persistence
- Keep mixed-pack seed1211, normal world and structures=true for canonical native
  worldgen comparison. Neither unchanged companion depends on its old lane seed
- Chunky runs before freezing, with its existing120-second bound. No orb lifetime
  extension or expiry suppression is applied. Extra XP or lost orb evidence fails
- Port25621 preserves the original Quilt parser's exact loopback assertion and
  must be reserved by runtime coordination. The program checks it is free
- Root `config/neoforge-server.toml` sets LAN advertisement=false before first
  startup. Whitelist, online mode, no query/RCON/status; no players/accounts
- Original missing `clumps.refmap.json` warning remains recorded, never repaired

## Commands

Preparation copies files only, including independent runtime library copies:

```sh
python four-loader/combined-control/test_harness.py -v
python four-loader/combined-control/prepare.py --profile unified-combined-98d-first
```

Launch only after the coordinating parent grants the runtime slot:

```sh
python four-loader/combined-control/run.py --profile unified-combined-98d-first --phase create --runtime-slot-approved
python four-loader/combined-control/run.py --profile unified-combined-98d-first --phase reopen --runtime-slot-approved
```

Separate create/reopen logs and JSON evidence are written to
`logs/unified-combined-98d-first/`. Existing evidence cannot be overwritten.
A failed create cannot proceed to reopen. A timeout/failure stops the one process
and preserves its log and partial world for diagnosis.

Offline tests concatenate already-accepted *separate* lane logs solely to test
parser logic. Such concatenation is never counted as combined runtime evidence.
The test suite starts no JVM, server, client or game process.

This is server integration with a project-owned Quilt probe, not real OP Tab or
client acceptance. It does not establish real-player XP pickup/cancellation,
Mending, broad modpack compatibility, or performance.

## Runtime acceptance, 2026-10-03

The fresh `unified-combined-98d-retry2` profile passed both CREATE/SAVE and REOPEN,
with clean exit0 and all strict runtime/input/NBT guards. The summary is
[`accepted-combined-summary.json`](accepted-combined-summary.json), backed by
`logs/unified-combined-98d-retry2/{create,reopen}.json` and original full logs.
No core or mod archive changed during this work. The runtime slot was released.

Two initial controller failures are retained with their original reports and
controller source snapshots under the respective log directories:

1. `unified-combined-98d-first`: vanilla force-query output displays `Overworld`,
   not its resource key. Corrected the exact display-label assertion; actual
   response passes and wrong coordinate, unloaded state or wrong dimension fails
2. `unified-combined-98d-retry1`: Java writes the normal world type value as
   `minecraft\:normal`. Corrected only that known property's equivalent escaped
   colon spelling; different world types and network values still fail. Replayed
   every post-stop assertion on actual retry1 files before the fresh retry2 run

The final17 offline test methods pass. No original assertion was omitted to get
acceptance. The failed attempts are not retroactively marked passed. The final
accepted profile's independent saved entity check retained one Clumps survivor,
all six logical units and72XP, while the same world retained the Quilt marker,
FD item/block/cooking state and all nine canonical native-equal Chunky targets.
