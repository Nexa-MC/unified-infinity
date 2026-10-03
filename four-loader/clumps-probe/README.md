# Forge-only Clumps behavior probe

Original MIT-licensed companion fixture, compiled once against official Forge
52.1.0, clean Mojmap Minecraft 1.21.1 types, and compile-only Clumps 19.0.0.1.
The JAR contains no Minecraft, Forge or Clumps implementation classes. Run the
same unmodified JAR and pinned upstream Clumps JAR on native Forge and Unified.

**Building/testing this directory never launches Minecraft.** Compilation and
the pure arithmetic unit tests do not establish actual runtime behavior. See
the separately owned `four-loader/clumps-control/` for phase controllers and
native/Unified runtime evidence. No publication is authorized.

## Build and pure tests

From the project root:

```sh
python3 four-loader/clumps-probe/build.py
python3 four-loader/clumps-probe/test_probe.py
```

Outputs: `build/unified-clumps-probe-0.1.0.jar`, `build/build-report.json`
(all source/resource/input hashes), and `build/probe-javap.txt` (real emitted
Forge ABI evidence). `frozen-artifact.json` pins the final built artifact.
The Clumps input is fixed to SHA-256
`e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19`.

## Actual behavior under test

The only Forge APIs used are `@Mod`, `MinecraftForge.EVENT_BUS`, its generic
`addListener(Consumer)` overload, `ServerStartedEvent.getServer()`, and explicit
`TickEvent.ServerTickEvent.Post.getServer()/haveTime()`. No automatic
subscribers, fake players, additional Forge mappings, mixins of our own, direct
merge calls, manual orb ticking, or Clumps map setters are used.

In a new isolated test world, phase `create` forces chunk `(0,0)`, waits for
entity-ticking and entity-loaded readiness, lays a 7-by-7 stone platform at
y=99, clears y=100..103 above it, and spawns six real `ExperienceOrb`s close
together at x=8.35..8.60, y=100.1, z=8.5. Values are **1,3,7,7,17,37**. Each orb
has no gravity, zero initial motion, and tag `unified_clumps_probe`. Tests
require no players. Clumps' actual getter lazily initializes its own map;
the fixture observes it and never writes the map.

Normal server entity ticks must reduce six entities to exactly one. On every
observed transition, each injected `IClumpedOrb.clumps$getClumpedMap()` must
aggregate to **{1:1,3:1,7:2,17:1,37:1}**, six original orb units, and weighted
sum **72 XP**. Five consecutive one-entity observations and a positive real
entity tick count are required before acceptance. Missing mixin injection,
vanilla-only merging, lost entities, changed denomination counts, duplicated
XP, and no entity ticking cannot pass. A 200-post-tick bound fails stalled
behavior (about 10 seconds at 20 TPS after server startup; the external
controller needs its own wall-clock timeout).

The survivor is serialized through real `saveWithoutId`, and its actual
`clumpedMap` compound must match exactly. A new comparison orb is loaded from
that NBT and checked through the injected interface. This comparison object
is never added to the world. This is **in-memory NBT round-trip evidence**, not
by itself world-reopen evidence.

After successful create assertions, SavedData `unified_clumps_probe` stores
`marker="clumps_forge_19_0_0_1_probe_v1"` and `survivor=<UUID>` (vanilla UUID
int-array encoding). The persisted entity retains its tag and NoGravity.
Actual phase `reopen` reads these existing records, waits for the saved UUID
to load, and verifies one surviving orb, same identity/tag/gravity, platform,
full histogram, 72 XP and another NBT round-trip. It never repairs the platform,
forces a missing saved chunk, respawns the entity or writes missing marker data.

## Controller contract

Start with `-Dunified.clumpsProbe.phase=create` on a new world, then
`-Dunified.clumpsProbe.phase=reopen` on that same saved world. The same JAR is
used for both phases and both loaders. All diagnostic lines use
`UNIFIED_CLUMPS_PROBE PASS stage=<stage> ...`, or
`UNIFIED_CLUMPS_PROBE FAIL assertion=<assertion>`.

Required exactly-once stage sets:

- create: `constructor`, `server_started`, `post_tick`, `seeded`, `merge`,
  `nbt_roundtrip`, `world_create`, `ready_to_save`
- reopen: `constructor`, `server_started`, `post_tick`, `world_reopen`,
  `nbt_roundtrip`, `ready_to_save`

Wait for both Minecraft server readiness and the correct `ready_to_save`.
Then issue `tick freeze`, `save-all flush`, await a successful save
acknowledgement, and `stop`; require clean exit, complete saves, no FAIL marker
or runtime exception, exact marker counts, and unchanged input hashes.
The fixture itself does not execute console commands or stop the server.
Keep native and Unified runs serialized under the parent's runtime slot.
Never use startup alone as a successful result.

Independent offline validation can examine:

- `world/data/unified_clumps_probe.dat`: marker string and survivor UUID
- `world/entities/r.0.0.mca`, chunk `(0,0)`: exactly one arena experience orb,
  matching UUID, tag, NoGravity and exact `clumpedMap`
- `world/region/r.0.0.mca`, chunk `(0,0)`: stone platform
- `world/data/chunks.dat`: forced chunk `(0,0)`

Minecraft native `value` and `count` fields are not used as a substitute for
the mod's weighted histogram. In inspected Clumps bytecode `count` is assigned
from the receiver's old map before map combination, so assuming it equals the
six logical input units would be an incorrect test. The histogram and its
weighted sum are the authoritative assertions here.

## Sources and limits

The exact inspected upstream bytecode lives in
`docs/four-loader/forge/clumps-inspection/`:

- `com_blamejared_clumps_helper_IClumpedOrb.javap.txt`: injected interface ABI
- `com_blamejared_clumps_mixin_MixinExperienceOrb.javap.txt`: `canMerge`,
  `merge`, `clumps$getClumpedMap`, save and read injections
- `META-INF_mods.toml`: upstream mod identity and dependencies

The clean Minecraft 1.21.1 `ExperienceOrb` bytecode schedules its entity scan
when `tickCount % 20 == 1`; this fixture relies on that normal tick path.

Not tested: real-player pickup, pickup cancellation gameplay, mending, player
XP awards, client rendering, concurrent players, performance, or other mods.
Pickup-cancellation bridge unit tests belong to the adapter's separate tests
and are not gameplay evidence from this fixture.
