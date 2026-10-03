# M2 verified baseline — Unified ∞ Infinity

This is a feasibility/regression baseline, NOT the final source-integrated architecture.

## Actual observed passes
- NeoForge1.21.1 empty server creates, saves and reopens a world; exits0
- Internally bundled FFAPI host compiles and preserves43 nested upstream archives
- Two clean builds produce the same host SHA256
- The compatibility mods directory contains host + officialConnector + our Fabric probe;
  no standalone FFAPI file is needed
- Exact same project-owned Fabric probe0.1 JAR passes native Fabric and compatibility:
  entrypoint, actualEventFactory dispatch, Mixin7→42, worldcreation/save/reopen
- Three alternating sequential reopen runs pass for each profile
- Probe0.2 additionally injects MinecraftServer.tickServer in intermediary namespace;
  both runtime profiles pass and record200 idle ticks after100warmup ticks
- 73 standalone metadata/security admission tests pass at this checkpoint

These are project-owned probes, not an existing third-party corpus. Rendering,
client networking, gameplay registries, large modpacks, arbitrary Mixin plugins and
cross-version support are not established by these runs.

## Recorded performance observations
Three reopen runs using probe0.1, sameJava21/-Xms512M/-Xmx2G/seed1211/settings:
- NativeFabric ready median12.105s; sampled peakRSS median872564KiB
- Compatibility baseline ready median16.775s; sampled peakRSS median888788KiB
- Current startup median is about38.6% slower; no performance acceptance claim

Probe0.2 single idle-server tick sample:
- NativeFabric: p95=3.159ms,p99=10.062ms
- Compatibility: p95=2.400ms,p99=7.594ms
This single unloaded sample does NOT show a speedup. Shared cloud noise, game
state and sample size prevent a product-performance conclusion. Raw logs retained.

## Diagnosed and corrected fixture error
First probe placed its entrypoint and target inside its own Mixin package. Both
runtimes rejected that invalid package layout. Moving Mixins into their own package
fixed both. This was our fixture bug, not evidence of loader or third-party mod error.

## Source unification next
The user requires coherent source-level ownership, not a stack of wrappers.
Current packaging is retained only as a known-working control. Work in progress:
- audit real discovery/resolution/mapping/Mixin/lifecycle/event ownership
- remove static-preflight false authority over the runtime candidate solver
- refactor the actual Connector source phase path and its per-JAR thread fan-out
- central bounded scheduling, cancellation, progress events and memory budgets
- connect own client preloading UI to actual stage events

Optional infinity-api/ is an isolated tested design candidate, not runtime integration
or proof that a facade unifies the loader.
