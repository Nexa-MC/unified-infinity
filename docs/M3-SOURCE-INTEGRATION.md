# M3 — actual source-pipeline integration

Target remainsMinecraft1.21.1/Java21. This is an incremental source-class fork,
not a complete upstream source rebuild or final universal loader architecture.

## Actual runtime changes
- Recompiled the actual Connector discovery/transformation path, with the existing
  provider identity; no second resolver, game classloader or Mixin engine
- Single bounded outer transformation owner, limited by CPU/heap/configured budget
- Patched the real shaded FART single-thread path to execute directly on that owner,
  eliminating nested worker pools/queues rather than merely wrapping them
- Deterministic candidate ordering, failure attribution, cooperative cancellation,
  worker drain before global cleanup, explicit failure instead of empty success
- Resource scope closes batch-owned runtime providers/clean ZIP handles
- Source fingerprint invalidates both transformed and generated-adapter caches
- Real discover/resolve/transform/commit observations, atomic/coalesced10Hz output
- Modified fork/source identity is logged; original upstream attribution retained

Frozen core artifact SHA256:
9a6e896e7742fb920469266808c409c76ac0ab84e0d82f7ac4b5ecbe9ee11eb1

## Verified behavior
- Ten loading-core tests plus real FART ownership/failure/cancellation tests pass
- Source-derived artifact rebuild is byte reproducible
- Both1-worker and4-worker profiles pass actualMinecraft startup, Mixin tick hook,
  200idle ticks after100warmup, save and orderly exit
- Against original upstream: all17 transformed archives,2088 entry payloads are
  identical in both final profiles (ZIP container timestamps ignored)
- Commit-stage open file handles fell187→169 versus the earlier source fork on
  the same synthetic corpus; this matches deterministic owned-resource cleanup
- The static scanner now defers candidate decisions to runtime instead of falsely
  rejecting the working JarJar deployment;99 tests pass, includingJava21 floor

Whole-process RSS/timing samples are recorded, but do not establish a repeatable
speedup or memory reduction. Cold world generation and shared-cloud activity are
confounders. Use logs/ and benchmarks/ for exact scope and raw measurements.

## Own preload UI
Own shader/scene/layout/animation/icon/window handling implements the real FML SPI.
Native cloud OpenGL4.5 llvmpipe smoke verified same-window/context handoff and cleanup.
Reduced-motion frames four seconds apart remain byte-identical without new events.
29 headless assertions pass in the QA-capable provider revision. The later NeoForge
reload/fade bridge is intentionally reused; no graphics-driver-from-scratch claim.
FullMinecraft client startup and real producer-to-window capture are in progress,
not yet covered by this checkpoint. The preview is an actual native framebuffer.

## Remaining consolidation
FML still owns host-final admission/classpath/registries. FFAPI implementations and
existing Fabric entrypoint/metadata solver remain credited upstream implementations.
Do not replay FFAPI native constructors through an added central dispatcher.
The old nested loader suppression is deliberate arbitration and remains until a
source-built dependency cleanup is tested. Optional infinity-api/ is a standalone
candidate, not a substitute for preserving legacy API/ABI.

No third-party mod corpus has been executed and no public release is authorized.
