# Consumer-generated pair seal contract

This document defines the final source candidate input contract. It is not a
runnable example, approval token, generated launch seal, or runtime evidence.
Actual probe-build, producer and graphics receipts remain separate prerequisites.

The CLI requires an absolute `--spec` path and independent exact `--sha256`.
The JSON spec must be a regular file, at most 8 MiB, without duplicate
keys or nonfinite numbers. All paths are canonical absolute consumer-local paths
without symlinks or `..`. Default mode only validates static files and explicitly
reports `passed: false`, `runtime_evidence_observed: false`. The separately
reviewed runtime path additionally requires `--execute-reviewed-ci-pair` and a
fresh absolute local `--destination`. A flag alone is not user authorization.

The top-level object has exactly these keys:

| Key | Contract |
| --- | --- |
| `schema` | `network-ci-pair-v2` for the final candidate; legacy v1 remains supported under its strict admission rules |
| `target` | `native-neoforge` or `unified` |
| `port` | Respectively 25631 or 25632 |
| `authorization` | Exactly `offline_identity_reference`, `eula_reference`, `ci_pair_review_reference`, each a nonempty bounded reference to actual existing approval |
| `inputs` | 1–16000 unique pins, each exactly `path`, positive integer `bytes`, lowercase 64-digit `sha256`; v2 owned files use the explicit preparation-root rules below; legacy read-only and exact-reviewed root-owned system-file rules remain otherwise unchanged; size/hash checked before and after except the narrowly documented server.properties lifecycle below |
| `immutable_trees` | Nonempty list of complete directories. Every regular file beneath each must be pinned; only v2 manifest-recorded contained JDK legal-file aliases are excepted from the no-symlink rule. Include full JDK, mods, config/defaultconfigs, assets, native-library directories and every directory classpath |
| `probe_path` | Exact built source-owned JAR, present in `inputs`; identical bytes copied into both profiles |
| `probe_source_manifest` | Pinned original probe `source-manifest.json`, with schema 1 and status `SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE`. Every listed relative source path/hash/size must match `inputs`; includes `protocol-schema.json` and `build.gradle` |
| `probe_build_receipt` | Pinned future build receipt described below, binding the unchanged source manifest to exact JAR bytes |
| `source_receipts` | At least two separately pinned producer receipts for official native/portable preparation and assembly. Producer review must establish genuine official derivation, source closure and launcher identity; the supervisor never reruns producer code |
| `graphics` | Exact object described below, generated from actual reviewed Xvfb/GL preflight |
| `server`, `client` | Exact role objects described below |
| `pair_lock` | Canonical absolute shared lock path, with existing parent. Native and Unified must use this same reviewed path in the serial job |

The probe build receipt has exactly: `schema: 1`, `status: "BUILT"`,
`source_manifest_sha256`, `artifact_path`, `artifact_sha256`, `artifact_bytes`.
All four identity values must exactly match the associated input pins. This
receipt must come from a successful separately authorized build; its existence
alone never constitutes runtime acceptance.

Each role object has exactly `cwd`, `command`, `environment`, `original_mods`,
`managed_mods`. CWD is a distinct fresh disposable existing profile; world and all
four fixed probe filenames must be absent at runtime preflight. `command` is the
literal expanded argv, directly starting its pinned JDK `bin/java`. No shell,
wrapper, implicit/wildcard classpath, unexpanded `@argfile`, injected Java agent,
external VM option file, alternate max-heap setting or credentialed client is
accepted. Retain exactly `-Xmx1280m` and `-XX:ActiveProcessorCount=2`. Producer
expansion must preserve the official launcher semantics; the supervisor cannot
infer a launch recipe from metadata names.

Class/module path entries must individually resolve to pinned files or complete
immutable directories. `-Djava.library.path` directories must be immutable trees.
Both profiles' `mods` directory inventories must match exactly three pinned
original real mods, the identical probe, plus explicit source-owned managed mods
for Unified only. Original EMI/Backpacks/Core names and hashes are fixed to the
current preparation pins. `config/neoforge-server.toml` and
`defaultconfigs/neoforge-server.toml` must be pinned with LAN advertisement false.
Additional config files are covered by the complete directory inventories.

