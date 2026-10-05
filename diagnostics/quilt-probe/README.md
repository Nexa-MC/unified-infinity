# Original API1 Quilt probe diagnostic

This is a source-only staging package for the single diagnostic branch
`diagnostic/quilt-loom-api1-20261005-0934` in `Nexa-MC/unified-infinity`.
Publishing and starting the workflow belong to the separately authorized publisher.
Check the repository's zero-Actions stop-spend guard immediately before publication.

The workflow has one serial `ubuntu-24.04` job, a hard 30-minute limit, read-only
repository permissions, and SHA-pinned official checkout v4.2.2. It has no main or
pull-request trigger, larger runner, secrets, Actions cache, or artifact upload.
The unchanged original probe builder, Java sources, and resource bytes are preserved
under `four-loader/quilt-api-probe`.

The self-authored probe and diagnostic helper code are copyright 2026 Unified
Infinity contributors and provided under the full MIT notice in `LICENSE`, copied
unchanged from the existing project notice. The original probe resource bytes are
unchanged. External tools, mappings, libraries, and Minecraft inputs retain their
upstream authorship and licenses; this stage does not relicense those inputs.

## Execution boundary

1. Verify the source manifest and complete dependency lock before downloading.
2. Restore the pinned official JDK 21.0.12.1+1 and Gradle 8.11.1, official unmodified
   Quilt Loom 1.8.5 and dependency closure, official Minecraft client/server inputs,
   mappings, compile libraries, Quilt loader, and three original QSL modules.
3. Seed exact original official Minecraft version metadata through Loom's supported
   `customMinecraftMetadata` API. The metadata is checked in as JSON; no Minecraft
   binaries are included in this package.
4. Run the official plugin strictly offline in a new cache, with one Gradle worker
   and a 1,280 MiB heap, to generate the merged/intermediary Minecraft and tiny maps.
   The minimal mapping project has no mod source and requests only
   `prepareProbeMappings` and its `classes` dependency. The diagnostic explicitly
   resolves `minecraftNamedCompile` and reports the official providers' output paths;
   Loom 1.8.5 creates intermediary and named Minecraft outputs during evaluation.
   It does not resolve or run
   the real-mod test set. A task-graph guard rejects assets, launch/run, JavaExec,
   tests, and source-decompilation tasks.
5. Require the original generated input hashes:
   - merged/intermediary Minecraft: `bd5e9b18303dfbd03365286b126dfde5c688861307e0ed541e16313e6aca1d90`
   - mappings.tiny: `0656f2619dc6e63f1fbfb06c2e4eaf541cec91853afb8ecd37588b229eca40f7`
   Before this gate, log a bounded path/existence/size/SHA-256 inventory of generated
   JARs and tiny maps. Failure messages distinguish a missing path from a hash
   mismatch. The inventory contains metadata only, never Minecraft payload bytes.
   An existing mismatched expected JAR also reports entry counts, compressed and
   uncompressed totals, timestamp/method metadata, entry-order hash, and a
   deterministic digest of sorted entry names, sizes, and content hashes. These
   diagnostics do not change or normalize any generated JAR or acceptance pin.
6. Require all 22 original builder input hashes and invoke the unchanged builder.
   Require the original probe JAR hash:
   `9106f5a6629d3e3f2206bc967d77aaff228f67ef6e216cd8f27f79139e743dfe`.
7. Only the exact self-authored probe, at most 65,536 bytes, can be returned in
   checksummed Base64 log lines after the successful build receipt. The publisher
   must review this explicit output step before starting the workflow. The output
   guard additionally allows only original resources and the probe's own class
   namespace. Minecraft binaries and negative-control JARs are never returned.

Every download and redirect is limited to allowlisted HTTPS hosts; each input has
an exact byte count and checksum. Downloads total at most 1 GiB and have a 10-minute
restoration deadline. The offline mapping step has a 12-minute subprocess deadline;
the unchanged probe builder has a 3-minute deadline. The outer job bounds all work.

## Local source-only validation

Run `python3 diagnostics/quilt-probe/ci/bootstrap.py check` from this staging root.
It does not download inputs or start a JVM. Use `check --require-ready` to reject
any unresolved prerequisite. Build mode is restricted to the literal approved
GitHub repository and branch and requires the explicit `--fetch` flag.

`ci/dependency-lock.json` records missing pins until all captured inputs are supplied.
An absent or mismatched input fails closed; no builder pin, original source, official
Loom class, platform detection, IPC check, or local socket restriction is patched.
Source-only validation does not establish a successful CI build or any game behavior.
Native/Unified GUI tooltip, dedicated-server rejection, and real-mod acceptance
remain separate work.
