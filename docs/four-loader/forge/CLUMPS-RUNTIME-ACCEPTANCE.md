# Clumps Forge 19.0.0.1: bounded native/Unified behavior acceptance

Verified 2026-10-03 UTC. The approved original Forge-only Clumps JAR runs unchanged
on Unified's single NeoForge host and passes the same genuine Forge-only companion
fixture as the native Forge 52.1.0 control. This is a real mod behavior/persistence
result, not only discovery, transformation or startup.

## Frozen tested tuple

- Minecraft 1.21.1, Java 21
- Reference native Forge 52.1.0
- Unified NeoForge 21.1.219, FML 4.0.42, native event bus 8.0.5
- Core `source-workspace/artifacts/unified-infinity-four-loader-26b599fc.jar`
  SHA-256 `26b599fc1c033614c427062b209ae8d7a48a3e75bca51e78f1c79ff8299f4cde`
- Matched FFAPI-only host SHA-256
  `9a6239e4fc5f99a3339da200b2fcec2f4c1642323618eee05df8a3b528233955`
- Accepted preload provider SHA-256
  `7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99`
- Original Clumps Forge 19.0.0.1 SHA-256
  `e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19`
- Original companion `four-loader/clumps-probe/build/unified-clumps-probe-0.1.0.jar`
  SHA-256 `b8b6822fc80d53b9a44daa994abeaa53b19ec0838649d9eb7e55f1a766bb6d09`

The matched host was successfully rebuilt/structurally verified against the 26b
core (`logs/four-loader/clumps-matched-host-build.log`). Its bytes match the previous
9a host because the core's declared version and the host's embedded resource
content did not change. The exact core input is independently pinned in the runtime
lock; a shared host byte hash is not evidence that the core input was ignored.

Native and Unified profiles contain the exact same original Clumps and companion
bytes. The Unified isolation profile contains no QSL or additional third-party
Forge mod. Accepted c892/380221 baseline artifacts and the first bda own-Forge pass
remain preserved independently.

## Actual assertions

Both native and Unified create six real nearby experience orbs with values
1,3,7,7,17,37. Normal server entity ticking, not direct merge calls or map setters,
reduces them to one. All transitions preserve exactly
`{1:1, 3:1, 7:2, 17:1, 37:1}`, six logical input units and **72 weighted XP**.
Five consecutive one-entity observations establish the settled result.

This exercises the actual ExperienceOrb Mixins and injected IClumpedOrb interface.
The real entity's `clumpedMap` survives an in-memory vanilla NBT save/load roundtrip.
After acknowledged tick-freeze, save and clean stop, reopening the same world checks
the saved survivor UUID, tag, gravity/platform, exact histogram and XP before any
mod write or repair. Independent offline parsing checks entity-region NBT and
SavedData before reopen and after both stops.

Unified create and reopen both exited 0 with all expected stages exactly once.
Create has eight stages; reopen has six. Both original mods produce verified warm
adapter-cache hits on reopen. The original JAR hashes remain unchanged.

The original config refers to an absent `clumps.refmap.json`. Both native and
Unified emit that warning and pass these actual Mixins/behavior checks. The adapter
preserves the original config and missing-resource state; it generates no refmap.

## Evidence

- `logs/unified-forge-clumps-26b/summary.json`
- `logs/unified-forge-clumps-26b/create.json`, `reopen.json`, complete phase logs
- `four-loader/clumps-control/unified-forge-clumps-26b-lock.json`
- `logs/forge-native-clumps/create.json`, `create-verifier-recheck.json`, `reopen.json`
- `four-loader/clumps-control/forge-native-clumps-lock.json`
- Preserved worlds: `run/unified-forge-clumps-26b/world`, `run/forge-native-clumps/world`
- Fixture contract/pins: `four-loader/clumps-probe/README.md`, `frozen-artifact.json`
- Controller and independent NBT tests: `four-loader/clumps-control/`

Native create's original controller report is deliberately retained with its
initial offline-verifier error: valid zero-byte entity-region placeholders were
rejected as truncated headers. The corrected reader accepts exactly empty
placeholders, continues rejecting nonempty truncation, and passed 11 tests.
Independent create recheck and normal native reopen then passed on the same saved
world; initial evidence was not overwritten. Unified used the corrected reader
and both phase reports pass directly.

Profiles bound only loopback, retained online-mode=true, disabled RCON/query/status,
and explicitly disabled LAN advertisement before first start in the correct loader
config location. No player account or public server was used. Nonessential upstream
update/auth public-key lookups were sandbox-blocked; their diagnostics are retained.

## Implemented surface and limits

`CLUMPS-EVENT-SLICE.md` describes the exact source adaptation. There is one host FML
admission/module layer, one native Mixin engine, native global event bus and native
registry owner. Original same-JAR services remain present. The static bridge returns
Forge's boolean post result from one native dispatch and preserves event identity,
mutable values, cancellation filtering and thrown failures, with 72 dedicated native
bus/PickupXp unit assertions. Those unit assertions do not substitute for gameplay
coverage.

Not tested here: real-player pickup/cancellation, Mending, XP awards to players,
client rendering, multiplayer interoperability, mixed packs, or performance.
The merge/persistence path does not claim all Clumps event/service branches execute.
Remaining general Forge APIs, event annotations/results/phase contracts, capabilities,
network/config/AT/coremods and other Forge-specific Minecraft patches remain bounded
or unsupported. One third-party mod pass is not full Forge compatibility.
