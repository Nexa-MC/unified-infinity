# Unified ∞ Infinity

Private research source for Minecraft **1.21.1** and **Java21**.

The current implementation integrates a disclosed Connector/FART source fork,
original FFAPI module implementations bundled internally, bounded artifact preflight,
and an independently drawn FML early-loading window. Original upstream licenses and
attribution remain. This is an incremental integration, not a universal-compatibility
release or a complete clean-room loader.

## Source layout
- integrated-loader/: actual loading path, one bounded transformation owner, source patches
- runtime-bundle/: internally managed byte-identical FFAPI implementation
- preload-ui/: actual FML provider, shaders, artwork integration and lifecycle handoff
- compat_admission/: bounded read-only inspection; runtime remains candidate authority
- infinity-api/: optional standalone event API candidate, not required by existing mods
- probes and registry-probe/: unchanged-JAR runtime regression fixtures
- docs/: ownership, safety, performance and verified-scope records

## Build and test
Use JDK21, Python3.11+ and Gradle8.11.1. See each component README for the pinned
artifact preparation and exact commands. No game binary, world save, account data,
credential, toolchain installation or dependency cache is included in this repository.
Minecraft tests require separately acquired official game artifacts and EULA acceptance.
No test script signs in or uploads a publication.

Read THIRD_PARTY_NOTICES.md and the original per-component licenses.
