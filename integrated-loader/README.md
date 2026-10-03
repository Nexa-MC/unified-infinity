# Unified ∞ Infinity: integrated loader source fork

This is an incremental source-level R&D fork of the pinned Connector pipeline,
not a wrapper mod and not a replacement for all host/bridge implementations.
The actual `ConnectorLocator`, `JarTransformer`, `JarTransformInstance` and shaded
FART `AsyncHelper` are recompiled with a common policy/progress/resource core. The rest of Connector, NeoForge,
Forgified Fabric Loader, Adapter, Mixin and FFAPI remain the pinned upstream code.

## Build and verify

From the repository root with the existing Java 21 toolchain, installed NeoForge
21.1.219 libraries, and captured official Connector full JAR:

```sh
python3 integrated-loader/build.py
integrated-loader/test.sh
python3 integrated-loader/verify.py
```

Artifact:
`integrated-loader/build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar`

Replace the top-level upstream Connector full JAR with this artifact; never load
both. This subproject does not install it or change a game instance. The verified
API bundle remains a separate native host artifact at this incremental stage.
The independent preload SPI provider consumes the optional snapshot file; this
fork itself contains no UI toolkit or second early-window provider.

`JAVA_HOME` may select another Java 21 installation. The provenance records the
actual compiler version and hashes every compile dependency. Repeatable bytes
require the same inputs and compiler. The build needs no download and does not
invoke the full upstream Gradle build or its SNAPSHOT userdev plugin. It is an
explicit source-class patch build, not evidence that upstream builds from source
in this environment. See [PATCHES.md](PATCHES.md) for limitations and attribution.

## Loading policy

- `-Dunified.infinity.maxWorkers=4`: hard configurable admission ceiling (default 4)
- `-Dunified.infinity.workers=1`: sequential differential/test mode; also accepts
  another positive ceiling, still subject to CPU, heap and maxWorkers limits
- Effective count is the minimum of uncached inputs, available CPUs minus one
  (minimum one), heap budget, configured maxWorkers, and optional workers override
- Heap budget is one worker per 256 MiB after a 512 MiB reserve, minimum one worker
  when work exists; this is a conservative heuristic, not a memory reservation
- At most that many futures are submitted/in flight, with a bounded queue and
  input-order collection. Both actual Renamer builders use direct single-worker
  entry execution on that JAR worker; no nested executor or per-entry futures remain
- Transform initialization, generated adapter write, audit save, global
  bytecode-loader/Mixin cleanup, split-package work and host submission stay on
  the locator thread in the original lifecycle order
- Batch-owned runtime providers and newly created clean ZipFiles/providers close
  after consumers finish; borrowed host filesystems are never closed
- Cancellation drains all workers before global cleanup. A hung uninterruptible
  transformation can still hang until the process is terminated

The default lowers the worst-case worker count from the number of uncached JARs
to a bounded value. It does not by itself establish lower process RSS or faster
startup; measure both against representative real modsets and the same cache
state. Per-entry transform logic is unchanged; this does not newly prove all shared
upstream state thread-safe. A sequential mode remains available for diagnosis.

## Single phase owner and real progress

ConnectorLocator remains the sole orchestration owner:

1. Discover: native-provider context plus existing Fabric root/nested discovery
2. Resolve: unchanged duplicate handling and existing DependencyResolver
3. Transform: cache selection, bounded independent JAR work, audit/safeguard
4. Commit: split-package merge, host pipeline submission, generated/embedded JARs

FML still owns final admission, validation, class loading and game lifecycle. A
candidate selected by Connector is not necessarily a final host-admitted mod.
The stage names are observed operations, not a second resolver/state machine.

Set `-Dunified.infinity.progressFile=/absolute/path/infinity-progress.json` to
publish a small atomic UTF-8 latest-state snapshot. It is replaced only at
stage boundaries and actual cache/transform completion, not on an animation
timer. Routine updates are coalesced to at most 10 Hz, with phase/failure/final
completion always forced immediately. The optional UI can poll at at most 10 Hz:

```json
{"stage":"transform","status":"running","completed":3,"total":7,"elapsedMs":824,"sequence":9}
```

`completed`/`total` are null when unknown. The transform numerator counts actual
cache-ready plus successfully transformed JARs, not host-final admission. The
denominator is known selected candidate count. Completed discover/resolve stages
report actual output counts; commit remains indeterminate. `elapsedMs` and
`sequence` are monotonic within this JVM's progress core. Failures add only the
exception type as `error`, without paths or messages. Snapshot failure never
fails mod loading; unsupported atomic replacement preserves the prior snapshot
and logs one short diagnostic. No unbounded event history is retained.

`commit` with `complete` means this compatibility locator completed its work,
not that Minecraft has started. The preload provider must wait for host lifecycle
handoff before ending its window. Progress has no impact when the property is
unset beyond small bounded in-memory counters.

## Cache and reproducibility

The generated BuildIdentity appends a deterministic digest of all main Java
sources, including the FART patch, to the shared environment cache version. Upstream/fork switches and
source changes invalidate mapped outputs and generated BFU adapters without
deleting user mods. Unchanged
fork sources support warm reuse; worker-count and UI options do not alter the
cache identity because they must not alter successful transform semantics.

The build verifies captured upstream source Git blobs, official binary SHA-256,
unchanged entry payloads, and identical service descriptors. It adds no second
loader/Mixin service. Provenance and the explicit changed-entry inventory live
in `build/provenance.json` and `build/entry-diff.json`; the upstream manifest and
nested dependency bytes are preserved. The emitted ZIP's timestamps, ordering,
permissions and compression are normalized for reproducibility. The source diff
is recorded in `upstream-source.patch`.

Focused core tests cover CPU/heap/cap policy, actual bounded overlap, deterministic
output order, sequential/bounded differential, input-ordered failure attribution,
timeout/interruption cancellation, complete worker drainage, submission-window
bound, real snapshot counts, coalescing, error redaction, owned-resource LIFO closure and
empty input. Direct FART tests also verify owner-thread execution, all three
entry APIs, named exception causes, and interrupt-driven cancellation/drain. Runtime parity and
memory measurements are separate integration checks owned by the main project.
