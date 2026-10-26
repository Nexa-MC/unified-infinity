# Same-root Forge core / probe compilation checkpoint

Unpublished preparation only. No new CI or JVM was started for this checkpoint.
The preceding approved CI 40184273253 / commit
1f30b7e922e1abf59648a2ee30c78b350dd21804 genuinely compiled the original Forge
@Mod probe and native driver; that result is not a runtime-ready bundle.

## Implementation boundary

`pipeline.execute(repo, consumer, deadline_monotonic, source_manifest_sha256)`
is the future approved CI call-in. It uses one fresh external consumer, original
355-file source validation, original public input locks and generated-output
checks. `strict_runtime_restore.py` is a separately reviewed orchestration layer:
only 404/410 may fall through another originally locked URL. Access denials,
hash mismatch, deadline and other errors stop immediately. It does not alter the
original downloader, locks, validators, source archives or their hashes.

Then `same_root.py` materializes precisely the seven-file Forge core delta from
the already compile-qualified source archive, retaining the untouched baseline
receipt as baseline evidence. `restore_core_inputs.py` restores the original
706 core inputs, four snapshot aliases, two QSL inputs and 116 FML input aliases.
Every copy is from this consumer and digest-checked; no historical build cache,
receipt or compiled output is transplanted.

A fresh owned Gradle compile generates a new producer receipt under
`<consumer>/evidence/`, with actual command, owner journal, source and toolchain
proofs. Exact core identity is required:
`346c02cb7e638f53c40f476e23ad56ff8939a57b94e43ca2f181651f45cf91a5`
(675 source records, 169 dependencies). The core-generated native compile JAR
must retain `6faad7d182a47d66ce28db569e9f4f475d9bf7bc4db452b9f3010b74c050008c`.
It is not interchangeable with the official runtime-exported JAR.

Both genuine probes are then compiled and bundled by the existing strict
`forge_probe_bundle.py` contract. All recursive configuration/source/JDK/owner
proof inputs must stay within the same consumer. No binary uploads occur here.

## Next approved run requirements

1. Recheck remote branch and zero existing queued/running jobs. Publish only on
   `diagnostic/network-pair-20261006-a` through the authorized lease protocol.
2. Add this directory as `work/forge-same-root`, preserving the existing
   `work/forge-play-compile-ci` and all 355 original manifest-pinned files.
3. Review a new fixed-round first-step anchor and one standard Ubuntu workflow
   entrypoint. Validate that anchor before passing an absolute monotonic deadline
   to `pipeline.execute`. Keep max 45 minutes, conservative one worker, explicit
   heaps, and at least 180 seconds cleanup reserve. A 35-minute job with the
   existing 5-minute cancellation reserve is a possible bounded shape; admission
   must fit the actual next round, not reuse today's timestamps.
4. Bind the reviewed `input-manifest.json` SHA in the entrypoint; include that
   entrypoint and anchor in the publication closure. No unanchored standalone CLI
   or runnable workflow is provided by this checkpoint.
5. Run the real pipeline. Local data-only tests do **not** establish this new
   combined pipeline's compile success. Capture text proofs, not game/toolchain
   JARs; stop immediately on denied access.

## Remaining gate before Forge PLAY runtime

Even successful core + probe compilation is **not** full runtime packaging.
The old refreshed profile fixes a different core identity (`8f53a44...`) and
requires full core/product/FML packaging receipts. Do not attach the new compile
producer to it or rewrite historical receipts. A separately reviewed Forge
candidate profile must bind the same fresh core identity, producer receipt and
actual packaged artifacts across assembly and probe bundle, then validate the
actual launch classpath/artifacts before a client/server pair may be accepted.
All this checkpoint's runtime/full-API acceptance flags remain false.
