# Unified ∞ Infinity

Private R&D source for **Minecraft 1.21.1**, **Java 21**, and **NeoForge 21.1.219**.
The current published milestone is the first bounded four-loader acceptance.
It is evidence for one small pinned pack, not universal compatibility or a public release.

## Accepted snapshot

- Core `98d86a92…`: complete Connector/FART/Adapter source with bounded Forge and
  native Quilt integration; all 390 embedded source/build identity records match
- Host `746ca5e3…`: managed FFAPI plus the two selected original QSL modules
- Provider `7b549d37…`: the existing custom early window, unchanged from M5
- Real client: original Fabric Lithium/Chunky, NeoForge Farmer's Delight, Forge
  Clumps and native Quilt OP Tab, with list visibility and local save/reopen checks
- Separate native Forge/Quilt controls and a combined server control preserve their
  exact scope; the server's Quilt test uses a project-owned probe, not OP Tab

Start with [the acceptance index](docs/four-loader/README.md),
[the frozen scope statement](docs/four-loader/ACCEPTANCE-README.txt), and
[publication verification](docs/four-loader/PUBLICATION.md).
The original [M5 record](docs/PUBLICATION-M5.md) remains historical evidence.

## Source layout

- `source-workspace/connector-four-loader/`: frozen accepted complete core source
- `runtime-bundle/`: accepted host source, QSL/FFAPI pins and notices
- `preload-ui/`: accepted provider sources and original/derived product artwork
- `four-loader/`: bounded adapter/probe/control test source and scoped summaries
- `docs/four-loader/`: exact source identity, component pins, provenance and limitations
- `source-workspace/provenance/`: historical M5 provenance, not the accepted98 identity

Run `python3 source-workspace/verify-four-loader-source.py` for source-only integrity
checks. [Reconstruction instructions](docs/four-loader/REBUILD.md) require the pinned
upstream Git context, unbundled tools and official dependency artifacts. No fresh
Java/Gradle build or game run was performed for this publication.

## Known limits

The accepted provider still has 16:9 letterboxing and long host-driven input-polling
gaps. The built-in list remains the ordinary 56-logical-record presentation.
Successor UI grouping/labels, foundation/bridge exclusion policy and a new independent
public API are outside this snapshot. Performance, GPU certification and arbitrary
mod or cross-version compatibility are not claimed.

These historical tests inherited their process environment. A later key-name-only
audit identified an inheritance risk; environment hardening is separate work.
Functional passes do not establish OS isolation or absence of data access/transmission.
No credential values, raw process inventories, game binaries/assets, captured game
media, save files or executable third-party mod archives are distributed here.

Preserve [all component notices](THIRD_PARTY_NOTICES.md), including FART's LGPL
corresponding source and original Quilt/FFAPI/QSL licenses. No blanket project-wide
reuse license is asserted for this mixed-license tree.
