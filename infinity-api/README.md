# Optional Infinity event API candidate

This is a **standalone, Java 21, new-mod API experiment** for Unified ∞ Infinity.
It is not integrated into Minecraft or the compatibility runtime, is not evidence
of unified loader/source architecture, and is not a substitute for that work.
Existing mod JARs do not need to adopt it or be rewritten. No runtime, loader,
probe, transform pipeline, or upstream namespace is changed by this directory.

The candidate is intentionally bounded: typed synchronous notifications, owned
subscriptions, explicit feature requirements, and a small dispatch path. There is
no global bus, dependency injection, annotation scanning, cancellation framework,
networking layer, registry abstraction, or asynchronous executor.

## Try the working example

From the repository root:

```sh
./infinity-api/check.sh
./infinity-api/check.sh --benchmark
```

The script uses `../.toolchains/jdk-21.0.12.1+1` by default, or `JAVA_HOME` when
provided. It compiles the runtime with `--release 21 -Xlint:all -Werror`, runs
22 dependency-free Java tests and a runnable example, and produces
`build/infinity-api-candidate.jar`. This ordinary library JAR is **not a
drop-in loader mod** and has no mod metadata. The candidate has no promised
stable binary API yet.

The complete runnable host simulation is
[`examples/infinity/InfinityTickExample.java`](examples/infinity/InfinityTickExample.java).
The essential shape is:

```java
Capability tickAccess = new Capability("infinity:server_tick");
EventSource<Tick> source = EventSource.onCurrentThread("infinity:after_tick", tickAccess);
Event<Tick> afterTick = source.event();

try (ModScope mod = ModScope.open("example", Set.of(tickAccess))) {
    Subscription subscription = afterTick.listen(mod, tick -> update(tick));
    source.emit(payload);  // host only, on the owner thread
    subscription.close(); // optional early removal
}                         // close every remaining subscription in this session
```

In a future integration, the host would retain `EventSource`, pass the listen-only
`Event` and a host-created `ModScope` to the mod, and close that scope on failed
initialization, stop, or unload. This candidate does not install those hooks.
Its runnable simulation prints:

```text
tick 1
session tick 3
session closed; listeners=0
```

## Contract

- `Event<T>` uses **payload type T**. It accepts `Consumer<? super T>` and returns
  an idempotent, thread-safe `Subscription`. Duplicate registrations are distinct
  subscriptions, even when they use the same listener object.
- `EventSource.onCurrentThread` binds the event to the current Java thread. The
  host must create it on the actual server/game thread, not a loader worker.
  Foreign-thread emission fails before any listener is called and identifies the
  event plus expected/actual threads. There is no automatic thread migration,
  queueing, ownership transfer, or main-thread discovery.
- `listen`, individual `close`, and scope `close` can be called from any thread.
  Scope and event mutation locks serialize registration/removal; the lock order
  is always scope then event. Dispatch acquires neither lock.
- Callback order is registration order at the event's mutation lock. Concurrent
  registration order is scheduling-dependent; each registering thread's own order
  is preserved. Callbacks from different mods are **not parallelized**.
- Dispatch captures one immutable array snapshot. A callback added during an
  emission starts on the next snapshot. A callback removed during an emission
  **can still run in that emission**, even if it has not started when `close`
  returns. The same applies to closing a whole mod scope from another callback
  or another thread. Closure is not an active-callback cancellation barrier.
- Reentrant emission is supported and is depth-first. Each nested emission takes
  a fresh snapshot, so it observes registrations/removals already completed by
  its caller. There is no recursion limit; a listener that emits endlessly can
  overflow the stack.
- After `ModScope.close` returns, all its listeners are absent from future
  snapshots and registration fails with a contextual lifecycle error. Already
  captured snapshots can retain listeners until the dispatch unwinds. Closed
  subscription handles clear their event, scope, and listener references. This
  does not remove references retained by the mod itself, unload classes, or make
  arbitrary listener resources safe to destroy mid-dispatch. Dispose those
  resources on the owner thread **between emissions**, after closure.
- A scope must possess an event's `Capability`, otherwise `CapabilityException`
  names the mod, event, and missing capability. These are host-declared feature
  grants/availability checks, **not a JVM security sandbox**. Trusted host code
  must supply the scopes. A malicious in-process mod is not confined by this API
  and can create its own objects or use ordinary Java access techniques.
- Listener `RuntimeException`s stop the emission immediately and are wrapped in
  `EventDispatchException` with event ID, mod ID, zero-based snapshot position,
  and original cause. Earlier listener changes are not rolled back. A listener
  remains registered after failure until explicitly removed. Nested failures
  preserve their context as a cause chain. `Error`s propagate unchanged and also
  stop dispatch; the API does not attempt to recover from VM failures.