The server requires `nogui`, loopback/assigned port, offline APILocal controls,
one entry enforced whitelist, empty ops, existing authorized `eula=true`, disabled
RCON/query/status/secure-profile, maximum one player and `level-name=world`.
The client requires exactly one each of `--username APILocal`, `--uuid` with the
fixed offline UUID, `--quickPlayMultiplayer 127.0.0.1:<assigned port>`,
`--accessToken 0`, `--gameDir <cwd>`, and pinned official `--assetsDir` /
`--assetIndex`. No real credential or account login is used.

Each `environment` is a complete object, never merged with the supervisor's
environment. Required exact fields are `JAVA_HOME`, fixed JDK plus
`/usr/bin:/bin` PATH, `LANG=C.UTF-8`, `TZ=UTC`, `DISPLAY`,
`LIBGL_ALWAYS_SOFTWARE=true`, `GALLIUM_DRIVER=llvmpipe`, and private profile-local
`HOME=.launch-home`, `XDG_CACHE_HOME=.launch-cache`,
`XDG_CONFIG_HOME=.launch-config`, `XDG_DATA_HOME=.launch-data`,
`TMPDIR=.launch-tmp` (all values expanded to absolute paths). Optional allowed
fields are `LC_ALL`, local `XAUTHORITY`, and `__GLX_VENDOR_LIBRARY_NAME=mesa`.
No other environment field is accepted. Xauthority contents are not read or
copied into logs or receipts.

`graphics` has exactly `display` (literal `:<integer>`), `pid`, `start_ticks`,
`executable` (pinned Xvfb), `preflight` (pinned actual measurement JSON), and
`reserve_bytes` (integer ≥268435456). Xvfb must already be running with this
display and `-nolisten tcp`; actual process executable inode and owned Unix
display socket are verified. It stays outside the two game process groups and
is never stopped by this runner.

The graphics preflight has exactly `schema: 1`, `display`, `xvfb_pid`,
`xvfb_start_ticks`, `renderer`, `direct_rendering: true`, `glx_capable: true`,
positive `gl_probe_peak_rss_bytes`, `measured_headroom_bytes` ≥268435456, and
nonempty `input_sha256` map. Xvfb/display identities must match actual observation;
renderer must be measured llvmpipe; each tool/library identity in the map must
match `inputs`. Review must establish the preflight's actual command, pinned
graphics closure and native measurement; no hand-written placeholder qualifies.
The reserve is the maximum of requested reserve, measured headroom and actual
Xvfb RSS plus measured GL-probe peak RSS.

The spec is an explicitly reviewed trust input. Read-only modes and pre/post
hashes detect ordinary changes; they do not defend against a malicious root
process altering and restoring files. The runtime sources remain external
prerequisites and no hostile-code containment claim is made.

## Legacy v1 portable admission

For v1, the JSON pair seal itself and user-owned preparation inputs still require their
original read-only modes. Only exact-pinned standard root-owned 0644/0755 system
files may retain owner-write bits, with the ordinary nonroot runner identity and
actual kernel read/write access checks specified in README. Reviewed source and
package/file provenance remains required; a matching hash alone is not proof of
an official package. No pair-schema or receipt-schema field was added.

Memory admission accepts actual VM MemAvailable when no finite cgroup-v2 bound
applies. Any visible finite ancestor tightens the available budget. The report
records all available measurements and the selected minimum. Resource evidence
must be readable, unambiguous and complete for the applicable hierarchy. The
3,758,096,384-byte aggregate reservation plus measured graphics reserve is
unchanged. This source package is runtime UNRUN.

## Portable2 server.properties lifecycle

The pair schema and sealed input rows do not change. Static CLI validation and
the last verification before server spawn still require every original byte pin.
The runner captures the original server.properties bytes after the complete
prestart verification and checks their hash and length against the original pin
once more. Both existing post-start verify_spec invocations use this captured
baseline: before client spawn and after the server exits.

Only the exact path `<server.cwd>/server.properties` has a lifecycle exception.
It retains regular-file and canonical-path rules and the selected schema
version's explicit ownership/mode admission. It may not itself be a symlink. Every decoded key/value must equal the captured original. No key addition,
removal, changed default, target pack change or safety-value change is permitted.
All other inputs, including whitelist.json, ops.json and eula.txt, retain their
exact original byte pins.

