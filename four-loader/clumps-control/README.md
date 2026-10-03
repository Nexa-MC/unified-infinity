# Bounded Clumps native / Unified control

These project-owned scripts run the **same original Clumps 19.0.0.1 JAR** and
**same original Forge-only comparison companion** in isolated native Forge and
Unified profiles. They do not rewrite the input JAR or use real accounts,
external players, external servers, or any other third-party mod.

## Fixed inputs and test

- Minecraft 1.21.1, Java 21; native reference Forge 52.1.0
- Original Clumps SHA-256: `e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19`
- Frozen companion SHA-256: `b8b6822fc80d53b9a44daa994abeaa53b19ec0838649d9eb7e55f1a766bb6d09`
- Spawn six real XP entities, values `[1, 3, 7, 7, 17, 37]`, near `(8.5, 100.1, 8.5)`
- Observe ordinary Minecraft/Clumps entity ticking, bounded by 200 post-ticks
- Require naturally merging to one entity, maintaining five stable observations
- Require exact XP histogram `{1:1, 3:1, 7:2, 17:1, 37:1}`, multiplicity six,
  weighted total **72**, throughout observed merge transitions
- Require the actual Clumps-injected interface and real save/read hooks
- Freeze ticks after fixture completion, await freeze acknowledgement, then
  `save-all flush`, await save acknowledgement, and stop cleanly
- Independently decode persisted NBT after stop; reopen the same world without
  fixture respawn and require the same saved survivor UUID and histogram

The original Clumps artifact references an absent `clumps.refmap.json`.
The warning remains visible in logs and reports. It is not repaired, suppressed,
or treated alone as proof of failure or success.

## Independent NBT evidence

`verify_world.py` executes no code from Minecraft, Clumps, or the companion.
It uses a bounded NBT reader to inspect compressed `level.dat`, companion
SavedData, and every nonempty saved overworld entity-region chunk (bounded to
16 region files and 256 chunks). It requires exactly one XP orb; the persisted
probe tag/no-gravity flag; actual int-array UUID equal to SavedData; and the
complete `clumpedMap` compound. It rejects missing/replaced orbs and an equal
XP total with a different histogram.

The map schema is taken from the **exact approved JAR's bytecode**, preserved in
`docs/four-loader/forge/clumps-inspection/com_blamejared_clumps_mixin_MixinExperienceOrb.javap.txt`:

- `addAdditionalSaveData` writes `clumpedMap` as a compound
- XP values are decimal string keys; multiplicities are NBT ints
- `readAdditionalSaveData` uses `getCompound`, `getAllKeys`, `parseInt`, `getInt`
- The native vanilla `ExperienceOrb.tick` scans entities when `tickCount % 20 == 1`

Clumps sets native `Count` from the receiver's earlier map during merge.
The authoritative conservation assertion is the exact histogram's weighted
sum, **not** an invented requirement that vanilla `Count` must be six.

## Run contract

`prepare.py` requires a fresh profile and an exact frozen companion build report.
For native Forge it first verifies the accepted native baseline environment lock,
then makes separate runtime-file copies without copying an accepted world.
Both preparation and every launch check original inputs and all fixture source
and resource hashes. The launcher rechecks exact mod and runtime-JAR inventories,
all requested properties, and loader-correct LAN configuration.

Native profile: `run/forge-native-clumps`, loopback port `25594`.
Unified profiles: `run/unified-forge-clumps-*`, loopback port `25595`.

The native `[server] advertiseDedicatedServerToLan = false` setting exists in
`defaultconfigs` before first launch and is required in the world's serverconfig
after creation and before reopening. Unified requires the NeoForge root setting.
All profiles use online mode, whitelist, no RCON, no query, and no status endpoint.
They reuse the user's prior local-test Minecraft EULA acceptance.

Example, only after the coordinator grants the single runtime slot:

```sh
python four-loader/clumps-control/run.py --profile forge-native-clumps --phase create
python four-loader/clumps-control/run.py --profile forge-native-clumps --phase reopen
```

Logs and JSON reports are preserved under `logs/<profile>/<phase>.*`; rerunning
an existing phase is refused. A failed run's world and logs are retained.

```sh
python -m unittest discover -s four-loader/clumps-control -p 'test*.py' -v
```

## Scope boundaries

A passing control establishes this exact artifact's server startup, required
Mixin behavior, natural merging, histogram/XP conservation, and entity-persistence
slice. It **does not exercise pickup, PlayerXpEvent cancellation, ValueEvent,
mending/RepairEvent, clients/rendering, or arbitrary Forge compatibility**.
Arithmetic/packaging/harness tests alone are not game runtime evidence.

## Native outcome (2026-10-03)

The approved native control passed startup/Mixin acceptance, actual six-to-one
merge (by post-tick 6), XP72 histogram conservation, save, and same-world reopen.
Create and reopen stopped cleanly in 27.9 and 14.4 seconds respectively. The same
survivor UUID persisted across restart; its actual native `Count` remained five,
while its `clumpedMap` represented all six original XP orbs and `Value` was 72.

The initial create verifier rejected two exactly-zero-byte unused region files.
The Minecraft run itself had already passed all eight stages and saved cleanly.
A verifier-only refinement permits exactly empty lazy region placeholders while
still rejecting nonzero truncated headers. An eleventh regression test covers
this case. The initial failed-verification JSON remains unchanged; the separate
`create-verifier-recheck.json` records the successful independent inspection and
links its original report hash. Reopen passed with the corrected verifier.

Canonical native summary: `native-control-summary.json`.
Original evidence: `logs/forge-native-clumps/{create,create-verifier-recheck,reopen}.json`.
No Clumps, companion, Minecraft, or Forge code was modified to achieve this pass.
