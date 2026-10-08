# Portable2 graphics CI prerequisite

Status: **SOURCE_ONLY_NOT_RUNTIME_ACCEPTANCE**. This derivative adds an honest
installed-package observation route to frozen `../network-graphics-ci-portable1`.
No graphics, JVM, game, package command, download, installation, CI dispatch,
network operation, CUA or host setting change was performed. No actual runner
inventory, graphics lock or runtime receipt is supplied.

## What changed

`graphics_preflight.py` accepts either of two explicitly different provenance
receipts in the existing lock field `package_provenance`:

- `OBSERVED_INSTALLED_PACKAGES`: actual Ubuntu 24.04 distribution, exact GitHub
  runner image and machine, installed package versions/architectures, per-file
  package ownership, and file SHA-256 values matching the independently reviewed
  lock pins. This mode makes **no claim of a verified archive/signature chain**
- `VERIFIED_UBUNTU_CLOSURE`: the existing signed Ubuntu snapshot/package receipt
  contract, unchanged. Use this label only when that chain was actually verified

An already-installed reputable Mesa/Xvfb on the actual official runner can use
observed provenance. A full signed APT closure is not a prerequisite for that
route. Both modes retain exact canonical executable/library paths and byte pins,
pre/post hash validation, the real process/display/GLX/llvmpipe observations,
loaded-library coverage, memory gates, and exact-owned-child cleanup.

The collector imports only the exactly pinned shared helper:
`../network-ci-supervisor-portable3/supervisor.py`, SHA-256
`01f3796c0d6e9c54a770375f0ae1cc3451a89074bb88934023f997f7c48dc1bf`.
Its verified source-manifest SHA-256 is
`6c94bfd342ef1faa97f42e88952df2a5f3c0b15da38e0ec56658523a9d6f2075`.
Frozen graphics portable1 remains unchanged. The collector uses the helper
without a preparation-root argument, retaining the existing graphics-input
permission checks.

## Producer interface

The existing CLI and lock schema are unchanged. `LOCK-CONTRACT.md` specifies the
observed receipt's exact keys. A future authorized producer on the **actual
GitHub Ubuntu 24.04 runner** records `/etc/os-release` identity, its real
`ImageOS`, `ImageVersion`, machine, installed package database versions and
architectures, and ownership of every canonical pinned file. Retain the raw
observations in the review evidence named by `observation_reference`; obtain
file hashes from the real files, not from package web pages or image manifests.
Record canonical file ownership even when a public executable or library name
is a symlink. Resolve any ambiguous/missing ownership before making the receipt.

The collector validates consistency, exact pins and the unchanged runtime
observations. It does not run a package manager, manufacture an inventory,
independently authenticate the package database, or establish .deb origins or
signatures for an observed receipt. A status string/reference is not proof that
the producer performed the observations; the reviewer must inspect the evidence.

Prepare the complete reviewed tool/library set for the target process and
client. Observed loaded paths must be a subset of that set; a short glxinfo
trace does not prove coverage of every possible future workload. Pin runtime
helpers/data as applicable. An unpinned loaded library remains a hard failure.
No package acquisition or installation is required solely to upgrade an honest
observation label to a signed-chain label.

`official-input-research.json` is copied historical acquisition research. Its
package-page candidates are not installed-runner observations and are not a
valid lock or signature proof. Its former signed-closure blocker does not apply
to the new observed-installed route.

## Existing runtime boundary

Default invocation with `--supervisor`, `--lock` and its independently reviewed
`--sha256` only validates static inputs. Runtime additionally needs
`--execute-reviewed-ci-preflight`, a fresh absolute `--destination`, actual
`GITHUB_ACTIONS=true`, and exact image/machine match. This remains the official
GitHub Ubuntu24 CI route. The Debian desktop/native existing-display route is
separate and remains memory-blocked; this change does not authorize it.

The unchanged collector starts one pinned Xvfb with its unused display,
`-screen 0 1280x720x24 -nolisten tcp -noreset`, and one native pinned
`glxinfo.x86_64-linux-gnu -B`. Its closed environment keeps the existing software
selectors and `LD_DEBUG=files`, with fresh private home/cache/config/data/temp
folders. It observes the exact Xvfb PID/start ticks/executable and owned live
DISPLAY socket, direct rendering, llvmpipe and OpenGL core >= 3.2, real mapped/
initialized files, Xvfb VmHWM, and exact glxinfo wait4 RSS/exit status.

Graphics reserve remains Xvfb VmHWM + glxinfo ru_maxrss + 256 MiB slack. The
shared memory gate still requires 3,758,096,384 bytes for the game pair plus that
reserve and uses host MemAvailable and applicable finite cgroup ancestor
headroom. Missing/ambiguous readings and competing JVMs still fail. No host or
cgroup settings change. glxinfo measurements do not represent the entire game.

The existing `graphics-preflight.json` consumer schema and 8192-byte bound,
`measurement.json`, `ready.json` and `lifecycle.json` are unchanged. The sealed
provenance receipt remains pinned in the runtime receipt, preserving its mode.
Success means graphics preflight readiness, never pair acceptance. The collector
must stay alive while serial consumers use its display and stops afterward.
Its existing bounds remain: 15-second startup, 30-second probe, 2,520-second total
lifetime, 1 MiB per log stream, and exact owned pidfd TERM/KILL cleanup. It never
signals imported receipt PIDs or by process name/group, or deletes an existing
X socket. Abrupt parent SIGKILL/machine failure and malicious root remain outside
the tested lifecycle guarantees.

## Verification

Run from this package:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_graphics_preflight.py test_installed_provenance.py
```

All 32 synthetic tests pass: 15 original tests plus 17 observed-provenance and
preservation tests. Test-wide guards reject native process launches. Coverage
includes both provenance modes, exact observed distribution/image, bounded
identity/reference fields, ownership/hash completeness and drift, prohibited
archive claims, and local-runtime rejection. Existing execution and cleanup
functions/classes remain AST-identical to portable1; the original 15 test
bodies remain unchanged. See `evidence/` and `source-manifest.json` for source
and test evidence. Synthetic passes establish no real graphics feasibility.
