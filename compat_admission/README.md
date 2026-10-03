# Bounded admission prototype

Requires Python 3.11+; uses only the standard library at runtime.

```sh
python3 -m compat_admission plan original-mod.jar \
  --minecraft 1.21.1 --environment server \
  --fabric-loader-version 0.16.10 --neoforge-version 21.1.219 \
  --fml-version 4 --bundled-inventory inventory.json --output report.json
python3 -m unittest discover -s tests -v
```

The example loader versions are explicit target inputs, not automatically detected
installed versions. `--java-version` similarly describes the target (default 21).
The output path must not already exist. Exit statuses: 0 metadata pass, 1 rejected,
2 invalid invocation or report-output failure.

Inventory schema: `{"schema_version":1,"bundled_apis":[{"id":"original_id",
"version":"original_version","ecosystem":"fabric","environment":"*",
"provides":[]}]}`. Environment and provides are optional. An optional lowercase
SHA-256 is retained as supplied provenance, not verified against an API binary.
No API IDs, versions, or aliases are fabricated or renamed. Inventory data does
not prove those APIs are actually present or correctly implemented.

Supported metadata includes Fabric schema 1, its nested `jars`, NeoForge
`javafml` TOML, side-specific dependencies, and manifest Implementation-Version
substitution. Exact single providers are required; duplicate candidates are
rejected instead of implementing loader-specific candidate selection. Mutual
required-dependency groups are reported; explicit NeoForge ordering cycles fail.

Fabric predicates support numeric versions with up to three components,
prereleases including the empty-prerelease boundary, ignored build metadata,
comparators, whitespace AND, array OR, a trailing wildcard, caret (major bound,
including 0.x), and tilde. Maven predicates support numeric single intervals and
exact brackets. Unsupported syntax fails closed, including unsupported branches
of OR expressions. This is intentionally a conservative subset of real loaders.

NeoForge JarJar candidate selection, ZIP64, ambiguous dual descriptors, other
language loaders, class validation, transformers, mixins, access wideners,
entrypoints, registries, and binary API linkage are not implemented. JarJar is
explicitly rejected with `LOADER_JARJAR_UNSUPPORTED`. Class bytes are never
loaded or executed. Non-selected ZIP payloads are not decompressed or CRC-tested;
selected metadata and nested JAR payloads are bounded and CRC-checked by zipfile.

Passing means only `metadata_pass`; `runtime_compatibility` always remains
`unverified`. A runtime consumer must re-hash original artifacts before use.
The planner is a host-side diagnostic, not an in-game admission enforcement hook.

## Runtime-authoritative preflight

Add `--runtime-authoritative` (Python API: `runtime_authoritative=True`) for the
Unified Infinity runtime handoff. A clean safety scan returns `runtime_deferred`,
never `metadata_pass`. Exit 0 in this mode means only that no blocking preflight
problem was found; it is not a loader or compatibility verdict.

Candidate selection, dependency/version resolution, sidedness, and ordering are
owned by the pinned **NeoForge FML + Sinytra Connector** runtime. The report names
that authority and explicitly leaves candidate selection deferred. It exposes no
selected dependency graph or active-mod count. Logical metadata discovery is
best-effort, not the runtime's authoritative inventory. Runtime pins remain the
responsibility of the externally verified runtime installation.

In this mode declared NeoForge JarJar children are recursively bounded-inspected
(including every ZIP entry name and directory/header checks). JarJar selection is
still unimplemented and appears as a deferred `LOADER_JARJAR_UNSUPPORTED`
advisory. Duplicate candidates, dependency failures, unsupported version syntax,
and other loader-owned decisions are deferred, not promoted to admission
rejections. Unsafe archives, corrupt JSON/TOML, malformed metadata structures,
missing declared children, exhausted budgets, and invalid target configuration
remain blocking. Strict mode retains its original diagnostic behavior.

## Java target policy

Every current or future Minecraft target adapter has a global minimum of Java
21. A newer game's requirements may raise that minimum. Both strict and
runtime-authoritative preflight reject a declared Java version below 21 or a
malformed version; these policy errors are never deferred as loader dependency
decisions. Declared versions `21`, `21.0.12`, and `25` are accepted by this floor.

Reports expose `java_policy.minimum_major` separately from
`java_policy.declared_target_version`. This validates configuration only and does
not infer or verify the JVM actually launched. The supported Minecraft target
remains exactly 1.21.1; the direction and scope of cross-version Minecraft
compatibility remain unresolved by this policy.
