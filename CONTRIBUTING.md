# Contributing to Unified Infinity

Thanks for helping make compatibility claims reproducible. Small, focused
contributions with clear evidence are especially useful at this experimental stage.
English and Chinese issue reports are welcome.

## Before starting

1. Read [the current scope](README.md#current-status),
   [v6 acceptance limits](docs/fusion-v6/README.md) and [license scope](LICENSING.md).
2. Check existing issues and pull requests. Discuss large architecture changes,
   dependency upgrades and new public APIs before implementing them.
3. Base work on the intended branch and state that base revision. `diagnostic/*`
   branches are isolated experiments, not replacements for the accepted `main` baseline.
4. Keep unrelated refactors out of compatibility fixes. Preserve upstream copyright,
   license, source identity, original mod IDs and dependency semantics.

## Development setup

Use a disposable checkout with Python 3, Java 21 and Gradle 8.11.1. The historical
compiler was Java `21.0.12.1+1`; different inputs need a new recorded identity.
Read [REBUILD.md](docs/fusion-v6/REBUILD.md) and
[DEPENDENCY-RESTORATION.md](docs/fusion-v6/DEPENDENCY-RESTORATION.md) before a build.
The repository does not include all binary/generated prerequisites or the
executable Gradle wrapper JAR, and a clean-network build is not yet verified.

First run the read-only source check from the repository root:

```sh
python3 source-workspace/verify-fusion-source.py
```

For documentation-only changes this must continue to pass. When intentionally
changing a frozen source, a mismatch identifies the old baseline; do not rewrite
its hashes to pretend the new source was already accepted. Preserve the baseline
and supply separate candidate identity and verification evidence.

After restoring the exact pinned inputs, build and test the core:

```sh
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 fullJar
python3 source-workspace/gradle-build.py --four-loader --heap-mib 512 check
```

Additional targets and their prerequisites are in the rebuild guide. In
particular, product tests can invoke Java/Gradle; QSL structural and full core
checks need explicit original binary/derived fixtures. Report missing inputs as
blocked tests, not passes. Do not run inherited upstream publishing/upload tasks;
this fork is not authorized to publish to upstream project accounts.

## What to test

- Add a regression that fails before the fix and passes after it
- Preserve the original upstream mod/probe bytes; adaptations belong in this
  runtime unless a test explicitly concerns a changed mod
- Check descriptors, class origins, lifecycle order, dependency resolution and
  failure behavior when the change affects them
- For runtime compatibility, use an equivalent native-loader control and a
  bounded Unified run with exact versions, mod hashes, configuration and cache state
- For persistence changes, save, exit and reopen a copied test world; never use
  a valuable original world as a fixture
- For UI changes, inspect real rendering and interactions, including resize,
  reopen and relevant failure paths; a screenshot or headless assertion alone
  does not prove the interaction works
- For server/client or networking changes, distinguish each process and side;
  a client-only run cannot establish dedicated-server compatibility
- Keep resource limits, timeouts and cleanup explicit; native/game tests require
  their actual external prerequisites and a suitable environment

A green diagnostic job does not broaden support claims by itself. Record what
ran, what passed, what failed and what was not run, with exact artifact identities.

## Issues and pull requests

A useful bug report includes:

- Commit or branch, Minecraft/Java/loader versions, operating system and architecture
- Minimal original mod list with versions and, where available, SHA-256 hashes
- Exact reproduction steps, expected result and actual result
- A small redacted log excerpt, plus whether a native-loader control reproduces it

For a pull request, explain the problem, changed behavior, why the implementation
belongs in that layer, tests run and remaining limitations. Include dependency
and license impact when relevant. Open an incomplete contribution as a draft.
Update user-facing documentation when behavior changes.

Do not attach credentials, session tokens, private server addresses, account data,
raw environment dumps, personal worlds or redistributable-uncleared JARs. Prefer
public upstream coordinates and hashes over binary uploads. See [SECURITY.md](SECURITY.md)
for sensitive reports.

## Code, evidence and licensing

Follow the surrounding Java/Python/Gradle style. Keep changes easy to review and
avoid generated output, local absolute paths, large logs and compiled artifacts.
Retain source archives and existing notices needed for corresponding source;
source archives are not runtime binaries. Clearly label historical evidence.

Contribute only material you have the right to contribute. Original project
contributions use the LGPL-2.1-or-later terms described in [LICENSING.md](LICENSING.md); changes
to upstream-derived files remain under the applicable upstream terms. Do not
remove a header or substitute the root license for a component license. For copied
or adapted material, include the upstream URL, revision, license and modification
notice in the same change.

This guide does not introduce a copyright assignment, CLA or mandatory
`Signed-off-by`/DCO process. Contributors retain their copyrights. Any future
change to contribution terms must be stated explicitly rather than inferred
from an upstream project's separate contribution policy.

Be respectful, explain technical disagreements with evidence, and avoid personal
attacks. Please keep support expectations proportional to an experimental project.
