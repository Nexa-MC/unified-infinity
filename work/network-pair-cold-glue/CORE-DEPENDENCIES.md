# Exact core build dependency capture

`capture_core_dependencies.py` reads the preserved strict Gradle verification XML, the exact render build identity, original restoration locks, the observed Gradle file cache, and the existing pinned SNAPSHOT repository. It writes a download index only. It never copies/publishes a binary, downloads, or starts Java/Gradle.

    python capture_core_dependencies.py --repo-root /path/to/mod-compat-runtime --output /path/to/new-core-lock.json

The output must not exist. The inspected cache is the explicit API1 cache which the render assembly uses through a symlink. The capture reads its real repository path, without following a symlink extraction route. The XML's 347 components / 712 artifact entries bound eligibility. Inspection is additionally bounded at 2,000 files, 512 MiB total, and 64 MiB per artifact. The full historical verification set is retained because a narrower complete plugin/test resolution graph was not preserved.

The delivered index has 706 entries totaling 247,379,240 bytes: 702 rehashed Gradle cache artifacts plus four pinned SNAPSHOT files. They contain 237 JARs, 123 Gradle module metadata files, 344 Maven POM files, and two ZIP artifacts. All 169 exact candidate dependency hashes have verified observed bytes in this index. Pure Python recomputed all 670 source byte streams, these 169 dependency byte streams, and the recorded exact compiler-runtime string, reproducing `54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6` exactly. This proves the reference identity; it does not claim a consumer JVM or build ran.

Excluded: 58 cache files absent from strict verification and one additional ModDev plugin marker POM with mismatching bytes. The expected strict ModDev POM variant was found and is included. Six XML-listed release artifacts (JAR/module/POM for external FART and Adapter core) were absent and are explicitly omitted because the unchanged render build substitutes them with `:infinity-fart` and `:infinity-adapter` source projects. No expected identity dependency is omitted. Exact exclusions and omission reasons are machine-readable in the index.

110 indexed artifacts have known exact URLs from existing restoration locks. The remaining release candidates use repository-layout URLs explicitly marked `availability-unverified`; no remote availability was tested. All four SNAPSHOT artifacts retain the original timestamped URLs, using marker build `1.2.1-20260813.224440-41` and implementation build `1.2.1-20260813.224440-42`. Every future download must satisfy its exact size and SHA-256 regardless of URL availability or metadata returned by a server.

Artifact `path` values are relative to the consumer `work/api1` root and target `source-workspace/pinned-build-maven`. The shape is compatible with the existing restore helper's `artifacts`, `allowedHosts`, `urls`, `phase`, `bytes`, and `sha256` fields. The stage is `core-build`.

The driver needs a consumer-only init adapter which uses this restored Maven file repository for pluginManagement and project resolution while retaining strict verification. Keep the four source bootstrap SNAPSHOT artifacts also in the existing `pinned-maven` location required by the original exclusive repository rule. Gradle's file cache payloads alone are not an offline cache; its binary metadata/cache indexes are deliberately excluded.

Official generated ModDev/NeoForm inputs, FML local library paths, QSL/FFAPI original archives, actual regression probe/mod fixtures, assets and launch exports still belong to the separate runtime restoration stage. No clean-runner build was attempted, and these URLs plus a successful capture must not be described as cold-runner success.
