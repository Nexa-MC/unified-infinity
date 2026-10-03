# Unified ∞ Infinity performance and API requirements

The product name is Unified ∞ Infinity. Performance and a more usable optional
API for new mods are explicit goals; unmodified existing JAR support remains.
No numerical product SLA has been approved yet.

## Measurement contract
Compare native Fabric versus compatibility with the same immutable probe/mod hashes,
same Minecraft version, Java 21, -Xms512M -Xmx2G, seed1211, view/simulation distance2,
loopback-only networking, and equivalent world state. Native NeoForge empty host is
an infrastructure control, not a substitute for native Fabric parity.

Initial harness records ready-marker duration, total save/stop duration and sampled
peak resident memory. RSS is sampled opportunistically with a maximum half-second
wait, not a perfect OS high-water measurement. Label fresh-world versus reopen,
transform/cache cold versus warm separately. Run repetitions before claiming trends.
No game tick p95/p99, allocation rate, client FPS or physical GPU measurement has yet
been implemented or demonstrated. These must remain explicitly NOT MEASURED.

## Architecture budgets (proposals, not acceptance claims)
- Translation, remapping and structural linking should primarily happen at load time
- Do not use reflective calls in each tick/event as the default compatibility bridge
- Cache transforms by immutable input hash + mappings + adapter/host version
- Measure cache invalidation and startup hit/miss independently
- Add isolated event dispatch throughput/allocation microbenchmarks before API scaling
- Record heap/RSS and tick latency with representative native and cross-loader mod sets

## New API vertical slice
The first optional API should cover one typed event/lifecycle path with stable error
messages and capability discovery. Compare actual lines/setup complexity to equivalent
Fabric and NeoForge examples. 'More usable' is an objective to test with examples, not
something guaranteed by introducing a facade. Existing ecosystem IDs, APIs, entrypoints
and Mixin behavior must remain compatible without requiring adoption of the new API.

## Observed native infrastructure controls
NeoForge empty first-world start/save/stop: 24.823s total, exit0. Reopen/save/stop:15.686s total, exit0. These early runs did not capture ready-only time or RSS and are not cross-loader performance comparisons. See logs for exact run evidence.
