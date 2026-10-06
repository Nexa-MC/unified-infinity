# Third-party implementation and artifact notices

Unified ∞ Infinity is an R&D source integration using credited upstream software.
It is not presented as a clean-room implementation of Fabric, NeoForge, Connector,
FFAPI, Mixin or their authors' work. Original project code/documentation licensing
is now described in `LICENSING.md`; component licenses remain unchanged. This
source publication does not certify a combined binary distribution.

- Sinytra Connector2.0.0-beta.17+1.21.1: MIT. The integrated-loader artifact is a
  disclosed source-derived build; its changed-source patch, original-source hashes,
  MIT text, build scripts and startup source identity accompany it.
- Sinytra ForgeAutoRenamingTool1.0.14: LGPL2.1 license text is retained. Its modified
  AsyncHelper is source-provided, together with the complete exact upstream source
  archive, patch and rebuild procedure. This archive is explicitly included in
  source distributions accompanying the modified binary.
- Sinytra Adapter core2.0.43+1.21.1: MIT. The complete pinned source archive,
  complete modified core sources, three Lithium-fix source changes, original
  copyright/license, patches and reconstruction instructions are included under
  source-workspace/. Adapter runtime remains a separate upstream dependency.
- Forgified Fabric API0.116.7+2.2.1+1.21.1: Apache2.0; byte-identical aggregate and
  nested modules are embedded in the managed host. Original IDs, aliases and notices
  remain. Upstream license copies are in runtime-bundle resources.
- Fabric Loader/Forgified Fabric Loader: upstream Apache2.0 notices and sources are
  retained in research records; their public API and existing implementation are
  reused, not claimed as newly written.
- NeoForge/FML, Minecraft and host-selected Mixin/ASM/native libraries are supplied
  by official installer/development tooling. Minecraft game binaries/assets are
  never included in our user-facing source checkpoint. Minecraft EULA acceptance
  applies only to the authorized private test instances.
- LWJGL3.3.3 is a compile/runtime dependency of the preload provider. Its binaries
  are not shaded into the provider JAR. The host supplies the official runtime.
- The cube/infinity artwork was supplied by the user. The original is preserved;
  the transparent derived asset is not represented as carrying a valid original
  C2PA signature after modification.

Exact artifact coordinates, source URLs and checksums live in baseline-lock.json,
component provenance records and their captured upstream license files. This file
summarizes attribution; it does not replace the original license texts or claim
that later public distribution has received a comprehensive legal review.

## M5 source publication

The companion core is the complete source-derived Connector/FART/Adapter build,
not an unchanged upstream binary. Its complete corresponding source ZIP is
`source-workspace/artifacts/unified-infinity-complete-connector-fart-adapter-sources.zip`.
See `source-workspace/source-lock.json`, the original licenses under
`source-workspace/upstream/`, and `docs/full-source-build/README.md`.
No single license replaces all component licenses in this mixed-license tree.
The original M5 attribution update did not relicense any component; the later
root grant is scoped by `LICENSING.md` and preserves these existing terms. Frozen runtime evidence
keeps its original tested hashes; the corrected host notice is a publication
change and a future rebuilt host must be pinned and tested separately.

## Accepted four-loader source publication

The accepted98 complete source is under `source-workspace/connector-four-loader/`,
with its exact 390-record identity in `docs/four-loader/accepted-build-identity-98d86a92.json`.
The earlier M5 source archive remains historical corresponding source, not the
complete source record for the newer four-loader core.

The bounded Quilt API adaptations retain the original Quilt Loader Apache-2.0
license and modification attribution under the core's `src/main/resources/META-INF/licenses/`.
The host's internally supplied QSL base/lifecycle modules remain byte-identical
upstream components with `runtime-bundle/src/main/resources/META-INF/licenses/QSL-*`
license/source notices. No Quilt Loader runtime engine is embedded. Forge compatibility
facades are a bounded source implementation, not a bundled Forge runtime or a claim
of complete Forge API semantics. Original probe licenses remain with their sources.

All existing Connector/Adapter MIT, FART LGPL-2.1, FFAPI/QSL Apache and other original
notices remain. This does not relicense the combined project. Runtime resource notices
are preserved as the frozen accepted source; this external clarification does not
alter the hashes of already accepted core/host/provider binaries.


## Source-owned FML and shared admission

The v6 source snapshot includes modified FancyModLoader4.0.42 sources under
`source-workspace/fml-unified`, with LGPL-2.1 text, upstream provenance and
`MODIFICATIONS.md`. Shared BOOT admission retains its MIT notice. Connector
and Adapter retain original Sinytra attribution; modified FART retains LGPL-2.1
and corresponding source. Original component licenses apply independently;
this project does not replace them with a blanket license.

## Open-source documentation update (2026-10-06)

Original project code and documentation, to the extent contributors have the
right to license them and where no existing component grant applies, use
LGPL-2.1-or-later under `LICENSING.md` and `LICENSE`. This does not replace
Connector/Adapter MIT, FML/FART LGPL-2.1-only, Quilt/Fabric Apache-2.0 or any
other upstream terms. Existing MIT probe/admission grants remain in place.

The retained DevLaunch 1.0.2, JarJarSelector 0.4.1 and BootstrapLauncher 2.0.2
source JARs in `source-workspace/fml-unified/provenance/` have accompanying
license texts and archive-specific notices in `LICENSES/`. They are reference
source archives, not shipped executable JARs. Their original bytes are unchanged.
The pinned BootstrapLauncher source specifically declares LGPL version 3; it
is not covered by the root version-2.1-or-later grant.

Original user-supplied and upstream branding assets are excluded from the new
code/documentation license grant. See `LICENSING.md` for scope and redistribution
limits. Frozen runtime notices and source identities are historical evidence;
this documentation-only update does not change any accepted runtime artifact.
