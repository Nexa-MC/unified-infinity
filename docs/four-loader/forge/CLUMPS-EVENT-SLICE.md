# Clumps-focused event slice: implemented

The first actual own-Forge Item create/reopen acceptance stays frozen at bda743b2 /
9a6239e4; see IMPLEMENTED-SLICE.md. The subsequent source patch passed actual native/Unified Clumps merge and persistence
controls; see CLUMPS-RUNTIME-ACCEPTANCE.md for the exact bounded runtime claim.
This file describes the API/resource adaptation and unit coverage.

## Active native host-bus semantics

The three exact Clumps `IEventBus.post(Forge Event):boolean` sites are rewritten to
`ForgeEventBridge.post(native IEventBus, native Event):boolean`. Method-handle form
is rewritten with the receiver as the first static argument. The bridge posts the
same object to the supplied native owner exactly once, then reports its final
ICancellableEvent state (false for a plain event). Native priority ordering,
receive-cancelled filtering, mutation and thrown listener failures remain owned by
the native bus. No new bus, dispatcher, listener collection or event copy exists.

Clumps ValueEvent/RepairEvent become subclasses of native Event, preserving their
fields and mutable payload. Only plain constructor-only Forge Event subclassing is
admitted. The exact native PickupXp class preserves the existing player/orb and
cancellation contract. Forge cancellation annotations, result/phase APIs, custom
cancelability, other Forge event subclasses and direct Forge Event construction
remain rejected. The bridge applies to the running host-owned bus; Forge bus
shutdown/start semantics are not emulated or exposed.

## Resources

Same-JAR service interfaces/providers with valid public zeroarg implementations
are statically validated. Descriptor bytes remain identical. FML's automatic-module
builder discovers providers from them; it must not receive explicit TOML `services`
uses, because Java rejects uses declarations on automatic modules. The test checks
the actual FML-generated module descriptor.

The original `MixinConfigs` manifest entry is projected into the native FML Mixin
metadata. Config and annotation bytes remain direct Mojmap; no intermediary/SRG
remap or second Mixin engine is introduced. Config plugins, missing classes and
present refmaps requiring an unimplemented translation contract are rejected.
Clumps' originally absent `clumps.refmap.json` remains absent and is recorded in the
audit. Required native Mixin application and real orb merge/persistence subsequently passed
the coordinated native/Unified controls; real-player pickup/Mending remain untested.

## Static verification

- 63 native-bus assertions: identity, mutable values, priorities, supplied owner,
  exactly one post, cancellation filtering/final state and identical exception
  propagation
- 9 actual native PickupXp assertions, with null player/orb, no game bootstrap
- 38 exact-original-Clumps assertions: SHA unchanged; all 15 classes audited and
  transformed; all three post sites rewritten; genuine ValueEvent/RepairEvent
  objects are mutable native events; service/Mixin/manifest/source-TOML bytes
  unchanged; no refmap invented; actual FML mod/module descriptor valid
- 53 previous adapter metadata/cache/ASM assertions and 51 context/registry
  facade assertions remain passing

Commands from connector-four-loader: components/infinity-forge/run-event-tests.sh,
run-clumps-tests.sh, run-adapter-tests.sh and run-facade-tests.sh (with that same
component prefix). No game process is launched by these scripts.
