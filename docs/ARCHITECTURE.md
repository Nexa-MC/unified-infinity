# Architecture and evidence gates

## Fixed boundary
Minecraft 1.21.1 was explicitly selected by the user. Host choice is delegated.
NeoForge is the initial host because Connector provides a maintained Fabric binary
translation path and FFAPI ports Fabric API contracts onto NeoForge lifecycles.
The official Connector 1.21.1 release is prerelease software; this project does
not relabel its compatibility guarantees as stable or universal.

## Layers
1. **Version adapter**: Minecraft classes/mappings/registries/lifecycle for exactly
   1.21.1. A different game version is a different validated target, not a renamed jar.
2. **Loader adapters**: NeoForge native runtime plus upstream Connector's Fabric
   discovery, remapping and translation. Versioned interfaces isolate extensions.
3. **API implementation bundle**: FFAPI for NeoForge; original modules/IDs/versions
   remain visible. A plain Fabric API binary is not assumed to work on NeoForge.
4. **Transformation pipeline**: preserve upstream Mixin and Connector adaptation;
   remapping/refmaps/target patches occur before target classes are defined. No
   early reflective class loading during admission. Mixin errors retain target,
   injector, namespace, phase and transformer provenance.
5. **Admission and diagnosis**: resource-bounded read-only inspection plus runtime
   evidence, strict separation between accepted metadata and runtime compatibility.
6. **Regression harness**: same unchanged JAR hash in native Fabric and compatible
   NeoForge profiles; native NeoForge cases establish the other host baseline.

## Internal bundle acceptance
API bundling must work from the delivered runtime package without asking users to
install a separate API mod. Logical API metadata must remain intact. Simply listing
fake built-in module IDs without executable implementations is prohibited. Candidate
JarJar bundling must prove nested discovery, dependency resolution and early-loader
ordering before it can be accepted. Conflicting external API copies must receive a
clear diagnostic, never silently override the tested internal implementation.

## Failure attribution
Retain categories: artifact/security; metadata; game_version; environment;
dependency; loader/bootstrap; mapping/linkage; API/lifecycle; Mixin/transform;
ordering; mod_pair; unknown. A successful native run and failing compatibility run
is presumptively an adapter issue until evidence shows otherwise. A mod-pair label
requires independently successful single-mod tests and reproducible pair failure,
with native comparison. Never infer mod-pair failure from a loader stack trace.

## Runtime gates
No blanket support claim. Capabilities are keyed by game version, host version,
source loader, environment, mod hash, dependency set and exercised behavior.
Compilation is not bootstrap; bootstrap is not world creation; world creation is
not save/reload, networking or rendering. Unknowns stay unknown.

## Next scope
Quilt, legacy Forge, cross-game-version compatibility and Bukkit are outside this
first target. Adding them requires separate adapters and parity evidence, not a
metadata alias. Public publication is a separate authorization step.

## Java runtime floor
Every target adapter has a minimum host JVM of Java21. Future Minecraft versions may require a higher version. Supporting an older game onJava21 still requires testing bytecode transformers, obsolete APIs, native libraries and game/bootstrap behavior; changing --release alone does not establish compatibility. The direction of cross-Minecraft compatibility is not yet a fixed product contract.

## Verified source-refactor progress
The first real source fork modifies the existing ConnectorLocator/JarTransformer path, retaining one provider identity. The initial bounded scheduler version preserves every entry payload in17 transformed JARs (2088 entries) against upstream in sequential and4-worker runs. ActualMinecraft tick injection/save/reopen passes in both. This is incremental source integration, not completion of all architecture factoring. Further work is removing nested remapper executors and unifying cache identity; untested follow-up builds are not covered by the initial result.
