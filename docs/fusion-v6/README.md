# v6 foundation acceptance

Status: **PASS, scoped client acceptance with measured limits**.

The frozen SERVICE `b138700e`, GAME `78cc8094`, PRODUCT `469118e4` and preload
`ca776b21` ran with installation-policy-assembled FML `6d431507`. The raw source
build of FML is `bd51010d`; those are distinct byte identities. Full hashes are
in `artifact-and-input-pins.json`.

The client reached its menu and new Mods screen. The footer now shows five
user mods without overlapping copyright at 1180×812. Mods shows 56 loaded
entries, 46 bundled API entries, 11 visible rows and one API summary. Persistent
details explain 45 original-source-and-ID exclusions from two external
infrastructure archives. The live toast expired before saved F2 screenshots;
none of the persisted menu captures is claimed to show it.

The copied test world reopened with its saved test stove, all dimensions saved
at 17:37:16 UTC, and the client exited 0 at 17:37:37 UTC. Independent saved-data
verification passed and the original v5 world remained unchanged. World files
and raw saved-data projections are not published.

## Source evidence

- All 655 core/FML/BOOT identity records exactly match the immutable complete
  source ZIP and accepted SERVICE build identity.
- PRODUCT has a frozen 39-file source/build/test snapshot. Nineteen compiled
  classes and eight raw resources matched the pinned product artifact.
- Seven launch/validation helpers have exact frozen hashes.
- Preload's twelve main source/resource files match the immutable earlier
  source checkpoint. Product source remained unchanged after its build, but
  no contemporaneous javac source-hash receipt exists. This is source continuity,
  not a new byte-reproducible provider build proof.

The original freeze receipt predates runtime acceptance and correctly retains
its then-pending status. `acceptance-summary.json` supplies the later result.
Build and test summaries distinguish their actual inputs and dates from the
final combined runtime; no unperformed full build or test suite is claimed.

## Limits

One Linux software-rendered client with a 1280 MiB heap was tested. Native
preload resize/restore completed while real progress continued, but a transient
compositor artifact appeared on immediate restore. Duration and input latency
were not measured. No zero-stutter, cross-platform, large-pack or fresh v6
dedicated-server acceptance is implied. Reverse mixed-container rejection is
covered by focused tests, not by a new mixed-container in-game fixture. Class
origin observations are bounded, not exhaustive tracing of every alias or
lifecycle callback. The earlier offline public-key/sound errors did not produce
a mod-lifecycle fatal or an out-of-memory failure.

The metadata gate is not an OS sandbox and cannot constrain arbitrary admitted
code. Historical environment-inheritance limits remain part of the earlier
evidence; raw environment or credential inventories are not distributed.
