# Implemented Forge own-probe vertical slice

Verified 2026-10-03 UTC. This is the first **actual Unified runtime pass** for an
unchanged, genuine Forge-only mod. It establishes the narrow surface below, not
complete Forge or Clumps compatibility.

## Exact accepted test tuple

| Input | SHA-256 |
|---|---|
| Core, frozen `source-workspace/artifacts/unified-infinity-four-loader-first-bda743b2.jar` | `bda743b2a0ed5cab72ac78ab4d75cb0a30384d8bba95dd76680639fe8ae697db` |
| Forge-isolation host, `runtime-bundle/build-forge-candidate/libs/unified-infinity-0.1.0-dev.jar` | `9a6239e4fc5f99a3339da200b2fcec2f4c1642323618eee05df8a3b528233955` |
| Unchanged preload provider | `7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99` |
| Original `four-loader/forge-probe/build/unified-forge-probe-0.1.0.jar` | `3a016e8b8340c7c10b6490f15bb7452c1555363035c7373f4d81ccfacfde15fe` |

Minecraft 1.21.1 / NeoForge 21.1.219 / FML 4.0.42 / Neo bus 8.0.5 / Java 21.
The host includes existing FFAPI; this isolated profile contains no QSL and no
third-party Forge mod. The original Forge probe is identical to the independently
passed native Forge 52.1.0 control. Its source and metadata contain Forge API
references only, not a NeoForge fallback.

The earlier accepted core `c8921d6...` and host `3802215...` were not overwritten.
The newer source's dedicated-server side-name normalization and clearer log text
are not part of the frozen bda artifact. The tested own probe uses BOTH dependencies,
so that source-only refinement does not affect the demonstrated semantics.

## Runtime result

Both create/save and reopen/save completed with exit 0. Each process records each
of these stages exactly once:

1. Real Forge-context constructor selected and supplied its per-mod facade;
   premature RegistryObject.get throws Forge's expected NullPointerException
2. Common setup received on the native host lifecycle bus
3. enqueueWork executes once on the actual host deferred queue
4. Deferred Item supplier invoked once, ID/key/presence match the host registry
5. ServerStarted observes the same server and performs world assertions
6. Explicit ServerTickEvent.Post sees the same server/thread and adapted haveTime
7. Ready-to-save, acknowledged save and complete shutdown

Create stores `unified_forge_probe:anchor` ×7 in a vanilla chest at `(0,100,0)` and
SavedData marker `forge_52_1_0_probe_v1`. Reopen asserts them **before any mod write**.
An independent NBT reader confirms the same Item ID/count/slot and SavedData marker
before reopen and after both stops. The second launch uses a verified warm transform
cache. Original input SHA-256 remains unchanged.

This is an Item persistence pass, not custom Block persistence. Setup work uses the
host's `modloading-sync-worker` queue; native Forge's thread name is not imposed on
the existing NeoForge host.

## Evidence and reproduction

- `logs/unified-forge-probe-first/unified-summary.json`
- `logs/unified-forge-probe-first/unified-create.json` and `unified-reopen.json`
- Complete `unified-create.log` and `unified-reopen.log` in that directory
- `four-loader/forge-probe/unified-forge-probe-first-environment-lock.json`,
  SHA-256 `dfabd9c64f756c26320ce22bccde276e15b27d2abe69f40c1361e04d33da3daa`
- Preserved profile/world `run/unified-forge-probe-first/`
- Native comparison `logs/forge-native-probe/native-summary.json`
- Controllers `four-loader/forge-probe/prepare_unified.py` and `run_unified.py`

Controllers require a new profile, exact core/host/provider/probe bytes, all pinned
runtime libraries, existing accepted EULA, loopback-only binding, online-mode=true,
RCON/query off and immutable phase evidence. They do not rebuild the original probe.
The known sandbox DNS failure fetching public Yggdrasil keys does not involve a
player login and did not prevent either local control from completing. The first
profile bound the game socket to loopback but used NeoForge's default LAN-advertise
setting; it is functional ABI/persistence evidence, not proof of LAN-disabled
network behavior. Future controllers explicitly prewrite and guard root
`advertiseDedicatedServerToLan=false` in `config/neoforge-server.toml`.

## Implementation and static checks

Source: `source-workspace/connector-four-loader/components/infinity-forge/`.
Main-layer reader/ASM projection/provider/context/container and game-layer registry
facades use FML's original admission and game module layer. There is one host
registry and global event owner. No second Forge runtime or Mixin engine is loaded.
Source component README details supported symbols and cache/provenance behavior.

The combined fullJar/check passed, including:

- 51 Forge metadata/ASM/cache assertions against the original probe
- 36 constructor/context/lifecycle assertions using the actual pinned host ABI
- 15 registry facade assertions using controlled native DeferredHolder behavior

The Forge capability has a real native host @Mod entrypoint and metadata:
`unified_forge52_adapter` 52.1.0, displayed as “Unified Forge 52 ABI slice”. Original
Forge dependency ranges/order/side/mandatory semantics are retained in the
projection and final native FML validation. Capability version is a bounded ABI
reference, not a claim that every Forge API is implemented.

Still unsupported: custom event posting/cancellation/results, generic listeners,
base TickEvent fields, automatic event subscribers, config/capabilities/network,
client extensions, arbitrary registries, services, AT/coremods/Mixins and missing
Forge Minecraft patches. BLOCK/ITEM registry-key views have unit coverage, but the
MDK IForgeRegistry overload and custom Block persistence await their own genuine
runtime fixtures. Clumps has not been launched on this adapter.
