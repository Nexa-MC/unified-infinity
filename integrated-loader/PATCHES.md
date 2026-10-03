# Unified Infinity loader source integration (R&D)

This local derived artifact recompiles released Connector 2.0.0-beta.17+1.21.1
ConnectorLocator, JarTransformer and JarTransformInstance source classes, plus
its existing shaded FART 1.0.14 AsyncHelper, and adds a shared loading policy,
progress and resource core. It is an incremental source fork, not a full source
rebuild, independent loader implementation, or upstream-endorsed release.

## Changes

- Replace the existing one-thread-per-uncached-JAR executor with one bounded CPU,
  heap and configured-cap budget. No extra resolver, lifecycle executor,
  class-definition path or Mixin engine is added.
- Set both actual Renamer builders to threads=1; patched FART executes this mode
  directly on the calling JAR worker, without an inner executor or per-entry
  futures. Other FART thread-count modes retain upstream behavior. Entry order,
  null filtering and named exception cause structure are preserved; interruption
  is checked before each direct entry and never consumed.
- Submit at most the selected worker count of JAR tasks and return results in
  original candidate order, including mixed cache hits/misses. Exceptions are
  attributed in input order. Later failure may wait for earlier inputs to finish.
- Cancel outstanding work on failure, timeout or interrupt; wait until all workers
  terminate before global bytecode-loader and Mixin-cache cleanup. Uninterruptible
  third-party code still requires terminating the process; timeout triggers
  cancellation but is not a hard termination guarantee.
- Surface interruption as failure rather than an empty successful transform list.
- Extend the shared environment cache version with a deterministic main-source
  digest, invalidating mapped JAR and generated BFU adapter caches when switching
  upstream/fork or changing sources. Log the modified fork/source identity while
  retaining upstream component IDs and ABI/version ranges.
- Close the newly created runtime ClassProvider after worker drain, generated
  adapter/audit completion and global callback removal. A scoped environment
  closes only newly created clean ZipFiles/development providers, with unchanged
  upstream path selection, LIFO closure and suppressed close failures.
- Keep ConnectorLocator as sole discover/resolve/transform/commit owner; extract
  existing root/nested discovery into a named stage seam. Publish actual optional
  UI snapshots, coalescing routine completion writes to at most 10 Hz and forcing
  phase boundaries, errors and final completion. These phases describe candidate
  preparation and host submission, not host-final admission or game readiness.
- Retain existing dependency resolution, Mixin safeguard, split-package work,
  generated adapter commit, upstream services, native lifecycle and finally
  embedded JAR discovery. No service descriptor is changed or added.
- Use the published reloc.net.minecraftforge.* namespaces in compiled sources,
  equivalent to original Shadow relocation. AsyncHelper is the only changed FART
  class; no additional copy or new package relocation is introduced.

## Reproduction and provenance

Run `python3 integrated-loader/build.py` using the repository Java 21 toolchain
and installed NeoForge 21.1.219 libraries. The script verifies the official full
JAR SHA-256, captured Connector source Git blobs and pinned FART source archive;
compiles all modified/new Java sources with annotation processing disabled; and
deterministically replaces only owned classes plus adds notices/provenance/source.
All other entry payloads, including service descriptors, manifest and nested
runtime dependencies, are verified byte-identical. ZIP container ordering,
timestamps, permissions and compression are normalized. The manifest identifies
the upstream ABI; filename, startup log and provenance clearly identify the fork.

A generated BuildIdentity puts the SHA-256 of all main Java sources in the shared
cache version. Both mapped-input and generated-adapter caches receive it.

Official upstream full-JAR SHA-256:
`270b2d385be50932419b7d57d4f4bf7328d70e08d0dd9d88adefdb3c5d08a986`

Captured released Connector source Git tree (not commit):
`8b27f1ad042aae8037bcc522b321c03fcce1a12a`

Published FART 1.0.14 source archive SHA-256:
`1cf3acb13c14360805a84040266cb12ad467bdd98238b3ba8ec1b115be79782a`

## Licenses and source

Connector MIT copyright/license are preserved in LICENSE and in the derived JAR.
FART's original LGPL-2.1-only header is retained with a dated modification notice.
Its complete LGPL text, exact published source archive and modified AsyncHelper
source are inside META-INF/unified-infinity. The repository contains every changed
source, the source diff and reproduction scripts. Unchanged dependencies retain
their original licenses; this is not a complete redistribution license audit.
Minecraft and host game binaries are not included.
