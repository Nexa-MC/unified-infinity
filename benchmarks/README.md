# Bounded-loading regression corpus

`python3 benchmarks/generate_corpus.py` generates16 project-owned Fabric JARs with
128 independent Java classes each. They contain no game hooks or entrypoints; the
separate unchanged parity probe supplies real Minecraft Mixin/lifecycle behavior.
This is a repeatable transformer workload, not a third-party mod compatibility corpus.

## First source-fork comparison
All three actual server profiles passed creation, actualMinecraft tick injection,
200idle ticks after100warmup, save and orderly exit. All17 transformed JARs have
byte-identical entry payloads across upstream, sequential fork and4-worker fork:
2088 entries compared in each candidate, ignoring ZIP container timestamps.

Single cold/profile observations with JFR enabled:
- Upstream: ready24.155s; observedRSS highwater1244252KiB; peak sampled threads158
- Source fork1worker: ready24.154s; RSS1340768KiB; threads72
- Source fork4workers: ready26.528s; RSS1423148KiB; threads73

This demonstrates bounded-thread governance and behavior parity, not a speed or
memory improvement. World generation, GC timing, JIT and shared-cloud noise affect
whole-process results. The measured memory increase remains an optimization target.
JFR sample weights are estimates. Follow-up profiles must isolate transform-stage
cost and repeat on identical existing worlds before making product claims.
