"""Focused synthetic safety tests. Synthetic receipts are never production build evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest import mock
import warnings
import zipfile

import diagnostic_fml_build as b


def supervisor_module():
    path = b.HERE.parent / 'network-ci-supervisor-portable3/supervisor.py'
    spec = importlib.util.spec_from_file_location('diagnostic_build_pin_supervisor', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class DiagnosticBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / 'base.jar'
        self.classes = {name: b'\xca\xfe\xba\xbe' + name.encode() for name in b.REPLACEMENTS | b.OWN_CLASSES}
        self.reference = {name: b.canonical_digest(data) for name, data in self.classes.items()}
        self.patch = mock.patch.object(b, 'EXPECTED_CLASS_SHA', self.reference)
        self.patch.start()
        self.metadata = {'target': 'synthetic-unit-test', 'diagnostic_only': True, 'baseline_acceptance': False}
        self.make_archive()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def make_archive(self, extras=()):
        with zipfile.ZipFile(self.base, 'w') as archive:
            for name in sorted(b.REPLACEMENTS): archive.writestr(name, b'original-class')
            archive.writestr(b.SERVICE, b.SERVICE_ORIGINAL)
            info = zipfile.ZipInfo('META-INF/MANIFEST.MF', (2020, 1, 2, 3, 4, 6))
            info.comment = b'preserved'; info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, b'Manifest-Version: 1.0\n')
            for name, payload in extras: archive.writestr(name, payload)

    def derivative(self):
        output = self.root / 'diagnostic.jar'
        result = b.archive_derivative(self.base, output, self.classes, self.metadata)
        return output, result

    def test_preserves_every_unrelated_payload_and_metadata(self):
        original = self.base.read_bytes()
        output, result = self.derivative()
        self.assertEqual(self.base.read_bytes(), original)
        self.assertEqual(result['unrelatedEntriesPreserved'], 1)
        self.assertEqual(result['replacedEntries'], sorted(b.REPLACEMENTS | {b.SERVICE}))
        self.assertEqual(len(result['addedEntries']), len(b.OWN_CLASSES) + 1)
        self.assertEqual(b.compare_derivative(self.base, output, self.metadata), result)

    def test_exact_service_append_preserves_three_original_providers(self):
        original = b.SERVICE_ORIGINAL
        self.assertFalse(original.endswith(b'\n'))
        output, result = self.derivative()
        with zipfile.ZipFile(output) as archive:
            actual = archive.read(b.SERVICE)
        self.assertTrue(actual.startswith(original))
        self.assertEqual(actual, original + b'\n' + b.SERVICE_PROVIDER.encode('ascii') + b'\n')
        self.assertEqual(actual.splitlines()[:3], original.splitlines())
        self.assertEqual(actual.splitlines().count(b.SERVICE_PROVIDER.encode('ascii')), 1)
        self.assertEqual(len(actual.splitlines()), 4)
        self.assertTrue(result['originalProvidersPreserved'])
        self.assertIn(b.SERVICE, result['replacedEntries'])
        self.assertEqual(result['serviceOriginalSha256'], b.canonical_digest(original))

    def test_changed_missing_or_preappended_service_refused(self):
        for altered in (None, b.SERVICE_ORIGINAL + b'\n', b.SERVICE_DERIVED, b'unknown.Provider'):
            self.make_archive()
            with zipfile.ZipFile(self.base) as archive:
                rows = [(info, archive.read(info)) for info in archive.infolist() if info.filename != b.SERVICE]
            with zipfile.ZipFile(self.base, 'w') as archive:
                for info, payload in rows: archive.writestr(info, payload)
                if altered is not None: archive.writestr(b.SERVICE, altered)
            with self.assertRaisesRegex(ValueError, 'service descriptor'):
                b.read_archive(self.base)

    def test_hardware_scope_is_explicit_and_separately_named(self):
        self.assertEqual(b.SCOPE['diagnosticProfile'], 'system-report-hardware-inventory-skip-v1')
        self.assertIs(b.SCOPE['behavioralChange'], True)
        self.assertEqual(b.SCOPE['hardwareScope'], 'all-SystemReport-instances-including-crash-reports')
        self.assertIs(b.SCOPE['nonHardwareFieldsPreserved'], True)
        self.assertIs(b.SCOPE['gameJarBytesModified'], False)
        self.assertIn('hardware-skip', b.OUTPUT)
        self.assertTrue(all('hardware-skip' in name for name in b.ARTIFACT_NAMES.values()))
        self.assertEqual(b.METADATA, 'META-INF/unified-hardware-inventory-skip-diagnostic.json')

    def test_duplicate_member_refused(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.base, 'a') as archive: archive.writestr('META-INF/MANIFEST.MF', b'duplicate')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): b.read_archive(self.base)

    def test_signatures_refused(self):
        for name in ('META-INF/test.SF', 'META-INF/test.RSA', 'META-INF/test.DSA', 'META-INF/test.EC', 'META-INF/SIG-X'):
            with self.subTest(name=name):
                self.make_archive([(name, b'signed')])
                with self.assertRaisesRegex(ValueError, 'Signed'): b.read_archive(self.base)

    def test_configured_installation_rejected_but_exact_unapproved_placeholder_preserved(self):
        name = 'META-INF/unified-admission/installation.json'
        for payload in (b'{"approved":true}', b'{"schema":1,"approved":false}', b'{}'):
            self.make_archive([(name, payload)])
            with self.assertRaisesRegex(ValueError, 'Configured'): b.read_archive(self.base)
        self.make_archive([(name, b'{"schema":1,"approved":false}\n')])
        output, result = self.derivative()
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read(name), b'{"schema":1,"approved":false}\n')
        self.assertEqual(result['unrelatedEntriesPreserved'], 2)
        self.make_archive([('other/installation.json', b'{"schema":1,"approved":false}\n')])
        with self.assertRaisesRegex(ValueError, 'Configured'): b.read_archive(self.base)

    def test_archive_symlink_rejected(self):
        info = zipfile.ZipInfo('link'); info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.base, 'a') as archive: archive.writestr(info, b'target')
        with self.assertRaisesRegex(ValueError, 'symlink'): b.read_archive(self.base)

    def test_archive_path_aliases_rejected(self):
        for name in ('../escape', '/absolute', 'a/../b', 'a\\b', 'a//b'):
            self.make_archive([(name, b'no')])
            with self.assertRaisesRegex(ValueError, 'Unsafe'): b.read_archive(self.base)

    def test_missing_launch_class_rejected(self):
        with zipfile.ZipFile(self.base, 'w') as archive: archive.writestr('other', b'no')
        with self.assertRaisesRegex(ValueError, 'Required'): b.read_archive(self.base)

    def test_previously_derived_base_refused(self):
        for name in (b.METADATA, b.OWN + 'Existing.class'):
            self.make_archive([(name, b'old')])
            with self.assertRaisesRegex(ValueError, 'Previously'): b.read_archive(self.base)

    def test_extra_or_missing_compiler_classes_rejected(self):
        for changed in (dict(self.classes, **{'unrelated/Evil.class': b'x'}),
                        {key: value for key, value in self.classes.items() if key != b.CLASS + '.class'}):
            with self.assertRaisesRegex(ValueError, 'inventory'):
                b.archive_derivative(self.base, self.root / 'bad.jar', changed, self.metadata)

    def test_forged_compiler_bytes_rejected_even_with_valid_inventory(self):
        changed = dict(self.classes); changed[b.CLASS + '.class'] = b'forged'
        with self.assertRaisesRegex(ValueError, 'deterministic'):
            b.archive_derivative(self.base, self.root / 'bad.jar', changed, self.metadata)

    def test_stale_output_refused_without_overwrite(self):
        output, _ = self.derivative(); original = output.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Stale'):
            b.archive_derivative(self.base, output, self.classes, self.metadata)
        self.assertEqual(output.read_bytes(), original)

    def test_unrelated_archive_mutation_rejected(self):
        output, _ = self.derivative()
        with zipfile.ZipFile(output) as archive: rows = [(info, archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(output, 'w') as archive:
            for info, payload in rows:
                archive.writestr(info, b'changed' if info.filename == 'META-INF/MANIFEST.MF' else payload)
        with self.assertRaisesRegex(ValueError, 'Unrelated'): b.compare_derivative(self.base, output, self.metadata)

    def test_filesystem_symlink_and_escape_refused(self):
        (self.root / 'link').symlink_to(self.base)
        with self.assertRaises(ValueError): b.exact_pin(self.root, self.root / 'link')
        with self.assertRaises(ValueError): b.rel(self.root, '../escape')

    def test_full_refreshed_proof_required_before_any_build_action(self):
        with mock.patch.object(b.refreshed, 'validate_full_build', side_effect=ValueError('FULL_PROOF_MISSING')) as verify, \
                mock.patch.object(b, 'source_inputs') as source, mock.patch.object(b, 'compile_classes') as compiler:
            with self.assertRaisesRegex(ValueError, 'FULL_PROOF_MISSING'):
                b.execute(self.root, self.root, deadline=time.monotonic()+10, profile='profile.json', build_proof='proof.json')
            verify.assert_called_once(); source.assert_not_called(); compiler.assert_not_called()
            self.assertFalse((self.root / b.OUTPUT).exists())

    def test_expired_deadline_refuses_even_proof_work(self):
        with mock.patch.object(b, '_proof') as proof:
            with self.assertRaises(TimeoutError):
                b.execute(self.root, self.root, deadline=time.monotonic()-1, profile='p', build_proof='q')
            proof.assert_not_called()
        for value in (float('nan'), float('inf'), None):
            with self.assertRaises(ValueError): b.remaining(value)

    def test_compile_inherits_remaining_deadline_and_cleans_classes(self):
        out = self.root / 'out'; out.mkdir()
        deadline = time.monotonic()+0.25
        def fake_run(command, **kwargs):
            self.assertGreater(kwargs['timeout'], 0)
            self.assertLessEqual(kwargs['timeout'], 0.25)
            self.assertIn('-J-Xmx128m', command)
            self.assertIn('-J-XX:ActiveProcessorCount=2', command)
            raise TimeoutError('inherited-expired')
        with mock.patch.object(b.bounded_process, 'run', side_effect=fake_run):
            with self.assertRaises(TimeoutError):
                b.compile_classes(self.root, out, self.root/'jdk', [], [], deadline)
        self.assertFalse((out/'classes').exists())

    def test_wrong_unified_hash_rejected_even_after_validator_return(self):
        (self.root/'profile').write_text('{}'); (self.root/'proof').write_text('{}')
        with mock.patch.object(b.refreshed, 'validate_full_build', return_value={'artifacts': {'fml': {'sha256': 'wrong'}}}):
            with self.assertRaisesRegex(ValueError, 'Wrong unconfigured'):
                b._proof(self.root, 'profile', 'proof')

    def test_synthetic_two_target_receipts_validate_and_reject_reordered_or_forged_evidence(self):
        # Every proof/compiler boundary is explicitly mocked. This tests portable
        # plumbing only, never pretends the missing real Unified build exists.
        repo = b.HERE.parents[1]
        unified = self.root / 'unified-original.jar'
        unified.write_bytes(self.base.read_bytes())
        with zipfile.ZipFile(unified, 'a') as archive:
            archive.writestr('META-INF/unified-admission/installation.json', b'{"schema":1,"approved":false}\n')
        native_pin = b.exact_pin(self.root, self.base)
        unified_pin = b.exact_pin(self.root, unified)
        for name in ('profile.json', 'proof.json'): (self.root/name).write_text('{"synthetic_unit_test":true}')
        proof_pins = [b.exact_pin(self.root, self.root/name) for name in ('profile.json', 'proof.json')]
        proof = {'artifacts': {'fml': unified_pin}, 'inputPins': [native_pin, unified_pin]}
        jdk = self.root / 'jdk'
        def fake_compile(consumer, root, actual_jdk, dependencies, sources, deadline):
            self.assertGreater(b.remaining(deadline), 0)
            for name in ('stdout', 'stderr'): (root/('compile.'+name+'.txt')).write_bytes(b'')
            command = [arg.replace(str(consumer), '${CONSUMER}') for arg in
                       b.compiler_command(consumer, root, actual_jdk, dependencies, sources)]
            return self.classes, {'exitCode': 0, 'timeoutSeconds': 1, 'inheritedDeadline': True,
                'heapMiB': 128, 'activeProcessors': 2, 'javaRelease': 21, 'command': command,
                'stdout': b.exact_pin(consumer, root/'compile.stdout.txt'),
                'stderr': b.exact_pin(consumer, root/'compile.stderr.txt'), 'classHashes': self.reference}
        with mock.patch.object(b, '_proof', return_value=(proof, proof_pins)) as proof_check, \
                mock.patch.object(b, 'compiler_inputs', return_value=(jdk, [], [native_pin])), \
                mock.patch.object(b, 'compile_classes', side_effect=fake_compile) as compile_check, \
                mock.patch.object(b, 'NATIVE_SHA', native_pin['sha256']), \
                mock.patch.object(b, 'FIXED_FML_SHA', unified_pin['sha256']):
            manifest = b.execute(repo, self.root, deadline=time.monotonic()+10,
                                 profile='profile.json', build_proof='proof.json')
            good_manifest = manifest.read_bytes()
            result = b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
            self.assertEqual([r['target'] for r in result['receipts']], ['native', 'unified'])
            self.assertEqual(set(result['artifacts']), {'native', 'unified'})
            self.assertEqual(compile_check.call_count, 1)
            self.assertEqual(proof_check.call_count, 3)  # entry, post-build, validation
            self.assertTrue(all(not r['baseline_acceptance'] for r in result['receipts']))
            for receipt in result['receipts']:
                for key, expected in b.SCOPE.items():
                    self.assertIs(type(receipt[key]), type(expected))
                    self.assertEqual(receipt[key], expected)
                    self.assertEqual(receipt['archiveMetadata'][key], expected)
            # Rehashed receipt metadata cannot re-label this as logging-only, or
            # substitute a numeric truth value for the exact behavioral flag.
            metadata_manifest = json.loads(good_manifest)
            metadata_receipt_path = Path(metadata_manifest['build_receipts'][0]['path'])
            metadata_receipt_bytes = metadata_receipt_path.read_bytes()
            for key, bad in (('diagnosticProfile', 'process-start-observation-only'), ('behavioralChange', 1)):
                changed = json.loads(metadata_receipt_bytes)
                changed[key] = bad
                changed['archiveMetadata'][key] = bad
                metadata_receipt_path.write_text(json.dumps(changed))
                changed_pin = b.exact_pin(self.root, metadata_receipt_path)
                metadata_manifest['build_receipts'][0] = dict(changed_pin, path=str(metadata_receipt_path))
                manifest.write_text(json.dumps(metadata_manifest))
                with self.assertRaisesRegex(ValueError, 'diagnostic metadata'):
                    b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
            metadata_receipt_path.write_bytes(metadata_receipt_bytes)
            manifest.write_bytes(good_manifest)
            exported_paths = {row['path'] for row in result['inputPins']}
            for receipt in result['receipts']:
                for key in ('stdout', 'stderr'):
                    log = receipt['compilation'][key]
                    self.assertEqual(log['bytes'], 0)
                    self.assertEqual(log['sha256'], b.canonical_digest(b''))
                    self.assertNotIn(log['path'], exported_paths)
                    self.assertEqual(b.refreshed.check_pin(self.root, log).read_bytes(), b'')
            supervisor = supervisor_module()
            for row in result['inputPins']:
                self.assertGreater(row['bytes'], 0)
                absolute = dict(row, path=str(self.root/row['path']))
                self.assertEqual(supervisor.file_pin(absolute, self.root), self.root/row['path'])
            # Empty observations remain strictly checked through the sealed receipt.
            log_path = self.root / result['receipts'][0]['compilation']['stdout']['path']
            log_path.write_bytes(b'changed-after-compile')
            with self.assertRaisesRegex(ValueError, 'compiler log pin'):
                b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
            log_path.write_bytes(b'')
            self.assertEqual(b.exact_pin(self.root, self.base), native_pin)
            self.assertEqual(b.exact_pin(self.root, unified), unified_pin)
            # Exercise nonempty provenance streams through the SAME actual
            # validator and supervisor boundary, without mocking either.
            originals = {}
            current = json.loads(good_manifest)
            log_paths = {row['compilation'][name]['path']
                         for row in result['receipts'] for name in ('stdout', 'stderr')}
            for name in log_paths: (self.root/name).write_bytes(b'compiler observation\n')
            try:
                for index, receipt_pin in enumerate(current['build_receipts']):
                    receipt_file = Path(receipt_pin['path'])
                    originals[receipt_file] = receipt_file.read_bytes()
                    receipt = json.loads(originals[receipt_file])
                    for key in ('stdout', 'stderr'):
                        receipt['compilation'][key] = b.exact_pin(self.root, self.root/receipt['compilation'][key]['path'])
                    receipt_file.write_text(json.dumps(receipt))
                    current['build_receipts'][index] = dict(b.exact_pin(self.root, receipt_file), path=str(receipt_file))
                manifest.write_text(json.dumps(current))
                nonempty = b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
                self.assertTrue(log_paths.issubset({row['path'] for row in nonempty['inputPins']}))
                for row in nonempty['inputPins']:
                    absolute = dict(row, path=str(self.root/row['path']))
                    self.assertEqual(supervisor.file_pin(absolute, self.root), self.root/row['path'])
                for name in log_paths:
                    (self.root/name).write_bytes(b'changed compiler log\n')
                    with self.assertRaisesRegex(ValueError, 'compiler log pin'):
                        b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
                    (self.root/name).write_bytes(b'compiler observation\n')
            finally:
                for name in log_paths: (self.root/name).write_bytes(b'')
                for path, data in originals.items(): path.write_bytes(data)
                manifest.write_bytes(good_manifest)
            # An empty executable/runtime input must not receive this special
            # provenance treatment, even with an internally consistent digest.
            empty_runtime = self.root/'empty-runtime.jar'
            empty_runtime.write_bytes(b'')
            empty_pin = b.exact_pin(self.root, empty_runtime)
            with self.assertRaisesRegex(ValueError, 'Invalid pin'):
                supervisor.file_pin(dict(empty_pin, path=str(empty_runtime)))
            proof['inputPins'].append(empty_pin)
            try:
                # Make receipts agree so the failure is specifically the positive
                # launch-input constraint, not a stale receipt-provenance mismatch.
                current = json.loads(manifest.read_text())
                originals = {}
                for index, receipt_pin in enumerate(current['build_receipts']):
                    receipt_file = Path(receipt_pin['path'])
                    originals[receipt_file] = receipt_file.read_bytes()
                    receipt = json.loads(originals[receipt_file])
                    receipt['fullBuildInputPins'].append(empty_pin)
                    receipt_file.write_text(json.dumps(receipt))
                    current['build_receipts'][index] = dict(b.exact_pin(self.root, receipt_file), path=str(receipt_file))
                manifest.write_text(json.dumps(current))
                with self.assertRaisesRegex(ValueError, 'Runtime provenance input must be nonempty'):
                    b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
            finally:
                proof['inputPins'].pop()
                for path, data in originals.items(): path.write_bytes(data)
                manifest.write_bytes(good_manifest)
            with self.assertRaisesRegex(ValueError, 'Stale'):
                b.execute(repo, self.root, deadline=time.monotonic()+10,
                          profile='profile.json', build_proof='proof.json')
            self.assertEqual(compile_check.call_count, 1)
            value = json.loads(good_manifest); value['build_receipts'].reverse()
            manifest.write_text(json.dumps(value))
            with self.assertRaises(ValueError): b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')
            manifest.write_bytes(good_manifest)
            value = json.loads(good_manifest)
            receipt_path = Path(value['build_receipts'][0]['path'])
            receipt = json.loads(receipt_path.read_text())
            receipt['compilation']['command'].append('--forged')
            receipt_path.write_text(json.dumps(receipt))
            pin = b.exact_pin(self.root, receipt_path)
            value['build_receipts'][0] = dict(pin, path=str(receipt_path))
            manifest.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'compiler command'):
                b.validate(repo, self.root, manifest, 'profile.json', 'proof.json')

    def test_source_hook_is_after_prelaunch_and_source_bytes_are_pinned(self):
        repo = b.HERE.parents[1]
        rows = b.source_inputs(repo)
        self.assertEqual(len(rows), 3 + len(b.SOURCE_SHA))
        data = (repo/b.SOURCES/'CommonLaunchHandler.java').read_bytes()
        anchor = b'        var args = preLaunch(arguments, gameLayer);\n'
        self.assertEqual(data.count(anchor), 1)
        hooked = data.replace(anchor, anchor + b'        net.neoforged.fml.loading.diagnostic.ProcessStartDiagnosticLaunch.startOrThrow();\n')
        self.assertEqual(b.canonical_digest(hooked), b.HOOK_SOURCE_SHA)


if __name__ == '__main__': unittest.main()
