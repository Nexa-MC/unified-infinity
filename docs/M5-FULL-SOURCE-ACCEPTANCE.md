# Unified ∞ Infinity: complete-source acceptance

Minecraft 1.21.1 / Java 21 / NeoForge 21.1.219. Private research alpha.

The complete Connector, FART and Adapter core source build now passed fresh runtime acceptance together with the branded managed host and custom early window. The build is no longer the earlier individual-class replacement experiment. NeoForge, FFLoader, FFAPI and Adapter runtime remain credited pinned dependencies.

## Immutable tested profile

- Core: c8921d6a6d3ff3bb47e12913fb867344d1fab7c233e5bce7a9f35a53fef5e65e
- Managed host: 3802215d427501040a432a54e1304e50bbd6758a4610efeea46b0a479641b61e
- Preload provider: 7b549d3725cbf63a529cf543aafa9ce1f9d0d65d3fe3cac93411f429e0955d99

The host pins the actual complete-source core version and SHA rather than pretending it is the upstream release. An initial mismatched-version launch correctly failed admission before a world was created; that evidence is retained.

## Passed

- Complete source compilation, 508 Adapter regression checks and negative control
- Repeated offline build produces identical core JAR and complete source ZIP
- 1,300 class definitions have unique ownership
- Dedicated server with unchanged official Lithium 0.15.4: fresh startup, save, all dimensions, clean exit, restart, persisted scoreboard value read back
- Client with unchanged project parity probe: cold transformation, actual stage events, custom window/context handoff, game reload, branded main menu, cleanup and graceful quit
- Client footer: Unified ∞ Infinity (49 mods); title: Unified ∞ Infinity | Minecraft 1.21.1

## Evidence

- docs/full-source-build/README.md and source-workspace/provenance/
- logs/source-built-lithium-unified-1.json and -2.json with corresponding logs
- preload-ui/reports/client-attempts/05-source-built-client/acceptance.json and source-built-main-menu.png
- logs/source-built-profile-pin-mismatch.json: retained failed attempt

## Limits

This is one real third-party mod, not universal compatibility coverage. The client main-menu test used our probe, not Lithium, and did not open a world. Rendering used llvmpipe software OpenGL. No improvement in total startup time, peak RSS, tick performance or physical GPU behavior is claimed. Hopper behavior and broader real workloads need further differential coverage. Cross-version work remains deferred.
