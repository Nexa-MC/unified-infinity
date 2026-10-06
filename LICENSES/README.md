# Additional reference-source notices

These texts accompany the unchanged reference source archives in
`source-workspace/fml-unified/provenance/`. Those JARs contain source rather than
compiled classes and do not embed a separate license-text file. This notice
supplements them without modifying their bytes or the accepted source identity.
Do not redistribute an archive alone without its applicable notices and terms.

## DevLaunch 1.0.2

- Upstream: <https://github.com/neoforged/DevLaunch>
- Archive source: <https://maven.neoforged.net/releases/net/neoforged/DevLaunch/1.0.2/DevLaunch-1.0.2-sources.jar>
- The retained `net/neoforged/devlaunch/Main.java` header credits Remko Popma
  (2017) and NeoForged and contributors and specifies Apache License 2.0
- Full text: [Apache-2.0.txt](Apache-2.0.txt)
- The archive is retained unchanged; its original source header remains authoritative

## JarJarSelector 0.4.1

- Upstream: <https://github.com/neoforged/JarJar>
- Archive source and hash are also recorded in
  `source-workspace/fml-unified/provenance/jarjar-source.json`
- Upstream [LICENSE](https://github.com/neoforged/JarJar/blob/main/LICENSE)
  publishes GNU LGPL version 2.1; full text: [LGPL-2.1.txt](LGPL-2.1.txt)
- The preserved [version-specific Maven POM](JarJarSelector-0.4.1.pom)
  declares LGPL 2.1. Its SHA-256 is
  `c52a5852dfef565b547cbea3bf866ca025bfca45166bc4f97fc6b62c3f040fbc`.
  The retained source classes have no more-specific license header. This notice
  does not invent an `or-later` grant or relicense this pinned archive
- Credits: NeoForged and the JarJar contributors; all existing archive content
  and provenance remain unchanged

## BootstrapLauncher 2.0.2

- Upstream: <https://github.com/McModLauncher/bootstraplauncher>
- Archive: `cpw.mods:bootstraplauncher:2.0.2:sources`
- Retained `cpw/mods/bootstraplauncher/BootstrapLauncher.java` header:
  copyright 2021 cpw; GNU Lesser General Public License, version 3
- Upstream [license notice](https://github.com/McModLauncher/bootstraplauncher/blob/main/LICENSE)
  refers to both COPYING.LGPL and COPYING
- Full texts: [LGPL-3.0.txt](LGPL-3.0.txt) and [GPL-3.0.txt](GPL-3.0.txt)
- This archive retains its version-3-only source notice. The new project grant
  cannot change it to version 2.1 or add a later-version option

## Immutable source archive identities

- `DevLaunch-1.0.2-sources.jar`: `a7b173d5f64f06cc19f398e2c3a3fcfa995736096b1a4de61175bef0b3edde5d`
- `JarJarSelector-0.4.1-sources.jar`: `48f49141fbe2db076e7dab02cb0f16aae4311b2caa7ff3e5ef5c2d284c440b1f`
- `bootstraplauncher-2.0.2-sources.jar`: `d148fae013b890a08061cd0407bcdba9b836d4ddc6135f869d2c8b80913f056c`

The LGPL 2.1 and Apache 2.0 texts are copied verbatim from existing retained
component texts. The standard LGPL 3 and GPL 3 texts are supplied verbatim from
the system's `/usr/share/common-licenses` copies, as companion license documents.
Original component copyright and grant notices remain in the source archives.

Other component-specific license copies stay in their original directories;
see [LICENSING.md](../LICENSING.md) and [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
This is not an exhaustive license audit of all separately downloaded dependencies.