The producer must seed the complete accepted key set before review/sealing. The
reviewed local4 seeds contain the accepted 61 keys, with preparation's fixture
overlays. `initial-enabled-packs` is `vanilla` for native and `vanilla,fabric` for
Unified. No defaults whitelist is built into the supervisor. This target choice
is a sealed producer value, never an inferred runtime normalization.

The restricted ASCII Java-properties decoder accepts comments, line endings,
separator whitespace, property ordering and Java escape sequences (including
`minecraft\:flat` versus `minecraft:flat`). It rejects duplicate decoded keys,
continuations, malformed Unicode escapes, raw control bytes and unsupported keys.
Trailing and escaped leading value whitespace remain semantically significant.

Fresh `server-properties-before-client.json` and
`server-properties-after-stop.json` receipts include the original and observed
SHA-256/length/exact hex bytes, a displayable unified diff, changed/added/removed
keys when parsing succeeds, and `SEMANTICS_PRESERVED` or `REJECTED`. The receipt
can reject even a known default being added. A rejected parse still records its
observed bytes when the regular bounded read succeeded. Receipt creation is
exclusive, never an overwrite. The existing result flag
`immutable_inputs_unchanged` covers the exact immutable pins; this property
lifecycle is separately established by the two receipts.

Existing production whitelist/ops are compact empty JSON without a newline;
prepared controls include a newline and an APILocal whitelist. That difference
alone does not prove an automatic rewrite of an identical whitelist. A runtime
serialization change to either JSON control remains a fail-closed byte-pin
error and needs separate evidence/review before any exception is considered.

## V2 explicit owned inputs and legal aliases

V2 requires two additional top-level fields, and no other new fields:

- `preparation_roots`: a list of 1–64 canonical absolute directory strings,
  explicitly reviewed, distinct and nonoverlapping. Each root and directory chain
  beneath it must be runner-owned, mode 0700/0750/0755, and actually readable and
  traversable. Both profiles and the pair-spec file must be within these roots.
- `jdk_legal_links`: a list of at most 1024 objects, each with exactly `path`,
  `link_text`, `resolved_path`, and `jdk_root`, all strings. Empty is valid for a
  JDK without aliases. Include every alias in the complete JDK tree.

Each ordinary owned input must lie in a preparation root and remain a canonical,
regular, singly linked file with the same runner UID. Permitted modes are
0400/0440/0444, 0500/0550/0555, 0600/0640/0644, and 0700/0750/0755. Actual read and,
when executable, execute access is required. If the owner-write bit is set,
actual write access must agree. Group/world write, set-ID or other special bits,
false ownership and access claims fail. Original byte sizes/hashes remain exact
at prestart and both later checks except the single documented properties
serialization lifecycle. This applies to config files, JARs, receipts and JDK
files alike without chmod/copies. Root-owned system files outside preparation
roots retain the unchanged previous package-provenance/access rule.

The pair-spec JSON itself may retain a normal owned mode in a declared root.
Its independent CLI digest is checked on entry and at both run boundaries. V1
continues to require the original read-only pair-spec mode. No v2 mode exception
is inferred merely from a pathname or matching hash without declared roots.

For a legal-link row, `path` is an owned symlink file below `jdk_root/legal`;
`jdk_root` equals the root of an actual sealed command JDK and appears in
`immutable_trees`. `link_text` is the exact literal bounded relative text from
readlink (maximum 4096 characters). `resolved_path` is the canonical regular
final target within that same JDK's legal subtree and must have its byte pin in `inputs`. The
alias itself is in `jdk_legal_links` only, never `inputs`. Every intermediate
alias must be manifest-recorded; every resolution hop stays within the JDK legal subtree;
cycles and chains longer than eight links fail. All observed tree symlinks must
match this complete manifest. Executable/directory aliases and other symlinks
are not admitted. The existing 205 official JDK legal aliases fit this contract.

Producer lifecycle exclusions are explicit: client options.txt is omitted from
final immutable supervisor inputs while its original bytes remain bound by the
assembly/prestart role receipt. The file is not under a required immutable
config tree. No general mutable-file list was added. Whitelist/ops use the
reviewed local4 exact schema serialization and remain exact byte pins; all
config/defaultconfigs files retain exact hashes and complete inventory checks.
