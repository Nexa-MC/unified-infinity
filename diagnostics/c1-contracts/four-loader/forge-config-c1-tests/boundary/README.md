# C1 exact symbol boundary proposal

Review-only artifacts for the COMMON lifecycle probe. This directory changes no production transformer, source owner, API ledger or executable artifact. No Java process, Gradle task or game is started by these scripts.

- `proposed-allowlist.json`: 10 proposed new type mappings, 28 exact method owner/name/descriptors, and only `ModConfig$Type.COMMON` as a new field; existing event-bus/context dependencies remain separate
- `static-results.json`: results of the 12 source/declaration/boundary tests
- `fixtures/NegativeConfigInputs.java`: 22 self-authored rejection classes, intended for a separately authorized compile against official Forge 52.1.0
- `validate_compiled_probe.py`: optional read-only checker for that independently compiled lifecycle probe and negative fixtures

The pinned API1 source ZIP is `source-workspace/fml-unified/build/successor-client-api1/frozen-inputs/api1-source-only.zip`, SHA-256 `c797a562f4a4b14eae619c89aaca75223f5315c599a9cd79f84d49f7a4af7e70`. The proposal pins its relevant source inputs and official Forge binary archives. Static resolution uses the existing hash-pinned Python classfile inventory reader without loading classes.

## What the tests establish

Run from the repository root:

```sh
python3 four-loader/forge-config-c1-tests/boundary/test_boundary.py
```

The tests establish exact official declarations, public access, the generic `Object` descriptors, inherited member-resolution owners, source/archive provenance, consistency with all 184 config member-shape rows (169 public and 15 protected), and compatibility with the existing exact-set/default-deny transformer syntax and class policy. Of those declared rows, this proposal admits 20 exact declaration-owner entries and rejects 164. The additional allowed inherited/context/event invocation owners are checked against official class hierarchies. Every existing ledger admission remains false.

The proposal includes only the invocation owners anticipated in the lifecycle probe. It explicitly defers base `ModLoadingContext` calls, including `get` and both registration overloads; base `ModConfigEvent` and `IConfigEvent` getter calls; Unloading; unused `ConfigValue.save` and `BooleanValue.save` aliases; enum `values`/`valueOf`/`extension`; constructors; raw data; tracker and handler access; every IConfigSpec method; unsupported overloads; custom specs and Forge subclasses.

The old generic IConfigSpec owner is a descriptor-only mapped type because it occurs in registration and `getSpec` descriptors. This grants no callable method or custom implementation. Runtime registration still needs an exact supported-spec and COMMON guard: obtaining a forbidden value through a Java API or reflection cannot be ruled out by an exact Forge-symbol list alone.

## Independent compilation gate

The static tests do not prove the anticipated call owners were emitted. After a separately authorized javac compile against official Forge, run:

```sh
python3 four-loader/forge-config-c1-tests/boundary/validate_compiled_probe.py \
  --positive /path/to/official-lifecycle-probe/classes \
  --negative /path/to/official-negative-fixture/classes
```

The checker requires every proposed member addition to be observed in the positive probe and rejects any unlisted Forge member reference. It separately requires every negative source class to produce a symbol or class-header rejection. It includes method-handle targets through their member constant-pool references. Keep the independent compiler/classpath receipt: classfile parsing cannot prove which inputs javac used.

The checker conservatively includes unused constant-pool references and does not inspect instruction opcodes, apply ASM rewriting, check generic metadata remapping, perform JVM linking or claim lifecycle semantics. Those remain separate integration gates. The class-header fixtures for ConfigValue subclasses are synthetic declarations, since Forge's package-private value constructors prohibit ordinary external Java subclass construction; they do not purport to be executable official-javac output.

`build_proposal.py` reproduces the proposal after verifying the API1 source ZIP and official archive pins. It writes only `proposed-allowlist.json` in this directory. Regeneration intentionally captures the current reviewed fixture hashes; changing a fixture needs review and another independent compilation.
