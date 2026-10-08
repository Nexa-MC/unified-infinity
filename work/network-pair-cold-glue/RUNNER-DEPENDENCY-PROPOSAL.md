# Ubuntu graphics dependency closure proposal

Status: SOURCE_PREPARED_INSTALL_AND_RUNTIME_UNTESTED. Another installation/CI run requires review of this expanded dependency scope.

Run37756576015 on Ubuntu24 image20260927.320.1 stopped before any package download, installation, JVM or game. It found missing mesa-utils-bin plus libdecor-0-0, libegl1, libgles2 and libxkbcommon-x11-0. This is runner preparation evidence, not a loader/API failure. Earlier source/mock checks verified control flow and pins; they could not establish a future runner image's installed package inventory.

## Exact permitted additions

At most these seven packages may be added. Their combined download bound is390800 bytes. Only packages absent from the current actual package state are selected. Installed packages are not upgraded, downgraded, removed or reinstalled.

| Package | Version | Bytes | SHA256 |
|---|---|---:|---|
| libdecor-0-0 | 0.2.2-1build2 | 16508 | 64bf085d16e504e9ed39b91d2a46748fb8881ad7f3603fbacef6c11c04aa7064 |
| libegl-mesa0 | 25.2.8-0ubuntu0.24.04.2 | 117222 | 8ccb85abbc76d53d47d952c975c5630bf305244a2af20e2b262725d1378d73c1 |
| libegl1 | 1.7.0-1build1 | 28670 | e549f7776216f7bd3b1c216729fb40a97a562e2eb7c563cde632b4931f9a4e57 |
| libgles2 | 1.7.0-1build1 | 17122 | 9dec2d79a2eebb80522f7cce77995f7a8ded22f0e3916f13353d066c62f97fac |
| libxcb-xkb1 | 1.15-1ubuntu2 | 32302 | 53bc0a58834c981fa8ce5c3ab6195387e5c8a417039d82cc7a8b49724fa53228 |
| libxkbcommon-x11-0 | 1.6.0-1build1 | 14536 | 3befe840ce612ddfc0998d8610c6eed295726722a78e75cd08520bbd75065a23 |
| mesa-utils-bin | 9.0.0-2 | 164440 | d64539eb18416708948d7857506946a024637e4c6147d91a28a42868e038cb00 |

The two conditional additions are libegl-mesa0 and libxcb-xkb1. Exact official package URLs and source metadata URLs are in ubuntu-graphics-candidates.json. The same seven full Debian records are preserved in ubuntu-graphics.Packages. No package binary is stored in the source stage.

The matching Mesa EGL provider is25.2.8-0ubuntu0.24.04.2 from noble-security. It requires libgbm1 and mesa-libgallium at that same version. The observed runner had the.2 DRI family; newer noble-updates.4 must not silently upgrade its companions. An incompatible actual installed family is an aggregate preflight failure. libxcb-shm0 is also checked through actual dependencies; its presence is not inferred merely from the runner label.

## Whole-state check and bounded future installation

1. Record current runner identity and the complete actual dpkg status; retain a digest and the original package/version/state records. Keep the existing trusted Xvfb/Mesa/graphics-tool checks.
2. Run native APT in simulation/check mode against that copied actual status, with source lists disabled and private empty cache/list paths. It does not fetch metadata, install packages or alter system sources/settings. A broken existing package state stops the task.
3. Append status records only for missing packages from the seven exact permitted stanzas. Run the same APT dependency check against the proposed complete state. This checks actual dependency versions and conflicts, including all transitive dependencies and installed alternatives. Any unsatisfied dependency outside the bounded additions is reported before downloading packages. No private dependency solver or signature-relaxation option is needed.
4. After explicit closure-install authorization, fetch every selected DEB only from its exact official HTTPS URL. Verify size/SHA256 and package control fields. Recheck that the actual package state did not change while preparing the plan.
5. Run one bounded dpkg command over the entire verified missing set. The existing root timeout and record-only owned-process cleanup semantics remain. Recheck actual package state, complete APT consistency, package ownership and graphics paths afterward, then continue the unchanged cold runtime pipeline.

Setup has a180-second limit within the existing42-minute work deadline. The job remains one standard ubuntu-24.04 job capped45 minutes. The explicit workflow/driver option becomes --install-reviewed-runner-closure; the old single-package option does not authorize this larger set. No package installation, third CI run or remote Git write occurred while preparing this source.

## Metadata provenance and limits

Official metadata supplies a complete59-package/172-edge reference closure in ubuntu-graphics-reference.json. This is explanatory metadata, not an instruction to install or downgrade59 packages. Only nine of those package versions were observed in the terminated runner's partial log; the actual full state must be checked again.

All six official compressed package indexes matched their suite Release SHA256 entries, and Release text matched InRelease content. Signatures were not independently verified, so this proposal does not claim a complete signed trust chain. The seven package URLs returned HEAD200 with their indexed lengths; no DEB body has been downloaded or executed here. Exact body validation remains mandatory in a future authorized run.

Primary sources:

- https://archive.ubuntu.com/ubuntu/dists/noble/Release
- https://archive.ubuntu.com/ubuntu/dists/noble-security/Release
- https://packages.ubuntu.com/noble/mesa-utils-bin
- https://packages.ubuntu.com/noble/libegl1
- https://packages.ubuntu.com/noble-security/libegl-mesa0
- https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html

The accepted ce4 FML/probe0.1.1 identities, original mod inventory, game arguments, graphics validation, memory gates and nonce/cleanup assertions are unchanged. No new Forge PLAY or API feature is included.
