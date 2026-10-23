# Graphics receipt capacity migration

Source-only derivative of cc6439f3798f99df805fb04f6cd17a758dac7a40. Runtime unproven.

The observed Ubuntu graphics closure failed the previous 8192-byte producer estimate. That limit applied to a JSON receipt containing every installed input path/hash plus actual renderer, process and memory observations; it was not an input-count or graphics-memory limit. The exact failed closure size was not present in the terminal log. This change does not assert a measured closure size or runtime readiness.

The producer estimate, collector serialization and supervisor bounded read now share a 32768-byte graphics-only contract. The collector obtains the constant from its exact SHA-pinned supervisor. The producer retains its conservative 1300-byte measurement allowance and strictly rejects an estimate at or beyond the bound. Actual serialization and decoding permit exactly 32768 bytes and reject 32769. A numbers-only capacity diagnostic does not assert readiness.

All input hashes and the maximum 128 input lock bound are retained. Measurement fields, lock revalidation, renderer/GLX requirements, Xvfb identity/socket ownership, live-child and cleanup checks are unchanged. The separate probe-build receipt remains 8192 bytes. Build/dependency/output pins are unchanged. No network, native graphics, game or CI was run for these tests.

Final tests: cold-glue 240/240 passed; finalizer 7/7 passed. Capacity-specific collector 12/12 and supervisor 17/17 passed (including inherited synthetic fixture checks). Full collector 44 ran: 42 passed and 2 missing historical portable1 fixture errors. Full supervisor 170 ran: 160 passed and 10 missing historical/API fixture errors. Baseline diversion-stage reproduced the identical 2 collector and 10 supervisor error identities; broad suites are not wholly passed.

The original collector and supervisor test files remain byte-identical to the predecessor. Capacity tests are separate modules. Historical AST preservation checks normalize exactly one reviewed capacity expression and assert its expected count and the 32768-byte constant. Additional independent predecessor-function AST hash tests verify that normalization preserves every other statement, reject missing/duplicate capacity expressions, and detect unrelated gate changes. The preserved function hashes are derived from the actual diversion-stage predecessor, not synthesized historical fixtures.

The migrated verify_graphics synthetic fixture passed with a 128-hash map above 8192 bytes, exact 32768 bytes, 32769-byte rejection, tampered-hash rejection and existing socket ownership rejection. Collector tests independently verify exact serialization boundaries, full 128-map equality, decoder/read overflow rejection. Producer tests verify all 128 inputs survive, estimate limit-1 passes, limit and limit+1 fail. These are synthetic boundary fixtures, not actual renderer measurements or readiness.

Commands: python -m unittest discover -s work/network-pair-cold-glue -v; the same command for work/network-pair-finalizer, work/network-graphics-ci-portable2 and work/network-ci-supervisor-portable3; capacity-only discovery adds -p test_receipt_capacity.py. Final source check: python work/network-pair-cold-glue/check_stage.py --profile work/network-pair-cold-glue/profiles/ffapi-20261023.json. All tests run offline without native graphics/game/CI execution.

Missing historical fixtures are graphics portable1 source/tests; supervisor original/portable1/portable2 source/manifests; API preparation source and previously accepted server.properties. They are not added to production closure or represented as available.
