# Unified Infinity

**An experimental Minecraft 1.21.1 compatibility runtime and unified mod inventory.**

[简体中文](README.zh-CN.md) · [Contributing](CONTRIBUTING.md) · [Build guide](docs/fusion-v6/REBUILD.md) · [License scope](LICENSING.md)

Unified Infinity explores running mods from the Fabric, Forge, NeoForge and Quilt
ecosystems in a shared, source-integrated runtime. It builds on credited upstream
projects, including NeoForge/FML, Sinytra Connector and Adapter, Forgified Fabric
API, and Quilt APIs. This repository contains research source and evidence, not a
ready-to-install modpack or a stable public mod-authoring API.

## Current status

The accepted source baseline on `main` is the **v6 foundation**, originating at
[`e527f35`](https://github.com/Nexa-MC/unified-infinity/commit/e527f35b852ba1cb66b0fa11aff3df55ec60ad34).
Documentation changes do not expand that runtime acceptance.

- **Target:** Minecraft 1.21.1, Java 21, NeoForge 21.1.219 and FML 4.0.42
- **Verified:** one bounded Linux client run with a pinned five-user-mod set;
  real menu, corrected footer, unified inventory, exclusion details, copied-world
  reopen and save, and a clean exit on 2026-10-03
- **Inventory in that run:** five user mods, 56 loaded entries and 46 bundled API
  entries, with one API summary rather than counting each API module as a user mod
- **Not established:** arbitrary modpacks, complete APIs for all four loaders,
  Windows/macOS, production readiness, or a fresh v6 dedicated-server acceptance

See the [acceptance record and limits](docs/fusion-v6/README.md) and
[exact input/artifact pins](docs/fusion-v6/artifact-and-input-pins.json).
A compiling API facade, successful diagnostic job, or source hash match is not
proof that a real third-party mod works in-game. Work on `diagnostic/*` branches
is separate from the accepted baseline unless a later acceptance record says otherwise.

## Architecture

- **BOOT:** source-owned FML and shared admission decide what enters the loader
- **SERVICE:** compatibility discovery, transformation and source identity
- **GAME:** internal compatibility and product lifecycle components
- **Product UI:** unified mod inventory and persistent explanations of excluded
  external infrastructure
- **Preload UI:** loading progress supplied by the runtime, with bounded native tests

Admission metadata checks are **not an operating-system sandbox**. Admitted mods
execute code with the privileges of the game process. Use trusted inputs and a
separate test instance, and back up worlds before experimenting.

## Start here

To inspect and verify the checked-in source without downloading dependencies or
starting Minecraft:

```sh
git clone https://github.com/Nexa-MC/unified-infinity.git
cd unified-infinity
python3 source-workspace/verify-fusion-source.py
```

The verifier checks 655 core/FML/BOOT source records, 39 product records,
12 preload continuity records and seven launch helpers. It does not build or
certify the runtime. See [Contributing](CONTRIBUTING.md) for test expectations.

### Build prerequisites

- Python 3 and a Java 21 development kit
- Gradle 8.11.1; the historical build used Java `21.0.12.1+1`
- Exact external dependencies and generated Minecraft/NeoForge compile inputs
  described in [dependency restoration](docs/fusion-v6/DEPENDENCY-RESTORATION.md)

The source snapshot omits toolchains, the executable Gradle wrapper JAR,
compiled runtime/mod JARs, Minecraft binaries/assets and worlds. A plain
`./gradlew build` from a fresh checkout is therefore not a complete recipe.
A clean-network reconstruction has not yet been verified.

After restoring the documented toolchains and hash-pinned prerequisites, the
supported core build/test entry points are:

```sh
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 fullJar
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 check
```

Use the [full rebuild guide](docs/fusion-v6/REBUILD.md) for FML, product and preload
steps, missing generated fixtures, Git-derived versions and artifact verification.
Do not remove a checksum pin or silently replace a dependency to make a build pass.

### Installation

There is no supported one-click installation in this source checkpoint. The v6
loader installation requires separately reconstructed inputs and a reviewed,
local installation policy. The historical two-JAR `runtimeDistribution` layout
is not the v6 installation recipe. Do not mix the modified and original loader
components or copy diagnostic artifacts into a valuable game instance.

Obtain Minecraft and required dependencies from their official sources and
follow the [Minecraft EULA](https://www.minecraft.net/en-us/eula). This project
is not affiliated with or endorsed by Mojang, Microsoft, or the upstream loader teams.

## Repository map

| Path | Purpose |
| --- | --- |
| `source-workspace/connector-four-loader/` | Modified Connector, Adapter, FART and bounded compatibility sources |
| `source-workspace/fml-unified/` | Modified FML and its source provenance |
| `source-workspace/admission-bootstrap/` | Shared BOOT admission sources |
| `runtime-bundle/` | Product, inventory, exclusion notices and footer |
| `preload-ui/` | Preload window source and test harnesses |
| `docs/fusion-v6/` | Authoritative v6 acceptance, hashes and rebuild instructions |
| `four-loader/` | Pinned probes, fixtures and historical control evidence |
| `infinity-api/` | Standalone event-API experiment; not integrated into the game |
| `docs/four-loader/`, `docs/full-source-build/` | Earlier milestones; historical when their pins differ |

## Direction

The long-term goal is broader API and behavior compatibility across all four
loader ecosystems, verified with original mods and native-loader controls.
Complete four-loader API coverage remains unfinished. A future Minecraft 1.21.1
Paper/Bukkit plugin layer is a separate plan; this baseline does not run Paper
plugins. The standalone Infinity API experiment does not replace existing mod
APIs or require mods to be rewritten.

## Contribute and report problems

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Bug reports
should include the exact revision, Java/Minecraft/loader versions, minimal mod
set, reproduction steps and redacted logs. Keep expected behavior separate from
observed results. Please use [SECURITY.md](SECURITY.md) for sensitive findings.

## Licensing and credits

Original project code and documentation are covered by [LGPL-2.1-or-later](LICENSE)
only within the scope explained in [LICENSING.md](LICENSING.md). Existing and
modified upstream components retain their own licenses, including MIT,
Apache-2.0, LGPL-2.1 and LGPL-3.0. **The combined repository has multiple licenses.**
Brand artwork and third-party assets are outside the new LGPL grant.

Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), retained license texts,
source headers and corresponding-source records before redistributing any part.
A public source repository is not a blanket clearance to redistribute a combined
binary package or Minecraft content.
