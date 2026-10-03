# Small proposed Forge test list

No mod in this list has been launched by this audit worker. The user subsequently
approved verification and isolated native Forge/Unified tests of the exact Clumps
artifact below. Static verification and inspection are now complete; game execution
belongs to the parent-coordinated runtime workers.

## First: our own genuine Forge-only probe

Use the API contract in [ABI-SLICE.md](ABI-SLICE.md). Its source and built SHA-256
must be frozen after implementation, before the coordinated native/Unified runs.
There is no built probe hash yet. Avoid unrelated third-party dependencies.

Proposed official native control: Minecraft **1.21.1**, Forge **52.1.0**, Java
**21**, isolated disposable game directory. Do not mix Forge libraries into the
NeoForge process. Parent coordination is required before installing/launching.

- Installer: https://maven.minecraftforge.net/net/minecraftforge/forge/1.21.1-52.1.0/forge-1.21.1-52.1.0-installer.jar
- SHA-256: `f1b620f2879ad6a5bbe15daba4d8f81eab9f5e08004967604960b98996bdebc4`
- SHA-1: `fa4f90047c23e6df4d2b4e649aec7fd5d1e20acd` (matches official release page)
- MDK: https://maven.minecraftforge.net/net/minecraftforge/forge/1.21.1-52.1.0/forge-1.21.1-52.1.0-mdk.zip
- MDK SHA-256: `da7ab2ca88a997442d59633a47582b3c528ea268538031b820b3aae95a660991`
- MDK SHA-1: `a081da53578f1bd9b053cf7d65dbe9e95d2b351c` (matches official release page)

The install profile lists the actual Forge bootstrap/loader/game-patch and
transitive library inputs. Their complete native-install artifact lock is a
future installation output, not claimed complete by downloading the installer.

## Approved third-party candidate: Clumps Forge 19.0.0.1

**Specific Forge-only artifact**, not an assertion that the whole project is
Forge-exclusive. This is one small approved candidate, not an initial
registry-probe substitute.

- Official author project: https://modrinth.com/mod/clumps
- Verified uploader/author: **jaredlll08**, Modrinth user `l45nT5ov`;
  official source project https://github.com/jaredlll08/Clumps
- Exact release: https://modrinth.com/mod/clumps/version/aeoQuGBI
- Modrinth project ID `Wnxd13zP`; version ID `aeoQuGBI`
- Filename `Clumps-forge-1.21.1-19.0.0.1.jar`
- Version **19.0.0.1**, Minecraft **1.21.1**, loader list **[forge]**
- Published **2024-08-13T07:49:16.412306Z**; **18,226 bytes**
- Published SHA-1: `e075af7907303f429165d2265d77c0ecac2adcab`
- Locally verified SHA-256: `e1de425ddd6f2b5c195c37a008d9fbc2c00c32fe1e214d76c63ab35446d13c19`
- Published SHA-512: `8a172b05b9efe42dc2dfdab6c89fb94e9255b794996c416ab979cbf5688f4c37994db8f2660ceb271f8a5ee1c3ddc38808ebe1d2c683236a8eba989ac9b7e0bf`
- Local bytes match published SHA-1 and SHA-512 and the published size
- Exact `mods.toml`: `javafml` loader `[52,)`; mandatory `forge` `[52,)` and
  mandatory `minecraft` `[1.21.1]`, both `ordering=NONE`, `side=BOTH`
- Release API declares no additional mod dependencies; archive inspection finds
  no additional declared mod dependencies and no nested JARs
- Expected behavior to test, after the relevant hooks/Mixins are inspected and
  supported: XP-orb aggregation and XP conservation on a controlled server,
  comparing the same original JAR on native Forge and Unified. This would test
  real mod behavior, not startup performance

Evidence is the captured official project/release API metadata under `upstream/`,
the verified digest record and static inspection under `clumps-inspection/`.
The first acceptance run remains the owned Forge probe; Clumps may require a
larger hook/Mixin surface than that minimal API slice.

## Actual API and transform surface

- All 15 classes are major 65 (Java 21). Minecraft calls and Mixin target strings
  are Mojmap; no SRG or intermediary-shaped name constants were found
- Genuine Forge `@Mod("clumps")` with a public zero-argument constructor
- Constructs `PlayerXpEvent.PickupXp(Player,ExperienceOrb)` and returns the boolean
  from `MinecraftForge.EVENT_BUS.post(Event)`. This directly exercises the
  Forge/Neo post-return and cancellation mismatch identified in the ABI audit
- Clumps `ValueEvent` and `RepairEvent` extend Forge `Event`; both are mutable
  payload events posted on the same bus. The post return is ignored for these
  two events, but it is used for pickup
- Two ServiceLoader provider resources select its Forge event/platform helpers.
  Preserve provider contents and host module visibility
- Required Mixin config contains `ExperienceOrbAccess` and `MixinExperienceOrb`.
  The latter has priority 1001. Hooks include merge, player pickup, Mending,
  save/read data, plus age/count accessors and local-variable-sensitive injection
- The released config names `clumps.refmap.json`, but **that resource is absent**.
  Named target strings are present directly. This is not yet a demonstrated
  failure: compare the native control before making any fix or generating a
  replacement. No Mixin compatibility pass is claimed from static inspection

## Approval and initial review boundary

A parallel research fetch attempted to retrieve the exact Clumps artifact along
with official Forge reference inputs. The reviewer rejected that artifact fetch:
the user requires a concrete test-mod list and confirmation before adding new
third-party mods. The rejection arrived after a Clumps-named file had already
materialized in the research directory. Inspection stopped and the parent was
informed immediately; no download retry occurred.

The user then approved verification and isolated cloud native Forge/Unified
tests, without accounts or a public network service. The existing file was
verified against published hashes before archive inspection and disassembly;
no redownload or game execution occurred. It is now admitted for that exact
test scope. The source lock and verifier include its frozen local SHA-256.
