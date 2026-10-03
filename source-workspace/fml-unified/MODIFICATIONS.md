# FML 4.0.42 source successor: Unified admission candidate

Modified 2026-10-03. Original Forge Development LLC/NeoForged contributor headers
and LGPL-2.1-only attribution are preserved. Complete official source archive:
https://maven.neoforged.net/releases/net/neoforged/fancymodloader/loader/4.0.42/loader-4.0.42-sources.jar
SHA-256 43ecb6251d1ca3b2f5e926de2d83e60fc8c5732a9c01967351b5dd2aa6a1625a

Changed host integration: ModDirTransformerDiscoverer, ClasspathTransformerDiscoverer,
ModsFolderLocator, ModDiscoverer pipeline, JarInJarDependencyLocator and native
production client/server and NeoForge development grouped platform providers.
The manifest identifies the modified build. The unmodified full archive content
and every upstream file hash are recorded in provenance/upstream-source.json.

The internal inventory/session package is compiled from ../admission-bootstrap.
That package has exactly one runtime owner, this BOOT loader module; its separate
model JAR is compilation-only and must never ship. No class injection into a
precompiled FML JAR is used. build_source.py compiles all 179 upstream Java sources
and the shared source package together, then packages source-owned resources.

This source candidate has no approved installation policy by default. Runtime
marker, dependency and real client/server acceptance remain required. It does
not alter the frozen accepted client, its original JARs, or the resolver's real
mandatory/optional dependency semantics.
