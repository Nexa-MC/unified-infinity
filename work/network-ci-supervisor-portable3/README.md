# Portable3 final bounded network-pair source candidate

Status: **SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE; runtime UNRUN**. Portable1 and
portable2 remain frozen and byte-identical. This candidate combines the reviewed
properties lifecycle correction with explicit admission of ordinary owned
preparation files and the existing JDK's manifest-recorded legal aliases.
No JVM/game/graphics/network/CI/Git/CUA execution, JDK copy or runtime-input chmod
was performed while preparing or testing this source.

## Final input contract

Use `schema: network-ci-pair-v2`. It retains the original fields and adds:

- `preparation_roots`: 1–64 distinct, nonoverlapping canonical absolute directories
  owned by the same ordinary nonroot runner. Their directory chains must use
  0700/0750/0755 modes and be actually readable/traversable. Both profiles and the
  pair-spec file must be contained in these reviewed roots
- `jdk_legal_links`: at most 1024 rows, each with exactly `path`, `link_text`,
  `resolved_path`, and `jdk_root`. Alias paths belong here, not in `inputs`

All ordinary owned `inputs` must lie within a preparation root. Each remains a
canonical regular file, singly linked, owned by the runner, and exactly pinned by
its original size/SHA-256. Supported modes are 0400/0440/0444, 0500/0550/0555,
0600/0640/0644, and 0700/0750/0755. Group/world write and special bits are rejected.
Actual read/execute access is required; an owner-write bit must correspond to
actual write access. No mode change is performed. Configs, JARs, receipts and the
JDK can retain their normal 0644/0755 modes. The pair spec itself uses this same
rule and retains its independently supplied `--sha256` at all three checks.
Files owned by someone else are rejected, including falsely declared ownership
or access. Existing root-owned system-package admission is unchanged outside
preparation roots. No ownership, security or permission setting is modified.

A legal alias must be an owned symlink beneath the exact command JDK's `legal/`
directory. The JDK root must also be an immutable tree. The manifest pins its
literal relative link text and canonical final target. Resolution must remain
inside that JDK's legal subtree at every hop; intermediate aliases must also be manifest rows;
cycles and chains exceeding eight links fail. The final target must be a regular
file with its exact byte pin in `inputs`. Every observed tree symlink must have
one manifest row. Executable/directory aliases, outside targets, changed text,
false target claims, omitted aliases and unpinned targets fail. This is a bounded
legal-notice exception, not a general symlink resolver or copy requirement.

Legacy `network-ci-pair-v1` remains supported with its original strict mode and
no-symlink admission. The new roots/links fields are accepted only in v2.

## Runtime file lifecycle

Before server launch, every original byte pin is required, then the verified
server.properties bytes are captured in memory. Before client launch and after
server stop, the same snapshot is compared with the observed decoded properties.
All keys and values remain locked. Equivalent Java-properties comments, order,
line endings, separators and escapes may differ. Added/removed keys, changed
safety or non-safety values, duplicate decoded keys, continuations, malformed
escapes and unsupported input fail. There is no default-insertion whitelist.
The complete 61-key seed uses native `initial-enabled-packs=vanilla` and Unified
`initial-enabled-packs=vanilla,fabric`; these are sealed producer values.

Fresh `server-properties-before-client.json` and
`server-properties-after-stop.json` receipts record exact before/after hex bytes,
size/SHA-256, unified diff, byte equality, semantic status, and changed key lists
when decoding succeeds. A rejected parse also retains observed bytes when its
bounded regular-file read succeeds. Receipts are exclusive writes. No runtime
rewrite becomes a new trusted baseline.

The one-pass adjacent-file audit established these integration choices:

- Keep config/defaultconfigs naturally writable, while retaining every original
  byte hash and the complete directory inventories
- Seed whitelist.json and ops.json using the reviewed exact schema serialization
  in local4, then retain their original byte pins. No JSON mutation exception
- Omit client options.txt from final supervisor `inputs`: the game may save its
  expanded options on exit. Retain its exact initial-byte provenance in the
  assembly/prestart role receipt. This is an explicit producer choice, not a
  generic mutable-file whitelist in the supervisor
- Worlds, logs and launch-home/cache directories remain runtime outputs. The
  original fresh-profile and saved-world evidence requirements remain unchanged

`result.json` keeps its original schema. Its immutable-input flag covers exact
pins except the separately verified server.properties serialization lifecycle.
Both property receipts are required evidence of that lifecycle's success.

## Verification and evidence

111 source-only Python tests pass. They include normal owned 0644/0755 files,
exact pre/post hashes, property escaping/diffs, changed safety and unknown keys,
unchanged mod/config/JSON pins, false ownership/access/write claims, unsafe modes,
hardlinks, roots/containment, actual legal aliases, outside targets, cycles,
depth bounds, changed link targets, missing manifest rows and legacy admission.

A read-only audit additionally checked all 462 distinct original file pins in
local4's four actual role launch seals using their existing modes: no failures.
The existing JDK has 249 regular files and 205 legal symlinks resolving to four
canonical legal targets. Its legal-link manifest validation passed. No zero-byte
JDK files, unsafe file/directory modes, extra hardlinks or unexpected owners were
found. These are source/input checks, not runtime or graphics acceptance.

The whole Pair class remains AST-identical to portable1 after normalizing exactly
five verification calls: the three properties checks and two pair-seal checks.
Actual memory, graphics, socket observation, probe, spawn, shutdown, signal and
cleanup paths are unchanged. The original thirty-test source file remains
byte-identical. AST checks preserve the rest of verify_spec outside v2 admission,
legal-tree inventory and the single properties dispatch.

```sh
cd /workspace/scratch/414822c1ef1a/mod-compat-runtime/work/network-ci-supervisor-portable3
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v test_supervisor test_portability test_control_serialization test_input_modes test_legal_links
```

Review `PAIR-SPEC.md`, `PROVENANCE.json`, `source-manifest.json`, and the files
under `evidence/`: synthetic-tests.txt, source-checks.json, actual-input-audit.json
and supervisor.diff. The manifest covers the complete frozen source candidate.

## Integration

Select this supervisor/source-manifest hash in the final producer. Generate a v2
pair spec under a declared preparation root and seal its original contents with
an independent digest. Retain the original pair schema fields and every genuine
probe build, official-source, actual graphics and resource prerequisite.

```sh
python /workspace/scratch/414822c1ef1a/mod-compat-runtime/work/network-ci-supervisor-portable3/supervisor.py \
  --spec /absolute/owned/preparation/pair-spec.json --sha256 ORIGINAL_PAIR_SPEC_SHA256
```

An already authorized runtime attempt additionally uses
`--execute-reviewed-ci-pair --destination /absolute/fresh/evidence-directory`.
This source candidate does not authorize execution or establish a successful
pair, GUI/tooltips, real EMI Fill Recipe, backpack rendering, performance or
loader-wide compatibility. Actual runtime evidence is still required.
