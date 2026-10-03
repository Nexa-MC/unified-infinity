# Parameter-removal regression tests

Standalone Java 21 regression coverage for the experimental
`org.sinytra.adapter.transform.param.RemoveParameterTransformer` patch. The harness
uses the actual transformer and dependency classes. It does not substitute a
copied implementation, mock the transformer, boot Minecraft, or change production
patch source/classes.

## Reproduce

Run from the repository root:

```sh
bash lithium-trial/patches/parameter-removal/tests/run.sh \
  > logs/lithium-parameter-unit.log 2>&1
```

The self-contained runner records input SHA-256 values and the actual transformer
and ASM code-source locations. Its exact compile/run commands are in `run.sh`.
It uses:

- `.toolchains/jdk-21.0.12.1+1/bin/javac` and `java`
- `lithium-trial/patches/parameter-removal/classes` first on the patched classpath
- `integrated-loader/build/libs/unified-infinity-connector-2.0.0-beta.17+1.21.1-derived.jar`
- ASM 9.8 jars before other jars from `run/lithium-unified/libraries`
- `docs/real-mod-trial/lithium-fabric-0.15.4+mc1.21.1.jar`

First, it compiles the existing experimental source into its own ignored
`build/recompiled-patch-classes` directory with `javac -g`, and requires that class
file to be byte-identical to the supplied compiled patch. The compiler's existing
unchecked-operation notice comes from the production patch's generic `List[]`
array generators; test-source compilation with `-Xlint:all` emits no warnings.

Then it compiles and runs the suite. Finally it launches a separate JVM against
the immutable base jar, deliberately excluding both patch class directories, and
runs the same actual-apply Lithium fixture as a negative control. A nonzero exit
alone is insufficient: the runner requires both the stale count assertion and
the matching ASM `ArrayIndexOutOfBoundsException` to appear in its output.

All generated files are under `tests/build`. Logging is console-only to avoid
mutating Minecraft's or another task's log files. No network access is required.

## Recorded result

On 2026-10-03:

- Patched suite: **31 tests, 429 checks, 0 failures**
- Fresh source compilation: **byte-identical** to supplied patched class
- Immutable-base control: **expected failure**, stale invisible annotation count
  `9` with descriptor/annotation-array lengths `7`, followed by
  `ArrayIndexOutOfBoundsException: Index 7 out of bounds for length 7` in
  `AnnotationWriter.computeParameterAnnotationsSize`
- Runner exit code: **0**, meaning the patched suite passed and the control failed
  for the precise expected reason

Input hashes:

```text
base jar:      9a6e896e7742fb920469266808c409c76ac0ab84e0d82f7ac4b5ecbe9ee11eb1
Lithium jar:   92329d98c57f5a22091a0adb509fdb1d60113a5602c708b799b13134bad13baa
patched class:d8610a0da184599c28ee7ebe3da96de86738a6c80bb856897be3c4716463772a
```

The full output is `logs/lithium-parameter-unit.log`. The negative-control output
is also copied to `tests/build/unpatched-negative-control.log`.

## Coverage

- Actual `RemoveParameterTransformer.apply`, using a real `MixinContext`
  constructed from `PatchContext.create`, a target type, and a null environment
- Exact original Lithium `EntityMixin.tryShortcutFluidPushing` descriptor,
  `MethodParameters`, annotation arrays/counts and `@Local` payloads read from the
  approved jar; no hard-coded substitute annotation fixture
- Nine original arguments: TagKey, double, CallbackInfoReturnable, six integers
- Two consecutive removals of the first argument while the method descriptor
  still has nine arguments, as in the surrounding transformation pipeline
- Final descriptor/array/count **7/7/7**, retaining `@Local(ordinal=0..5)` at
  descriptor indices **1..6**, including serialization and ASM readback
- Visible-only, invisible-only, and both annotation channels for first, middle,
  and last parameter removal
- Nonzero offset: removes `index + offset`, preserving the earlier annotations
- Removal down to zero parameters; null annotation arrays; implicit zero counts
  retain their in-memory meaning while ASM emits the correct effective count
- Direct tests of package-private validation and annotation-removal helpers
- Static and instance methods with category-2 parameters, proving correct LVT
  slot calculation/shifting and descriptor-coordinate annotation handling
- Explicit reduced counts, oversized/negative counts, and short/long annotation
  arrays rejected in either visibility before any metadata, parameter list,
  local-variable table, or instruction mutation
- Validation and an empty `TransformParameters` no-op preserve serialized
  fixture bytes; validation preserves the complete original Lithium class's
  ASM-normalized serialized bytes
- `CheckClassAdapter` structural checks and stable ASM serialization/readback

## Boundaries

The real-Lithium test uses a metadata-only abstract method with the original
parameter metadata. It does **not** assert that deleting used arguments from the
original executable handler body is independently valid. Such removal depends
on other adapter transforms and the real loader pipeline. The separate LVT tests
exercise actual instructions whose retained-local accesses must be shifted.

`RemoveParameterTransformer` intentionally leaves descriptor rewriting to
`TransformParameters`. The harness mirrors that caller-owned final step after
all removals and explicitly proves the descriptor was not rewritten between
them. It does not run the full nonempty `TransformParameters` audit/environment
path. The empty-transform test does run that class's actual no-op path.

Byte-identity assertions compare serialization before and after validation/no-op
using the same ASM writer. They do not claim an arbitrary original jar's raw
class bytes equal an ASM roundtrip, which may normalize constant-pool ordering.

`CheckClassAdapter` and readback establish structural serialization correctness,
not full Minecraft execution or admission compatibility. Reduced-count layouts
are deliberately refused rather than reinterpreted. Invalid removal indices and
missing `MethodParameters`/local-variable lists are existing caller-contract
concerns outside this annotation-layout fix. No production defect was found in
the tested, supported layouts.