- A slow listener blocks the owner thread and every later listener. There is no
  forced timeout, hidden worker pool, automatic retry, or silent failure skip.
  The host should diagnose slow work using its profiler and choose any future
  isolation/removal policy explicitly. Expensive I/O belongs outside this
  synchronous callback, with game-state changes marshalled by the host.
- Null payloads, listeners, and owners are rejected. Payload allocation,
  immutability, lifetime, and retention rules belong to each event contract.
  Thread-safe registration does not make captured mod state thread-safe.

## Dispatch cost and measured limits

The successful dispatch path performs an owner-thread check, a null check, one
volatile snapshot read, and an indexed callback loop. It uses no reflection,
stream, iterator, task submission, snapshot copy, or newly constructed dispatch
object. Copy-on-write array allocation is paid at registration/removal. Register
and remove are O(N); closing K subscriptions is up to O(K × N), intentionally a
cold-path tradeoff rather than a design for high-frequency listener churn.

[`reports/dispatch-benchmark.txt`](reports/dispatch-benchmark.txt) records the
local smoke measurement. See [`MEASUREMENTS.md`](MEASUREMENTS.md) for the observed
numbers and their limits. It reused one payload and nonallocating listeners,
measured 0/1/8/64 listeners, warmed each case for 1,000,000 emissions, then took
seven rounds of 1,000,000 emissions. HotSpot's per-thread allocation counter
observed **zero allocated bytes in every measured round** on this run. This is
evidence for this successful path under these conditions, not a universal
zero-allocation promise. Payload creation, listeners, exceptions, and mutations
can allocate. No claim about Minecraft TPS/FPS or relative Fabric speed follows.

## Honest comparison with Fabric

The comparison targets upstream Fabric API **0.116.7+1.21.1**, API base
**0.4.42+6573ed8c19**, not a reimplemented lookalike. The Java comparison in
[`examples/fabric/EquivalentFabricTick.java`](examples/fabric/EquivalentFabricTick.java)
is compiled against the existing pinned upstream JAR by `check.sh`; its checksum
and compile-only status are in [`reports/fabric-comparison.txt`](reports/fabric-comparison.txt).
It is not executed here because Fabric event initialization needs Minecraft
classes. The Infinity example above is executed independently.

For ordinary consumption, both APIs are already compact:

```java
// Fabric: T is the callback interface; one-line registration is already simple.
AFTER_TICK.register(tick -> update(tick));

// Infinity candidate: T is the payload; explicit owner and removal handle.
Subscription subscription = afterTick.listen(mod, tick -> update(tick));
```

Fabric's public `Event` exposes registration, invocation, and phase ordering; it
does not expose general unregistration in this version. The candidate adds
scope-based removal and keeps emission on a separate host handle, at the cost
of requiring a scope. Fabric also supplies phases that this candidate omits.
[Upstream Event contract](https://maven.fabricmc.net/docs/fabric-api-0.116.7%2B1.21.1/net/fabricmc/fabric/api/event/Event.html)

For defining a simple custom notification, this candidate avoids authoring a
callback interface and an array-combining invoker. Fabric's invoker factory is
more flexible: it can express multi-argument callbacks, primitive parameters,
return values, and short-circuit decisions. Wrapping those values in an Infinity
payload may allocate. Fabric's optimized factory overload can use an empty
invoker or a sole listener directly, so this experiment is not evidence of a
faster design. [Upstream factory documentation for the same Minecraft version](https://maven.fabricmc.net/docs/fabric-api-0.110.0%2B1.21.1/net/fabricmc/fabric/api/event/EventFactory.html)
and the compile-checked pinned API establish the factory shape.

The proposed ergonomic benefit is specifically fewer custom-notification setup
steps and explicit lifetime management. That is a hypothesis to validate with
mod authors. It does not establish “better than the other APIs” across modding
tasks. No mod-author usability study, upstream dispatch benchmark, loader
integration, existing-JAR compatibility expansion, or game performance run has
been performed for this candidate.

## Verification scope

`reports/tests.txt` records all 22 checks: typed payloads, ordering, duplicate
registrations, individual and scope close, released closed-handle references,
capability/lifecycle/input errors, mutation during dispatch, recursive emission,
failure propagation, foreign-thread rejection, concurrent registration/closure,
and a gated slow listener with concurrent mutation. One test uses reflection to
inspect a closed handle's fields; **the production API does not use reflection**.
The tests are standalone behavior checks, not a proof of all schedules or an
in-game acceptance test. There are no third-party runtime dependencies.
