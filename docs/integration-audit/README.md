# Unified ∞ Infinity: single-ownership integration audit

Audit date: 2026-10-03. Target: Minecraft 1.21.1, NeoForge 21.1.219,
FML 4.0.42, Connector 2.0.0-beta.17, FFAPI 0.116.7+2.2.1.

## Decision in one paragraph

The existing bundle is a useful **feasibility baseline**, not a completed integrated
runtime. The next real integration must replace the **actual early loading path**,
not add another loader or a facade around the late `@Mod` constructor. Retain FML as
the host classpath/registry authority, retain the pinned upstream candidate solvers,
and refactor Connector's existing discovery → selection → transformation → commit
path into one explicit, testable coordinator. Remove the Python preflight's competing
claim to decide candidate admission. Preserve FFAPI's existing per-module API/event
implementations; never dispatch their initialization again from a new universal bus.

中文结论：目前证明的是“这些实现可以一起正确跑通”，还不是“已经完成统一内核”。
下一步必须改实际启动链，把发现、候选选择、变换、提交及错误处理收归一条可验证的管线；
保留有明确边界的上游实现，删除重复决策权，而不是再增加一个总控外壳或重新包装几个 JAR。

## What was inspected

- The project's actual `compat_admission/core.py`, CLI, bundle Java constructor,
  bundle metadata/build, locked binaries, and the existing successful server log
- Connector release tag, verified to commit
  `8b27f1ad042aae8037bcc522b321c03fcce1a12a`
- FFAPI baseline release tag, verified to commit
  `4d9f331eddc1354c8eb930cdb75fc6a27e4c7b1b`; the older research checkout's
  `ffapi-tree.json` is a different/latest source revision and was **not** used as
  evidence for baseline event implementations
- Exact Maven source JAR for Forgified Fabric Loader
  `2.5.70+0.19.3+1.21.1`, which Connector shades
- Exact Maven source JAR for FML `4.0.42`
- Actual FFAPI lifecycle module's generated `@Mod` constructor using JDK 21 `javap`

Downloaded source URLs, SHA-256 values, and unsuccessful lookup attempts are in
[`source-manifest.json`](source-manifest.json). Sources are research copies, not
new original project code. The runtime's official artifacts remain untouched by
this audit. The Maven source archive is the loader evidence because a guessed tag
with the Maven version did not exist; no current-branch source was substituted.

## Deliverables

1. [Actual ownership and call graph](OWNERSHIP_GRAPH.md)
2. [Concrete source-integration plan and acceptance tests](NEXT_REFACTOR.md)
3. [Machine-readable ownership contract](ownership-contract.json)
4. [Current preflight failure reproduced against the project's own host](current-preflight-host.json)
5. [Service-provider and dormant-loader binary evidence](binary-provider-evidence.json)
6. [Audit provenance and limitations](PROVENANCE.md)
7. [Memory/resource ownership and measurable patch candidates](MEMORY_OWNERSHIP.md)

## Immediate, evidence-backed corrections

1. **Static preflight is not candidate selection.** Running the current CLI against
   `runtime-bundle/build/libs/unified-infinity-0.1.0-dev.jar` returns `rejected` with
   `LOADER_JARJAR_UNSUPPORTED`, even though this exact deployment form runs. The
   report is saved above. Fix the authority model, rather than implementing a
   second NeoForge/Fabric solver in Python.
2. **One engine does not mean one undifferentiated algorithm.** NeoForge JarJar
   selects Maven-coordinate libraries, Fabric's solver selects Fabric mod
   candidates, and FML's final uniqueness/dependency validation builds its admitted
   mod list. These decisions operate on different namespaces/stages. One coordinator
   must own their ordering and preserve those boundaries.
3. **FFAPI is not initialized like a Fabric input mod.** Native generated entrypoint
   classes are `@Mod` classes. The inspected lifecycle class calls
   `LifecycleEventsImpl.onInitialize()` from its FML constructor. Connector's
   `main`/`server`/`client` invocation applies to the Fabric metadata it projected
   into the host. Replaying FFAPI initializer methods duplicates bridge listeners.
4. **The second loader payload is deliberately suppressed today.** FFAPI carries
   an older standalone FFLoader; Connector shades its own newer loader API and
   registers a dummy `net.fabricmc.loader` library version `999.999.999` to prevent
   the standalone copy taking over. The standalone language-loader service is
   explicitly removed from the shaded Connector build. This is awkward packaging
   debt, not proof of two active loader engines. Do not simply delete that guard.
5. **A source fork needs a new transform-cache identity.** Upstream cache version
   is Connector's package Implementation-Version plus side. Altering source while
   retaining that identity can reuse stale upstream cache outputs. Key changed
   behavior by a source/patch digest and test invalidation.

## Completion claims this audit does not make

This is source and archive analysis plus one static-preflight reproduction. It did
not launch another game, validate a refactored engine, exhaustively establish
upstream reachability, establish a speedup, or prove client/render/network parity. The later memory
extension analyzes the parent task’s already-recorded stress/JFR measurements; it
does not treat those single runs as a causal performance comparison.
The prior native-versus-compat server probe remains useful evidence for its
exercised behavior. It does not establish the integrated design proposed here.
