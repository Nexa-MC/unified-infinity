# Unified Infinity

Unified Infinity integrates compatibility loading and a unified mod inventory
for Minecraft 1.21.1. This source snapshot is the **v6 foundation**, accepted in
one bounded Linux client run with the pinned five-mod set.

The source-owned FML/BOOT layer controls admission, SERVICE owns compatibility
discovery and transformation, and GAME owns internal compatibility and product
lifecycle components. The UI distinguishes five user mods from 56 loaded
entries and 46 bundled API entries; it displays one API summary and persistent
source/reason details for skipped external infrastructure.

The accepted run reached the real menu, showed the corrected footer, reopened
the copied test world with its saved Farmer’s Delight stove, saved all
dimensions and exited 0 at 2026-10-03 17:37:37 UTC. Fifteen pinned input paths
remained unchanged. See [acceptance and limits](docs/fusion-v6/README.md).

## Sources and verification

- `source-workspace/connector-four-loader`: Connector, Adapter, FART and
  compatibility sources
- `source-workspace/fml-unified` and `source-workspace/admission-bootstrap`:
  complete modified FML and shared BOOT admission sources
- `runtime-bundle`: product, mod-list, exclusion notices and footer source
- `preload-ui`: responsive preload source and bounded test harness

Run `python3 source-workspace/verify-fusion-source.py` for a read-only source
correspondence check. [Rebuild instructions](docs/fusion-v6/REBUILD.md) retain
exact dependency pins and clearly identify missing external/derived inputs.
No game, runtime/mod binaries or worlds are distributed here. Original source
archives and component licenses remain included.

## Scope limits

This is not universal four-loader compatibility or an independent public mod
authoring API. Large packs, other platforms and the v6 dedicated server were
not reaccepted. Real preload resize/restore completed during loading, but a
transient compositor artifact was observed; no zero-stutter or input-latency
claim is made. Admission metadata checks are not an operating-system sandbox.

The original four-loader acceptance and M5 history remain available in Git.
Earlier documents and artifacts under `docs/four-loader` and `docs/full-source-build`
are historical where their pins differ; v6 evidence under `docs/fusion-v6`
is authoritative for this source snapshot.
