# Direct registry and persisted-item parity

This is a project-owned regression fixture for Minecraft **1.21.1 / Java 21**.
It is not a third-party mod or evidence for universal compatibility.

## Verified result

On 2026-10-03 UTC, **all four actual dedicated-server runs passed**:

| Profile | Create + save | Restart + read |
|---|---|---|
| Fabric Loader 0.19.3 + Fabric API 0.116.7+1.21.1 | PASS | PASS |
| NeoForge 21.1.219 + derived Connector beta.17 + internal FFAPI bundle | PASS | PASS |

Every run positively asserted direct item registration and identity lookup,
the real Fabric `ServerLifecycleEvents.SERVER_STARTED` callback, console NBT,
save-flush acknowledgement, clean exit, and independently decoded region NBT.
The restart runs read the already-persisted stack; they do not place a chest or
recreate the item. Both loaders preserve this exact semantic value:

```json
{"id": "infinity_registry_probe:test_item", "count": 7, "Slot": 0}
```

The container is a chest at `0 64 0`, in chunk `0,0`. The harness waits for an
actual `execute if loaded` acknowledgement because forceloading is asynchronous.
It compares IDs/counts/slots, not random/timestamp-sensitive world-file hashes.

Primary evidence:

- [`../logs/registry-parity-summary.json`](../logs/registry-parity-summary.json)
- [`../logs/registry-inputs.json`](../logs/registry-inputs.json)
- `../logs/registry-{native,unified}-{create,reopen}.{log,json}`
- [`../logs/registry-direct-bytecode.txt`](../logs/registry-direct-bytecode.txt)
- [`../logs/registry-harness-tests.log`](../logs/registry-harness-tests.log)

## Unchanged original JAR

The same original fixture JAR is present in both profile mod directories, and
its SHA-256 is rechecked on every launch:

`5a85a2777180d8b67fe07c7b83b7940dfbd751658fb723b960734f0ac07b6b7a`

The Unified run uses:

- Derived Connector SHA-256: `9a6e896e7742fb920469266808c409c76ac0ab84e0d82f7ac4b5ecbe9ee11eb1`
- Internal runtime bundle SHA-256: `f09e465bf467cc5649fa1c66cbe6600bea030d92d9e8d977d7132e9f377b7696`

Connector's private transformed cache is expected. The fixture supplied by the
user/project is unchanged; the fixture neither performs reflection nor adapts
its behavior by loader. It directly registers a new vanilla `Item` instance
through the Minecraft registry API during
`ModInitializer.onInitialize`. Fabric API is used for the real lifecycle event.

## Mapping and compiler evidence

Compilation targets the native Fabric remapped 1.21.1 server JAR and Fabric's
actual loader/API libraries, with `javac --release 21`. No fake Minecraft API
stubs or reflection are involved. Mojang names below are connected through the
obfuscated namespace to Fabric intermediary:

| Mojang name | Official obfuscated name | Intermediary |
|---|---|---|
| `BuiltInRegistries` | `lt` | `class_7923` |
| `BuiltInRegistries.ITEM` | `lt.g` | `field_41178` |
| `Registry` | `jz` | `class_2378` |
| `Registry.register(Registry, ResourceLocation, Object)` | `jz.a` with that descriptor | `method_10230` |
| `Registry.get(ResourceLocation)` | `jz.a(ResourceLocation)` | `method_10223` |
| `ResourceLocation` | `akr` | `class_2960` |
| `ResourceLocation.fromNamespaceAndPath(String,String)` | `akr.a(String,String)` | `method_60655` |
| `Item` / `Item.Properties` | `cul` / `cul$a` | `class_1792` / `class_1792$class_1793` |

Inputs inspected locally:

- Official Mojang server mappings installed by NeoForge at
  `run/neoforge-compat/libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-mappings.txt`
  SHA-256: `9d0b04bead421c8229aff14b534432bbc927bea642e7c8593d1276b8df8ba53f`
- Fabric intermediary 1.21.1 at
  `run/fabric-native/libraries/net/fabricmc/intermediary/1.21.1/intermediary-1.21.1.jar`
  SHA-256: `6059157dfb4a536ec151697004f74f6004b7d346b289c2f89849e0e585aa36fa`
- Native remapped compiler target at
  `run/fabric-native/.fabric/remappedJars/minecraft-1.21.1-0.19.3/server-intermediary.jar`
  SHA-256: `4ae86fa04430cd19146a4e5b8714fae9314c1498c4e1913f8d678e037d1593a3`

`javap -c` in the evidence shows actual `invokestatic`, `getstatic`, and
`invokeinterface` references. Java uses `class_7922` (the defaulted registry
interface) as the inherited lookup method's bytecode owner; runtime resolution
works in both profiles.

## Reproduce

Run from the repository root. The baseline profiles, pinned runtime builds and
Java 21 toolchain must already exist. No downloads are performed by these scripts.

```sh
sh registry-probe/build.sh
python3 -m unittest discover -s registry-probe -p 'test_*.py' -v
# Only after the Minecraft EULA is explicitly approved for this test:
python3 registry-probe/prepare_profiles.py --accept-eula
python3 registry-probe/run_parity.py --loader native --stage create
python3 registry-probe/run_parity.py --loader native --stage reopen
python3 registry-probe/run_parity.py --loader unified --stage create
python3 registry-probe/run_parity.py --loader unified --stage reopen
python3 registry-probe/summarize.py
```

Profile preparation refuses to overwrite existing directories or saves.
Creation refuses to use an existing world. Restart can be repeated read-only with
respect to the test chest; normal Minecraft save operations still occur.
For a new full creation run, archive the old disposable profiles and evidence
deliberately before preparing new ones.

## Safety and limits

- Dedicated servers bind only `127.0.0.1`: native port 25566, Unified port 25567
- `online-mode=true`, RCON/query disabled; no account tokens or player login
- Immutable baseline libraries are hardlinked; saves/configs/caches are separate
- The blocked Mojang public-key lookup appears as `UnknownHostException` in logs;
  this is an isolated test environment and does not invalidate local registry or
  persisted-item assertions. Authentication/network behavior is untested
- No external unknown mods; no third-party corpus, client/render/input, arbitrary
  registries, complete API surface, performance, or universal-compatibility claim
- Harness unit tests fail on absent registration/lifecycle/readiness/stack
  markers and on incorrect or malformed persisted items
- No changes to the earlier probes, runtime implementation, or shared harness
