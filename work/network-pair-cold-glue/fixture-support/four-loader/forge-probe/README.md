# Genuine Forge 1.21.1 native ABI probe

This is original project-owned test code, built as a **Forge-only** mod using the
official Forge **52.1.0** production API. Its original JAR is the input to both
the native Forge control and the later Unified compatibility test. Do not edit
or rebuild one copy to make the compatibility side pass.

## Deliberately bounded contract

- `META-INF/mods.toml`, Forge `@Mod`, and one public
  `FMLJavaModLoadingContext` constructor
- Exactly one construction, item supplier invocation, common setup callback and
  `enqueueWork(Runnable)` execution
- `DeferredRegister.create(Registries.ITEM, MOD_ID)`, returning Forge
  `RegistryObject<Item>`; `get`, `getId`, `getKey`, and `isPresent` checks, including
  Forge's `NullPointerException` for premature `get`
- Native global bus callbacks for `ServerStartedEvent` and explicit
  `TickEvent.ServerTickEvent.Post`; real server identity, server thread and
  `haveTime()` invocation
- Actual built-in item registry identity, seven custom items stored in a vanilla
  chest at `(0,100,0)`, and original SavedData marker `forge_52_1_0_probe_v1`
- A second launch reads and asserts the saved chest item and SavedData marker
  **before any probe write**; missing or mismatched state fails rather than heals

This first fixture registers one Item, as requested. It does not register a
custom block and does not cover IForgeRegistry/ForgeRegistries, automatic event
subscribers, cancellation, custom events, capabilities, config, networking,
Mixins, client rendering, or any third-party mod.

## Build

From the repository root:

```
python3 four-loader/forge-probe/build.py
```

The build uses existing JDK 21 `javac` with explicit official
`forge-1.21.1-52.1.0-universal.jar`, `fmlcore`, `javafmllanguage`, and
`eventbus-6.2.27` binaries, whose SHA-256 values must match the captured official
source lock. The clean Mojmap Minecraft jar is a **compile type input only**.
Only compiled original probe classes and its own descriptor enter the mod jar.

Forge 52.1.0's native production namespace is Mojmap, and the exact official MDK
sets `reobf=false`. There is no ForgeGradle resolution, remapping, SRG dependency,
NeoForge shim, or dual-loader metadata in this build. Native execution must
still validate binary linkage and Forge behavior; compilation alone is not a
compatibility pass. `build/build-report.json` locks every actual compile input;
`build/probe-javap.txt` records the compiled constant pool and descriptors.

The build rejects NeoForge or Fabric source/class references and descriptor
contamination. Dependency input selection is explicit and never opens the
quarantined candidate directory indiscriminately.

## Isolated official control

`prepare_native.py` installs the unmodified official Forge 52.1.0 distribution
into `run/forge-native-probe`, reusing only matching-hash official cached
libraries. It never launches Minecraft. Installer logs and phase results live
under `logs/forge-native-probe`.

After successful preparation, the native environment lock fixes the installer,
JDK, runtime jars, launch args, probe and loopback settings. Parent-coordinated
game runs use:

```
python3 four-loader/forge-probe/run_native.py --phase create
python3 four-loader/forge-probe/run_native.py --phase reopen
```

For a fresh profile, run `pin_native.py` after the installer and before launching.
It also disables Forge's optional dedicated-server LAN advertisements. The
initial create control revealed that this upstream default was enabled; its
attempt was blocked by the sandbox. The default is now explicitly disabled and
was not attempted during the reopen control. Both runs listened exclusively on
`127.0.0.1:25591`. The original lock and corrected launch/configuration lock are
retained separately rather than obscuring the change.

Only the own pinned probe is allowed in `mods`. The server binds to
`127.0.0.1`, keeps online authentication enabled, disables RCON/query and uses
no player accounts. Each phase waits for the explicit fifth Post tick, requests
`save-all flush`, then sends `stop`. Existing reports/worlds are preserved;
create refuses an existing world. The harness requires exactly one of all
seven phase markers, save acknowledgement, orderly shutdown, and actual world
files. A maximum runtime is only a failure bound, never a pass condition.

## Verified result (2026-10-03 UTC)

Native Forge create and reopen both passed, exit code 0. The frozen probe is:

```
3a016e8b8340c7c10b6490f15bb7452c1555363035c7373f4d81ccfacfde15fe
```

All seven required stage markers occurred exactly once in each process.
Independent bounded region/NBT reads confirmed the custom item and SavedData
before reopen and after shutdown. SavedData bytes were identical across reopen.
`logs/forge-native-probe/native-summary.json` is the aggregate evidence;
`expected-abi.json` inventories the exact compiled Forge member references.
Rebuilding reproduced the same JAR hash.

The native control logged a missing pack-metadata warning for this code-only
fixture and an unavailable Mojang public-key fetch; neither is treated as a
network/player test. Online authentication was kept enabled and no player
connected. This verifies the genuine native probe, **not yet its Unified
adapter execution**.

## Provenance and licenses

Original fixture source is MIT licensed; see `LICENSE`. The mod jar contains no
upstream code. Forge artifacts remain unmodified, with their upstream license
notices preserved inside them (Forge sources state LGPL-2.1-only). Minecraft
is proprietary; the native local control uses the existing user approval for
local test-server EULA acceptance. See the official artifact source lock at
`docs/four-loader/forge/source-lock.json` and the exact inspected sources in
that directory. No third-party-mod execution is part of this own-probe control.
