# Third-party implementation and artifact notices

Unified ∞ Infinity is an R&D source integration using credited upstream software.
It is not presented as a clean-room implementation of Fabric, NeoForge, Connector,
FFAPI, Mixin or their authors' work. No public release is authorized.

- Sinytra Connector2.0.0-beta.17+1.21.1: MIT. The integrated-loader artifact is a
  disclosed source-derived build; its changed-source patch, original-source hashes,
  MIT text, build scripts and startup source identity accompany it.
- Sinytra ForgeAutoRenamingTool1.0.14: LGPL2.1 license text is retained. Its modified
  AsyncHelper is source-provided, together with the complete exact upstream source
  archive, patch and rebuild procedure. This archive is explicitly included in
  source checkpoints containing the modified binary.
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
