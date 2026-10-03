# Unified ∞ Infinity

Private research source for **Minecraft 1.21.1**, **Java 21**, and
**NeoForge 21.1.219**. This is the M5 complete-core-source milestone, not a
universal compatibility release or a complete all-dependency source distribution.

## Included work

- Complete, modified Connector + FART + Adapter core corresponding source,
  digest-pinned reconstruction patches, upstream source archives and licenses
- Managed host/API packaging with client-only title and footer branding
- Custom early-loading window, original/derived artwork, and real progress events
- Three validated Adapter repairs for the unchanged official Lithium 0.15.4 JAR
- Admission, resource ownership, API, preload, archive and regression tests
- Machine-readable frozen server/client acceptance evidence and build provenance

Forgified Fabric Loader, FFAPI, Adapter runtime, NeoForge/FML, and Minecraft remain
credited external dependencies. No Minecraft binaries/assets, game screenshots,
world files, account data, credentials, toolchain installations or dependency
caches are included. Source-only `.jar` and `.zip` archives are explicitly
identified and contain source, resources and notices rather than compiled code.

## Start here

1. Read [M5 acceptance and limits](docs/M5-FULL-SOURCE-ACCEPTANCE.md)
2. Follow [complete-source reconstruction and build](docs/full-source-build/README.md)
3. Read [publication validation and corrections](docs/PUBLICATION-M5.md)
4. Review [third-party notices](THIRD_PARTY_NOTICES.md) and original component licenses

The full source ZIP is an immutable corresponding-source record. Reconstruct an
ordinary pinned Connector clone with the supplied patches before building; the
ZIP alone omits upstream build properties supplied by that clone. Repetition in
the observed dependency cache was verified, but fresh-machine bitwise
reproducibility is not claimed. Adapter userdev still declares a mutable snapshot.

## Fast source-only checks

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s runtime-bundle/tests -v
python3 -m unittest discover -s registry-probe -p 'test*.py' -v
python3 source-workspace/verify-source-package.py
JAVA_HOME=/path/to/jdk-21 bash infinity-api/check.sh
```

Component READMEs describe additional prepared dependencies. Runtime tests require
separately acquired official game artifacts, the exact pinned third-party JARs,
and appropriate Minecraft EULA acceptance. No test command signs in or publishes.

## Evidence boundary

The accepted runtime hashes refer to the immutable M5 binaries. This source
publication corrects stale attribution prose and restores missing package inputs;
it does not claim a new Minecraft run. Rebuilding a host with the corrected notice
resource may change its JAR digest and requires a new pin and regression.
Later mixed-pack experiments and later hopper tests are outside this snapshot.

No project-wide license is asserted for this mixed-license tree. Preserve the
specific upstream license texts and notices, including FART's LGPL obligations.
