# Reviewed graphics input contract

No actual lock or provenance receipt is included. Synthetic test fixtures and
historical acquisition research are not runtime inputs. Placeholder hashes,
renderers, PIDs or measurements are never accepted as real observations.

The CLI is unchanged: absolute `--supervisor`, absolute `--lock`, and its
independently reviewed exact `--sha256`. Runtime additionally needs the existing
CI flag/destination. The helper must match the collector's exact source pin.
The read-only regular lock is at most 1 MiB, with no duplicate JSON keys,
nonfinite numbers, symlink paths or unrecognized fields. Its exact keys:

- `schema`: `network-graphics-lock-v1`
- `status`: `COMPLETE_REVIEWED`
- `review_reference`: nonempty reference to real review, at most 512 characters
- `expected_runner`: exactly `ImageOS` = `ubuntu24`, exact `ImageVersion`
  matching `YYYYMMDD.<integer>.<integer>`, `machine` = `x86_64`
- `display`: unused local `:<integer>`, at most five digits
- `tools`: exactly `xvfb` and `glxinfo`, canonical absolute executable paths with
  basenames `Xvfb` and `glxinfo.x86_64-linux-gnu`
- `inputs`: 3–128 unique pins, each exactly `path`, positive `bytes`, lowercase
  SHA-256 `sha256`; every path and byte/hash must pass the shared helper checks
- `package_provenance`: path already present in `inputs`, containing one of the
  following reviewed producer receipts

## Observed installed packages

Use for already-installed packages on the actual official GitHub Ubuntu24
runner. Exact receipt keys:

- `schema`: 1
- `status`: `OBSERVED_INSTALLED_PACKAGES`
- `observation_reference`: nonempty reference, at most 512 characters, to the
  retained actual runner/distribution/package/ownership/hash observations
- `distribution`: exactly `id` = `ubuntu`, `version_id` = `24.04`, read on target
- `runner`: exactly the same three fields and values as `expected_runner`,
  observed on that target rather than copied from a moving runner label
- `packages`: 3–256 installed package rows, each exactly `package`, `version`,
  `architecture` (`amd64` or `all`); include `xvfb`, `mesa-utils-bin`,
  `libgl1-mesa-dri` and other owners of the pinned inputs
- `file_packages`: map every pinned file except this receipt to its observed
  exact owner identity `package:architecture=version`; Xvfb/glxinfo must map to
  `xvfb`/`mesa-utils-bin`, respectively
- `file_sha256`: map the identical file set to each actual file's lowercase
  SHA-256; every value must equal its separately reviewed `inputs` pin

Versions are bounded to 128 characters and Debian version characters. Duplicate
package identities, incomplete/extra file mappings, unknown owners and wrong
hashes fail. All ordinary path/mode/hash checks remain in force. Observed rows
have no `.deb` URL/hash, snapshot or signature fields; those fields are rejected
rather than implying a verified chain. The status records observations only.

The separate producer records target `/etc/os-release`, actual runner image,
installed-package database identity and canonical per-file ownership, hashes and
review evidence. The collector checks the receipt and exact inputs; it does not
independently run dpkg or verify distribution signatures. Authenticity/accuracy
of the producer's observations is established by review, not by a label. This
route does not require reconstructing a signed APT closure and never upgrades
package-database observations to archive-chain verification.

## Verified signed Ubuntu closure (existing optional route)

Exact receipt keys remain `schema` = 1, `status` = `VERIFIED_UBUNTU_CLOSURE`,
UTC `snapshot` matching `YYYYMMDDTHHMMSSZ`, bounded nonempty
`signed_index_review_reference`, `packages`, and `file_packages`.

Each of its 3–256 rows has exactly `package`, `version`, `architecture` (`amd64`
or `all`), official snapshot `.deb` `uri` under that snapshot's `/pool/`, positive
`bytes`, lowercase `sha256`. Include the required Xvfb/GLX/Mesa package identities
and reviewed dependencies/runtime inputs. `file_packages` maps all pinned files
except the receipt to `package:architecture=version`, with the proper tool owners.
The producer must actually verify the signature/index/package/file chain before
using this status. The collector's syntax checks cannot establish that chain.

## Shared downstream contract

Every provenance receipt is independently byte-pinned with all runtime inputs.
The collector revalidates those original pins after graphics execution. Actual
loaded paths must be pinned. Neither a package inventory nor a short native
trace alone establishes every possible runtime dependency; preparation/review
must include the needed tools/libraries/helpers/data for the intended workload.

The future pair seal also pins the actual graphics receipt and every entry of
its `input_sha256` map. Its frozen 8192-byte bound, canonical file identities and
shared helper permission rules are unchanged. Root-owned standard package modes
pass only the helper's actual nonroot access and ancestor checks; other input
modes follow the selected helper contract. No permissions are changed here.

`ready.json` is emitted only after genuine process/display/renderer/memory
observations and the unchanged graphics validator pass. Raw measurements and
loader logs remain reviewable. No static validation result, observation label or
source checkpoint provides CI dispatch authority or successful pair acceptance.
