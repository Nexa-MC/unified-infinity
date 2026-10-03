# Build and packaging verification

Verified on 2026-10-03 with Temurin JDK 21.0.12.1+1 and Gradle 8.11.1.

## Passed

- Java 21 compilation against NeoForge 21.1.219's FML 4.0.42 API
- `clean build runtimeDistribution` on two consecutive clean builds
- Five archive-verifier unit tests
- FFAPI aggregate SHA-256 and byte-for-byte nested copy
- Recursive archive integrity and unique original native module IDs
- 45 total archives: host, FFAPI aggregate, and 43 upstream nested archives
- 45 native mod IDs across those archives
- Connector full-JAR SHA-256 and required early service-provider entries
- Runtime ZIP contains exactly two top-level mod JARs
- Reproducible host JAR hash across the clean builds

Host JAR:
`build/libs/unified-infinity-0.1.0-dev.jar`

SHA-256:
`f09e465bf467cc5649fa1c66cbe6600bea030d92d9e8d977d7132e9f377b7696`

Machine-readable archive inventory:
`build/reports/bundle-verification.json`

## Discovery ordering

Inspection of the installed FML 4.0.42 and JarJarSelector 0.4.1 binaries confirms:

1. `IOrderedProvider.DEFAULT_PRIORITY` is 0 and `LOWEST_SYSTEM_PRIORITY` is -1000
2. `ServiceLoaderUtil` sorts provider priorities in descending order
3. The normal JarJar dependency locator uses the default priority
4. JarJarSelector calls `recursivelyDetectContainedJars`
5. ModDiscoverer passes the updated discovered-mod list to each next locator
6. Connector beta.17's locator reports `LOWEST_SYSTEM_PRIORITY`

Therefore the normal JarJar pass discovers the host's FFAPI aggregate and its
modules before Connector resolves Fabric dependencies. Connector still must be
a top-level JAR for its earlier transformation services to be discovered.

## Build command used

From this directory, with the repository-local Java/Gradle toolchain:

```
gradle clean build runtimeDistribution --write-locks \
  -PffapiJar=../docs/research/upstream/ffapi-baseline.jar \
  -PneoforgeLibraries=../run/neoforge-native/libraries \
  --no-daemon --console=plain
```

`build-verified.log` contains the successful output. The initial build exposed
an undeclared generated-resource dependency in `sourcesJar`; it was fixed by
using the generating task as the source directory provider, then both clean
builds passed.

## Scope

This record covers compilation and packaging only. No Minecraft process was
started by this build project, and it did not accept an EULA. Dedicated-server,
client, parity, performance, and third-party mod results must be recorded by the
integration run separately. Byte-identical embedding is not a universal
compatibility or performance guarantee.

The public Maven-resolution path was not exercised in this local-input build;
the official release and loader artifacts already retrieved for integration
were used. Exact API coordinates are Gradle-locked, while FFAPI and Connector
also require the recorded immutable SHA-256 values.
