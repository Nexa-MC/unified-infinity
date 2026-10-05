#!/usr/bin/env python3
"""Explicit CI-only harness adaptation of one generated compiler-input pin."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

import bootstrap as harness


def main():
    harness.require(sys.argv[1:] == ['--compile'], 'Recovery adapter requires the exact --compile invocation')
    harness.require(os.environ.get('GITHUB_ACTIONS') == 'true'
                    and os.environ.get('GITHUB_REPOSITORY') == harness.REPOSITORY
                    and os.environ.get('GITHUB_REF') == harness.BRANCH, 'Recovery adapter restricted to approved CI branch')
    before = harness.recovery_input_record()
    source = harness.ROOT / 'four-loader/quilt-api-probe/build.py'
    spec = importlib.util.spec_from_file_location('original_api1_quilt_probe_builder', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    harness.require({**builder.CLASSPATH_PINS, **builder.PROVENANCE_PINS} == harness.EXPECTED['builderInputPins'],
                    'Original imported builder pins differ from preserved history')
    harness.require(builder.CLIENT == before['path'] and builder.CLIENT in builder.CLASSPATH_PINS,
                    'Recovery must adapt only the original intermediary compiler input')
    receipt = {'status': 'RECOVERY_ADAPTER_STARTED_NOT_ACCEPTED',
               'adaptation': 'CI_ONLY_SINGLE_GENERATED_COMPILER_INPUT',
               'builderSourceSha256': harness.digest(source), 'builderSourceBytesChanged': False,
               'javaAndResourceBytesChanged': False, 'officialLoomModified': False,
               'historicalEntryEquivalence': 'UNKNOWN', 'timestampOnlyDifferenceProven': False,
               'historicalWholeJarPinRetained': before['historicalWholeJarSha256'],
               'adaptedInMemoryPin': before['path'], 'beforeCompilation': before,
               'gameLaunched': False, 'runtimeAcceptance': 'NOT RUN'}
    target = harness.REPORT / 'recovery-receipt.json'
    target.write_text(json.dumps(receipt, indent=2) + '\n')
    # This is the sole adaptation. No source bytes, ZIP bytes, other compiler
    # inputs, tool pins, mappings, or acceptance hashes are rewritten.
    builder.CLASSPATH_PINS[builder.CLIENT] = before['sha256']
    try:
        builder.main()
        after = harness.recovery_input_record()
        receipt['afterCompilation'] = after
        harness.require(after == before, 'Generated compiler input or verified provenance changed during compilation')
        probe = harness.destination(harness.PROBE)
        harness.require(probe.is_file() and 0 < probe.stat().st_size <= harness.EXPECTED['probeMaxBytes']
                        and harness.digest(probe) == harness.EXPECTED['probeSha256'],
                        'Own-probe exact output mismatch; no further relaxation or transport')
        receipt.update({'status': 'PASS_RECOVERY_ADAPTER_EXACT_ORIGINAL_PROBE',
                        'probeSha256': harness.digest(probe), 'probeBytes': probe.stat().st_size})
    except Exception as error:
        receipt['status'] = 'FAIL_RECOVERY_ADAPTER_NO_PAYLOAD'
        receipt['failureType'] = type(error).__name__
        raise
    finally:
        generated = harness.destination(before['path'])
        observed = {'path': before['path'], 'exists': generated.is_file()}
        if generated.is_file():
            observed.update({'sha256': harness.digest(generated), 'bytes': generated.stat().st_size})
        receipt['observedAfterCompilation'] = observed
        if 'afterCompilation' not in receipt:
            try:
                receipt['afterCompilation'] = harness.recovery_input_record()
            except Exception as error:
                receipt['postCompilationVerificationFailure'] = type(error).__name__
        target.write_text(json.dumps(receipt, indent=2) + '\n')
        print('RECOVERY_ADAPTER_RECEIPT ' + json.dumps(receipt, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
