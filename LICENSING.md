# Licensing scope

## Original Unified Infinity work

Copyright (C) 2026 Unified Infinity contributors.

Except for the exclusions and existing component licenses below, original code
and documentation contributed to Unified Infinity are licensed under the
**GNU Lesser General Public License, version 2.1 or (at your option) any later
version** (`LGPL-2.1-or-later`). See [LICENSE](LICENSE) for the version 2.1 text.

This work is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.

This grant covers only copyright interests that Unified Infinity contributors
are entitled to license. It does not claim ownership of copied or adapted
upstream material and is not a new license for every file in the repository.

## Existing and third-party licenses take precedence

File headers, component licenses, retained archives and upstream notices continue
to apply to their respective material. Modified upstream-derived files remain
under their applicable upstream licenses. Existing separately MIT-licensed probe
and shared-admission components remain MIT-licensed; no earlier permission is
withdrawn. The new `or-later` choice does not add that choice to upstream files
marked `LGPL-2.1-only` or `LGPL-3.0-only`.

Important examples (not an exhaustive transitive-dependency bill of materials):

| Material | Existing license / evidence |
| --- | --- |
| Connector base and derivatives | MIT; `integrated-loader/LICENSE`, `source-workspace/connector-four-loader/LICENSE`; Apache-licensed source slices retain their own headers |
| Adapter core 2.0.43+1.21.1 | MIT; `source-workspace/upstream/Adapter-LICENSE.txt` and component resource notice |
| FART 1.0.14 and its modified sources | LGPL-2.1-only in source headers; `source-workspace/upstream/FART-LICENSE.txt` |
| FML 4.0.42 and its modified sources | LGPL-2.1-only in source headers; `source-workspace/fml-unified/LICENSE-LGPL-2.1.txt` and `MODIFICATIONS.md` |
| Shared BOOT admission and explicitly licensed Forge/Clumps probes | Existing MIT notices in their respective directories |
| Adapted Quilt Loader 0.30.1 API slice | Apache-2.0; original FabricMC/QuiltMC headers and `source-workspace/connector-four-loader/src/main/resources/META-INF/licenses/` |
| FFAPI and selected QSL modules | Apache-2.0 notices in `runtime-bundle/src/main/resources/META-INF/licenses/`; runtime payloads are external inputs |
| DevLaunch, JarJarSelector and BootstrapLauncher reference source archives | Separate Apache-2.0, LGPL-2.1 and LGPL-3.0 terms; see [provenance-source notices](LICENSES/README.md) |

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for component provenance,
exact source records and additional notices. A directory's broad project license
must not override a more specific source header or third-party license.

## Artwork, trademarks and excluded content

The new LGPL grant covers code and documentation, not project names, trademarks,
logos or artwork. In particular it does not relicense `preload-ui/assets/`,
`preload-ui/src/main/resources/infinity-icon.png`, or the upstream Connector logo
at `source-workspace/connector-four-loader/src/mod/resources/logo.png`.
Existing permissions, if any, still apply; ask the relevant rights holder about
independent artwork reuse. No trademark license or upstream endorsement is granted.

Minecraft game binaries, assets, accounts and world saves are not licensed by
this project and are not part of the source distribution. Dependencies obtained
separately remain subject to their own licenses and terms.

## Redistributing source or binaries

Keep all applicable copyright notices, license texts, modification notices and
corresponding-source records. If you distribute modified LGPL components or a
combined binary, comply with the applicable LGPL source and linking/relinking
requirements, including users' rights to modify the covered library. Merely
linking to this repository or adding the root `LICENSE` is not a substitute for
meeting those requirements for the exact distributed artifact.

The source tree is a mixed-license collection. Compatibility of the licenses in
a particular linked, shaded or bundled executable must be assessed for that
artifact. In particular, do not infer that Apache-2.0 material or version-specific
LGPL components can be relicensed simply by applying the root grant. This source
publication is not a comprehensive legal clearance for a combined binary release.

Frozen source archives and runtime-resource notices describe their historical
snapshots. Their bytes and accepted hashes are preserved. This current scope
statement supplies the grant for original project work; it does not retroactively
change upstream licenses or assert that historical binaries have been rebuilt.
