# Conditional Ubuntu glxinfo setup proposal

Status: SOURCE_PREPARED_INSTALL_AND_RUNTIME_UNTESTED. This proposal is awaiting
review of the changed dependency-install scope. It has not been published or run.

The frozen first publication was commit
789620d07ebfe3725a998bcd20d9b7f13ca22dc1, tree
4870e8ceeaf563f29039cba700b72e17a2019519, with 143 payload files plus its
manifest (144 total). Its manifest SHA256 is
1ed3aefa877323f252e23d60bb9f0234909d0671770991f74489db0eb0302de0.
Run https://github.com/Nexa-MC/unified-infinity/actions/runs/37742488802
failed at the early availability check on Ubuntu runner image 20261004.327.1,
before dependency restoration, Java, graphics, or either game process started.
Only /usr/bin/glxinfo was reported absent; the canonical binary was not checked.

## Proposed repair and exact installation scope

Ubuntu's mesa-utils-bin owns /usr/bin/glxinfo.x86_64-linux-gnu; mesa-utils supplies
the /usr/bin/glxinfo alias. Use the canonical binary already expected by the
unchanged later package-owner and graphics checks. Do not create an alias.

Before other downloads, inventory all original mandatory graphics paths and
the installed xvfb, libgl1-mesa-dri, dpkg and libc-bin packages. Inventory every
declared mesa-utils-bin dependency together: libc6 >=2.38, libdecor-0-0 >=0.1.0,
libegl1, libgl1, libgles2, libvulkan1 >=1.2.131.2, libwayland-client0 >=1.20.0,
libwayland-egl1 >=1.15.0, libx11-6, libxcb1, libxkbcommon-x11-0 >=0.5.0, and
libxkbcommon0 >=0.5.0. Installed architectures must be amd64 or all.

If the canonical executable is already trusted and owned by an installed
mesa-utils-bin package, no download or installation occurs. If both executable
and package are absent, the explicit --install-reviewed-runner-package flag
permits only this exact package, and only if all prerequisites are satisfied:

- Package: mesa-utils-bin 9.0.0-2, amd64
- URL: https://archive.ubuntu.com/ubuntu/pool/universe/m/mesa-demos/mesa-utils-bin_9.0.0-2_amd64.deb
- Bytes: 164440
- SHA256: d64539eb18416708948d7857506946a024637e4c6147d91a28a42868e038cb00
- Recheck size/hash, then dpkg-deb Package/Version/Architecture before install
- Install with sudo -n timeout --signal=TERM --kill-after=5s 60s dpkg --install
  on the verified local file; the actual limit is shortened if necessary
- Recheck installed identity, canonical ownership and prerequisites afterward

No automatic dependency resolution, apt update, repositories, package upgrades,
Mesa driver changes, new package set, or package-signature-chain claim is added.
Missing dependencies are reported together and stop before downloading this
package. An installed package with a missing or untrusted executable is a
separate integrity/repair issue and is not automatically reinstalled.

Setup is capped at 120 seconds within the same existing 42-minute work deadline.
The root-owned timeout also owns dpkg, and interruption waits for that bounded
child before driver cleanup. The job remains 45 minutes on one standard
ubuntu-24.04 runner with read-only contents permission, no secrets, caches or
uploaded artifacts. Existing exact branch trigger and all other frozen
build/probe/runtime code remain unchanged. A new run requires review of this
successor; preparation does not authorize publication.

## Other prerequisites and honest limits

The first run established only trusted path presence for Xvfb, swrast_dri.so,
libGLX_mesa.so.0, dpkg-query, ldd and the package database. It did not establish
their later installed-package ownership, recognized ELF/dependency closure,
actual GLX renderer, or runtime-loaded library closure. Those existing checks
remain required and unchanged. No evidence currently justifies installing
xauth, xkbcomp, fonts, alternate drivers, or additional graphics packages.

Other frozen runtime gates still require Linux /proc identity/network/maps/fd
evidence; /proc/meminfo and applicable ancestor cgroup memory readings;
unprivileged identity with no capabilities; pidfd and libc prctl support;
unused display :97; and at least 3840 MiB eligible memory with no competing JVM.
Python requires tomllib, hashlib.file_digest and supported tar extraction
filters. Java and Gradle come from the existing pinned restoration locks.
The installed image cannot be inferred completely from its public tool list.
Image 20261004.327.1 is historical evidence, not a guarantee that a future
ubuntu-24.04 job selects that exact image. Actual ImageVersion is recorded again.

Source/mock tests validate this proposal's decisions, byte gates, command bounds
and cancellation waiting. They do not establish download availability, package
installation success, native graphics, cold build or host nonce acceptance.

## Primary sources

- https://packages.ubuntu.com/noble/amd64/mesa-utils-bin/filelist
- https://packages.ubuntu.com/noble/amd64/mesa-utils/filelist
- https://packages.ubuntu.com/en/noble/mesa-utils-bin
- https://packages.ubuntu.com/en/noble/amd64/mesa-utils-bin/download
- https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20261004.327
- https://github.com/actions/runner-images/blob/e3fe113a581eb9a44ca43f479b69f9c93f36df34/images/ubuntu/Ubuntu2404-Readme.md

The official package hash also matches the pre-existing frozen
work/network-graphics-ci-portable2/official-input-research.json record.
