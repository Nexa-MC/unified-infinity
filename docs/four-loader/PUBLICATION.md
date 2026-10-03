# Four-loader source publication

This update curates the frozen first bounded four-loader acceptance snapshot onto
the existing private repository history. It does not publish current successor
UI, admission-policy, host, preload or independent-public-API work.

## Fresh publication checks

- Original source archive size/SHA-256 and all 1,234 checkpoint manifest entries verified
- Accepted core binary was read only after its exact SHA-256 matched; its source
  identity was extracted without execution, and no runtime JAR is distributed
- All 390 accepted source/build records, 382 Java sources and 169 dependency records preserved
- Nine omitted API test helpers/licenses/results recovered verbatim from the
  archive-contained historical patch and verified against its source-delta digests
- 28 accepted host/provider source records verified; the provider's source and
  required product icon remain the previously verified M5/7b549d37 version
- 92 Python source files passed syntax parsing; 109 JSON files parsed at the
  checkpoint before adding this publication record
- The source verifier passes and rejects a missing-input negative control

`publication-validation.json` records exact counts, supplemental-file provenance
and evidence path normalization. These checks do not constitute a new Java/Gradle
build, Minecraft run, successor UI pass or performance result. Recorded real native,
combined-server and client results retain their original scopes and limitations.

## Frozen sources and useful reconstruction

The current core snapshot is `source-workspace/connector-four-loader/` and its
accepted identity is `accepted-build-identity-98d86a92.json`. The older M5 identity
and core26b patch remain labeled historical. Only the nine absent helper files
were recovered from that old patch; its whole predecessor source delta was not
replayed over the accepted98 source.

The combined-server controller depends on several older shared hopper/mixed-pack
helpers absent from the archive. Those exact helpers and fixture reports were
included only after their hashes matched the accepted retry2 control lock. No
unlocked current experiment was imported. See `REBUILD.md` for the required
ordinary upstream Git context, unbundled toolchains and separately acquired
original dependency/mod artifacts. A fresh-machine build was not claimed.

## Privacy and evidence curation

Raw process/environment inventories, launch argument/classpath dumps, PID/resource
records, gameplay logs, screenshots/GIFs, detailed saved-state projections, save
files, compiled runtime/game/mod archives and unrelated research were omitted.
Original product artwork and source-only archives required for corresponding-source
obligations remain. The accepted source/archive licenses and modification notices
are preserved rather than replaced by a project-wide license.

Ten selected JSON evidence files had only the private absolute project prefix
normalized to a project-relative path. The provenance record retains the original
and published file digests. Recorded hashes of original test reports remain
historical hashes; they are not claims that normalized copies are byte-identical.
References to omitted raw logs, media or detailed save projections are evidence
references, not bundled payloads. Compact saved-state verifier outcomes retain
original report digests without publishing the detailed saved-state projections.

The actual historical accepted runs inherited their process environment. A later
key-name-only audit identified an inheritance risk; minimal environment hardening
remains separate work. No secret values or secret-key inventory is published.
Passing functional tests is not OS sandboxing or proof of no access/transmission.

## Accepted limitations remain visible

The accepted preload has known 16:9 letterboxing and host-driven polling gaps.
The built-in mod list remains the ordinary 56-logical-record view, with no new
API grouping or compatibility-label presentation. Foundation/bridge exclusion
policy and the independent public API discussion are outside this publication.
No broader compatibility, physical-GPU or performance certification is implied.
