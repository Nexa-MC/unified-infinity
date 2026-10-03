# Internal QSL deployment slice

QSL is supplied internally; this experimental profile does not ask users to install a separate QSL aggregate. The first explicitly selected modules are `quilt_base` and `quilt_lifecycle_events` from official QSL 10.0.0-alpha.5+1.21.1. The complete 30-module publication inventory is in `docs/four-loader/quilt/qsl-availability.json`; it is an availability inventory, not a compatibility claim.

`docs/four-loader/quilt/bundled-initial.json` pins logical IDs, Maven coordinates, versions and SHA-256 values. With `-PqslInventory=../docs/four-loader/quilt/bundled-initial.json`, the host embeds the original module bytes as a digest-pinned managed inventory consumed by the existing Connector discovery queue (not independently admitted by NeoForge JarJar). No Quilt Loader engine is embedded. Runtime Quilt API facades and adaptation belong to the single coordinated core.

The host declares exact required logical-module versions. A different external QSL version cannot silently replace this tested profile. Byte-identical duplicate candidate selection remains the actual runtime resolver's responsibility and still needs a real duplicate-input acceptance test.

Build to `-PbundleBuildDir=build-quilt-candidate` so accepted earlier runtime bytes are not overwritten. Pair with a verified Quilt-capable managed core using `-PmanagedCoreJar=...` and `-PmanagedCoreSha256=...` only after that core is built. A structural-only host is not a runnable compatibility release.

Structural verification checks the exact 47-archive inventory, preserved logical IDs/versions, original bytes, accompanying licenses, no shaded Quilt engine, and exact dependency pins. Seven focused QSL tests cover positive deployment, schema, duplicate IDs, missing pins, wrong version and wrong hash. Minecraft runtime acceptance remains separate.

The original module JARs declare Apache-2.0 but omit full license text. The host includes standard Apache-2.0 text and contributor/source attribution alongside them; original JARs are not modified to add files. Any transformed runtime resource/bytecode views must retain their own provenance and adaptation record.
