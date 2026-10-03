# Threat model

## Inputs and trust
Mod archives and metadata are untrusted. Archive inspection must never execute
classes, mixin plugins, static initializers or nested installers. Official dependencies
are downloaded from their first-party release/Maven sources and hash-locked.

## Admission boundaries
Cap compressed archive size, archive members, per-entry and aggregate expanded
bytes, nested depth and nested count. Reject traversal, absolute paths, duplicate
names, encrypted or symbolic-link entries, and ambiguous metadata. Do not extract
untrusted paths. Enforce budgets over the entire nested archive graph, not per jar
alone. JSON/TOML parsing and unsupported version predicates fail clearly. Preserve
original bytes and compute SHA-256; avoid copying arbitrary metadata into shell
commands. Treat metadata descriptions as data, never instructions.

## Execution boundaries
A JVM is not a security sandbox. Mod execution is arbitrary code. Only authorized
artifacts in isolated disposable cloud instances, without user tokens or account
credentials, may run. Keep network scope and resources constrained. No automatic
EULA acceptance, logins, security setting changes, public hosting or publishing.
Unknown-source executable mods require separate applicable approval.

## Provenance and licensing
Do not redistribute Minecraft binaries in source checkpoints. Keep upstream names,
licenses and notices intact. Reusing Connector, FFAPI, Fabric Loader or Mixin is not
original implementation. Record source URL, exact version/hash, retrieval time,
license and transformations for each artifact. A SHA is integrity evidence, not
proof of safety. Source code, logs and checksums are checkpointed durably.

## Reproduction
Logs may contain paths or environment data; never persist secrets. Runtime crash
reports must preserve diagnostic context while removing credentials if any appear.
Do not permit an untrusted mod to request broader permissions or change tests.
