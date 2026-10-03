# Empty-prerelease and OP Tab metadata regression

`optab-2.0.0V1.21.1+1.21.quilt.mod.json` is the exact, unmodified
`quilt.mod.json` entry extracted from the approved OP Tab archive. It is test
input only; no OP Tab classes are on the test classpath or executed.

- Official download: https://cdn.modrinth.com/data/JqlHhgpT/versions/tcJK6pdC/optab-2.0.0V1.21.1%2B1.21.jar
- Archive SHA-256: `6121446645d4521ddb5deae40e506fb02a7d4f06c0ce049fabc6ecaed548c296`
- Descriptor SHA-256: `4c874ddde93bf8dce82d1e482a3a5280f96970ccf934a8b988818d39f55d7d3f`

`NativeQuiltRegression` includes the metadata and predicate assertions on every
run. Its single FFLoader resolver tests retain missing dependency and
`>=0.31.0` negatives, and add `>=0.31.0-` rejection plus `>=0.16.0-` admission.

For a differential audit, invoke `NativeQuiltPrereleaseRegression` with the
transformer's test runtime classpath and two arguments: the official Quilt
Loader 0.30.1 JAR and the approved OP Tab archive. It checks both archive hashes,
the actual FFLoader binary hash, and the descriptor before comparing 540 cases.
Quilt is isolated in a platform-parent URLClassLoader, since its archive also
contains Fabric API classes. This calls only version/range utilities; it never
starts Quilt's loader engine, Minecraft, or an OP Tab class.

Reference behavior comes from Quilt 0.30.1's
`V1ModMetadataReader.readVersionSpecifier`, `SemanticVersionImpl.ofInternal`,
and `VersionInterval.isSatisfiedBy`, compared to FFLoader
2.5.70+0.19.3+1.21.1's actual `VersionPredicate` implementation. Five explicit
operators, six bounds, and eighteen semantic candidate versions exercise empty,
numeric and alphabetic prereleases, releases, build metadata, abbreviated
components, a fourth component, and both sides of the loader boundary.

The newly admitted grammar is deliberately limited to explicit comparisons on
the host-owned semantic `quilt_loader` provider. FFLoader already preserves an
empty-but-present prerelease, so no translation is necessary. Removing the dash
would reject valid prereleases; replacing it with `-0` would reject the empty
boundary itself. Bare Quilt constraints use caret semantics, and raw candidates
use Quilt's FlexVer ordering; the audit verifies these differ from the existing
FFLoader predicates and does not generalize this extension to either case.

Bare numeric dependency constraints such as `1`, `1.2`, `1.2.3`, and
`1.2.3-alpha.1+build.1` are rejected with a caret-semantics diagnostic for both
`depends` and `breaks`. This closes the previous accidental projection of those
Quilt ranges as Fabric equality. `*` and explicit `=`, `>=`, `>`, `<=`, `<` forms
remain accepted within the existing bounded semantic grammar. No range is
rewritten or inferred from a bare value.
