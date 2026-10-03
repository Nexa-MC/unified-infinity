# Native Quilt API slice verification

This directory verifies a bounded Loader API **view over FFLoader**, not a second
Quilt Loader engine. Run `./four-loader/api-tests/run.sh` from this checkout.
No game launch, downloaded QSL execution, network, or mod publication occurs.

- Java 21 standalone compilation of every supplied API/bridge class
- Public signatures and JVM descriptors of 37 supplied API classes (including
  nested public types) compared to the pinned, SHA-verified Loader 0.30.1 JAR
- Behavior fixture compiled with the **original upstream API first** on its
  compilation classpath, then executed against this implementation and a test-only
  FFLoader host stub. The upstream Quilt engine is absent from the runtime classpath
- Original `quilt.mod.json` ID/group/raw version, license details, contributor
  roles, contact/icon data and complete immutable root values
- Source archive path separate from transformed resource root; native source type
  and existing host classloader identity, pinned at lifecycle dispatch to prevent
  later worker-thread context changes from altering the container view
- Managed embedded source-chain precedence: physical host archive followed by its
  relative nested payload path, preserving the separately recorded verified
  extraction path and admitted runtime root without opening archives
- Native and normalized ID lookup, builtin compatibility-provider view, actual host
  mappings/environment/directories, exact dependency alternatives and ranges
- Lazy provider-aware entrypoint adaptation, arbitrary QSL event keys, once-only
  dispatch, source-aware aggregate failures, failed-stage non-replay

## Source and license provenance

Public API declarations and independent metadata/version value algorithms are
adapted from `org.quiltmc:quilt-loader:0.30.1`, source tag
`b33861b30a815f327652015018d2d1262f12b63a`.
Binary SHA-256: `a561a9fe9abb45556c696095a29e81477618bf2408b86c36db5aecdcd6a86fdb`.
Sources SHA-256: `66d1b1214179306574b730f0841a63d9499d47d1ea16b912ef336f6a2c62a08a`.
Original FabricMC/QuiltMC copyright notices remain in source. The Apache 2.0
license is preserved in `LICENSE-quilt-loader.txt`; include that license with
redistributed runtime artifacts containing these adapted classes.

API static factory implementation imports now target
`org.sinytra.connector.quilt.metadata`; Quilt engine, discovery, solver, Mixin
bootstrap, plugin system and classloader implementations are not copied.
`QuiltLoader`, `MinecraftQuiltLoader`, `EntrypointUtil` and `LanguageAdapter`
delegate to this host. The standalone upstream range helper was corrected to
preserve union upper bounds, merge closed touching endpoints, preserve legacy
lower-bound inclusivity, and prevent mutation of shared ANY/NONE. Contributor
roles are defensively copied. These are source changes, not claims of exact
internal implementation identity.

The bounded SPDX lookup uses exact name/id/reference values from the pinned
binary's `quilt_loader/licenses.json` for Apache-2.0, MIT, LGPL-3.0-only,
LGPL-3.0-or-later, and CC0-1.0. Other identifiers follow the public unknown-license
null/default contract. Original custom license objects retain their full values.

## Intentional limits

This is `native-quilt-v1`, not complete Loader 0.30.1 behavior. The builtin
`quilt_loader` descriptor explicitly names the compatibility profile. No owned
`org.quiltmc.qsl` definitions are added; the host separately bundles pinned original
QSL modules and owns their activation.

- Only the supplied public API types are provided; plugin/GUI/config/filesystem
  APIs are outside this slice
- Distinct non-SemVer ordering explicitly throws, because the external FlexVer
  implementation is not bundled. Raw identity and semantic comparison work
- Admitted dependencies are limited by the parser to flat semantic comparators
  and alternatives; the view does not grant wider solver support
- Global Quilt config/cache directories explicitly throw; the game cache maps to
  the existing game `.cache` directory. Global directory mode is false
- The synthetic builtin API provider has no independent resource root and reports
  that explicitly if requested; its classloader is null per upstream builtin ABI
- JSON-path locations are preserved for values; original line/column offsets are
  not invented after projection
- Class-to-mod lookup is best effort using actual code source, returning empty
  when it cannot establish provenance

`behavior-result.txt` (60 assertions), `abi-result.json` (37 API types), and
`qsl-linkage-result.json` (all Quilt API owners referenced by original pinned
base/lifecycle JARs supplied) describe focused checks. They do not
prove actual FML admission, QSL lifecycle timing, game execution, cold/warm cache
behavior, or third-party mod compatibility.
