# Unified ∞ Infinity

Experimental Minecraft **1.21.1 / NeoForge 21.1.219 / Java 21** packaging host.
It embeds the official **Forgified Fabric API 0.116.7+2.2.1+1.21.1** byte for byte
and uses the original **Sinytra Connector 2.0.0-beta.17+1.21.1** as a companion.
It is not a new compatibility engine and does not promise all Fabric mods work.

## Architecture

Put these two files in the NeoForge instance's `mods/` directory:

1. `unified-infinity-0.1.0-dev.jar` (this Java host, including FFAPI)
2. `connector-2.0.0-beta.17+1.21.1-full.jar` (the unchanged official release)

Then add existing, unchanged **Fabric 1.21.1** mod JARs appropriate for the side.
There is no separate Fabric API / Forgified Fabric API installation step.
Remove a standalone FFAPI copy to keep the test configuration unambiguous.
Do not install the ordinary Fabric API aggregate beside this runtime.

The host exposes the FFAPI aggregate through NeoForge's standard
`META-INF/jarjar/metadata.json`. That aggregate retains all 43 original nested
modules, native mod IDs, mixins, transformers, resources, and version metadata.
The entire aggregate remains byte-identical to the pinned upstream release.
The host does not extract JARs from its constructor: constructors run too late.

Connector stays at the top level because its service providers must be visible
to the early loader. Nesting Connector as a normal mod dependency is unsafe.
Appending FFAPI only to Connector's own JarJar metadata is also unsafe because
Connector scans Fabric dependencies before its final embedded-JAR scan.

NeoForge's ordinary JarJar dependency locator discovers the host's API modules
before Connector's `LOWEST_SYSTEM_PRIORITY` dependency locator resolves Fabric
mods. Runtime validation of this ordering is still required; a successful Java
build or archive check alone is not evidence that a mod or game booted.

## Build

Use JDK 21 and Gradle 8.11.1. There is no bundled wrapper binary. From this folder:

```
gradle clean build --write-locks
gradle runtimeDistribution -PconnectorJar=/absolute/path/to/connector-2.0.0-beta.17+1.21.1-full.jar
```

Offline dependency input is accepted as `-PffapiJar=/absolute/path/to/ffapi.jar`;
the same pinned SHA-256 is mandatory. Build outputs:

- `build/libs/unified-infinity-0.1.0-dev.jar`
- `build/distributions/unified-infinity-0.1.0-dev-runtime.zip`
- `build/reports/bundle-verification.json`

For a fully local build against an already installed NeoForge server, also pass
`-PneoforgeLibraries=/absolute/path/to/server/libraries`. API coordinates remain
locked by Gradle; FFAPI's exact version and immutable bytes are locked separately
so switching between local and Maven artifact input does not change the bundle.

The build uses NeoForge FML 4.0.42 and mergetool's distribution marker API only
at compile time. No Minecraft APIs, deobfuscation, custom classloader, or copied
Fabric interfaces are needed. All Minecraft/FML runtime behavior is provided by
the installed loader and upstream dependencies.

`check` validates the embedded bytes, 43 nested modules, unique mod IDs, service
separation, notice files, and archive safety. It never starts Minecraft, accepts
the Minecraft EULA, or executes a downloaded Fabric mod. The runtime ZIP keeps
Connector's full JAR unchanged at the top level of `mods/`.

## Acceptance gates

After a user-authorized dedicated-server/client run, record independent results:

1. NeoForge boot without the bundle
2. Bundle + Connector + no third-party mods; verify the host's initialization log
3. A known compatible unchanged Fabric 1.21.1 mod on its supported side
4. Each actual requested mod, mixin-heavy mods, and relevant native-mod pairings

Use separate fresh directories and worlds for each gate. A server-only run does
not test rendering, client events, or client mixins. Keep the original JARs and
record hashes. Unsupported mixins, native/Fabric collisions, missing third-party
libraries, and different Minecraft versions remain possible failure causes.

## Provenance and licensing

Sinytra and FabricMC wrote the upstream compatibility components. Their original
module identities remain visible in the loader. Upstream license texts and an
attribution notice are included. The official artifacts have no top-level license
entries, so verified source license copies are provided explicitly. Public
redistribution still needs a full upstream transitive-license audit and a license
decision for this host; no public publication is performed here.

Pinned primary sources:

- https://github.com/Sinytra/Connector/releases/tag/2.0.0-beta.17%2B1.21.1
- https://github.com/Sinytra/Connector/blob/2.0.0-beta.17%2B1.21.1/gradle/libs.versions.toml
- https://github.com/Sinytra/Connector/blob/2.0.0-beta.17%2B1.21.1/src/main/java/org/sinytra/connector/locator/ConnectorLocator.java
- https://github.com/Sinytra/ForgifiedFabricAPI
- https://maven.neoforged.net/releases/net/neoforged/neoforge/21.1.219/neoforge-21.1.219.pom
- https://docs.neoforged.net/toolchain/docs/dependencies/jarinjar/
