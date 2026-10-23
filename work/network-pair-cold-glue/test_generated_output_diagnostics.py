"""Tiny synthetic ZIPs only: no downloads, JVM, Gradle, CI or remote work."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest import mock
import warnings
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('generated_output_diagnostics', HERE / 'generated_output_diagnostics.py')
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def archive(entries=(('a.class', b'private class payload'), ('b.txt', b'private resource payload')),
            date=(2020, 1, 1, 0, 0, 0), comment=b'private archive comment'):
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(stream, 'w') as target:
            target.comment = comment
            for name, data in entries:
                target.writestr(zipfile.ZipInfo(name, date), data)
    return stream.getvalue()


class GeneratedOutputDiagnosticsChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='generated-output-check-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.profile = self.root / 'work/api1/run/api1-unified-client-build'
        self.lock_path = self.root / 'work/api1/ci/runtime-restore/input-lock.json'
        self.lock_path.parent.mkdir(parents=True)
        self.paths = [self.profile / 'build/moddev/artifacts' / name for name in
                      ('neoforge-21.1.219.jar', 'client-extra.jar', 'minecraft-clean.jar')]
        self.paths[0].parent.mkdir(parents=True)
        self.pins = []
        for path in self.paths:
            data = archive()
            path.write_bytes(data)
            self.pins.append({'path': str(path.relative_to(self.profile)), 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
        self.save_lock()

    def save_lock(self):
        self.lock_path.write_text(json.dumps({'generatedDevelopmentOutputs': self.pins[:2],
                                             'additionalCleanOutput': self.pins[2]}))

    def emit(self, deadline=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            report = diagnostics.emit(self.root, time.monotonic() + 30 if deadline is None else deadline)
        line = output.getvalue()
        self.assertEqual(len(line.splitlines()), 1)
        self.assertTrue(line.startswith('GENERATED_OUTPUT_DIAGNOSTIC '))
        self.assertLessEqual(len(line.encode()), 32768)
        self.assertEqual(json.loads(line.split(' ', 1)[1]), report)
        for forbidden in ('private class payload', 'private resource payload', 'private archive comment'):
            self.assertNotIn(forbidden, line)
        return report

    def inspect(self, path):
        return diagnostics._zip(path, [time.monotonic() + 20, diagnostics.MAX_HASH_WORK], False)

    def test_exact_three_identities_and_no_payload_contents(self):
        report = self.emit()
        self.assertTrue(report['diagnosticOnly'])
        self.assertFalse(report['fullHistoricalEntryBaseline'])
        self.assertEqual(report['metadataOnlyDifferenceConclusion'], 'UNAVAILABLE')
        for row, path, pin in zip(report['outputs'], self.paths, self.pins):
            self.assertEqual(row['statuses'], ['IDENTITY_MATCH'])
            self.assertTrue(row['exists'] and row['regularFile'])
            self.assertEqual(row['canonicalPath'], str(path.resolve()))
            self.assertEqual((row['actualBytes'], row['actualSha256']), (pin['bytes'], pin['sha256']))
            self.assertLessEqual(len(row['zip']['samples']), 8)
        baseline = report['outputs'][0]['zip']['knownPartialPayloadBaseline']
        self.assertEqual(len(baseline), 3)
        self.assertEqual({row['status'] for row in baseline}, {'MISSING'})

    def test_missing_remains_separate_from_mismatch(self):
        for path in self.paths:
            path.unlink()
        report = self.emit()
        self.assertEqual(len(report['outputs']), 3)
        for row in report['outputs']:
            self.assertEqual(row['statuses'], ['MISSING'])
            self.assertFalse(row['exists'])
            self.assertIsNone(row['actualSha256'])

    def test_corrupt_zip_and_size_hash_mismatch_are_separate(self):
        self.paths[0].write_bytes(b'not a ZIP')
        self.pins[1]['bytes'] += 1
        self.pins[2]['sha256'] = '0' * 64
        self.save_lock()
        rows = self.emit()['outputs']
        self.assertEqual(rows[0]['statuses'], ['SIZE_MISMATCH', 'HASH_MISMATCH', 'CORRUPT_ZIP'])
        self.assertEqual(rows[1]['statuses'], ['SIZE_MISMATCH'])
        self.assertEqual(rows[2]['statuses'], ['HASH_MISMATCH'])

    def test_crc_failure_is_corrupt_zip(self):
        self.paths[0].write_bytes(archive().replace(b'private class payload', b'changed class payload'))
        self.assertIn('CORRUPT_ZIP', self.emit()['outputs'][0]['statuses'])

    def test_payload_metadata_and_order_digests_are_distinct(self):
        original = self.inspect(self.paths[0])
        self.paths[1].write_bytes(archive(date=(2024, 2, 2, 0, 0, 0)))
        metadata = self.inspect(self.paths[1])
        self.assertEqual(original['payloadAggregateSha256'], metadata['payloadAggregateSha256'])
        self.assertEqual(original['entryOrderSha256'], metadata['entryOrderSha256'])
        self.assertNotEqual(original['zipMetadataSha256'], metadata['zipMetadataSha256'])
        self.paths[2].write_bytes(archive((('b.txt', b'private resource payload'), ('a.class', b'private class payload'))))
        reordered = self.inspect(self.paths[2])
        self.assertEqual(original['payloadAggregateSha256'], reordered['payloadAggregateSha256'])
        self.assertNotEqual(original['entryOrderSha256'], reordered['entryOrderSha256'])
        self.assertEqual(original['zipMetadataSha256'], reordered['zipMetadataSha256'])
        self.paths[2].write_bytes(archive((('a.class', b'changed'), ('b.txt', b'private resource payload'))))
        self.assertNotEqual(original['payloadAggregateSha256'], self.inspect(self.paths[2])['payloadAggregateSha256'])

    def test_partial_baseline_never_claims_full_historical_equality(self):
        name = next(iter(diagnostics.KNOWN_PARTIAL))
        self.paths[0].write_bytes(archive(((name, b'known'),)))
        with mock.patch.dict(diagnostics.KNOWN_PARTIAL, {name: hashlib.sha256(b'known').hexdigest()}):
            row = self.emit()['outputs'][0]['zip']
        self.assertEqual(row['knownPartialPayloadBaseline'][0]['status'], 'MATCH')
        self.assertFalse(row['fullHistoricalEntryBaseline'])
        self.assertEqual(row['metadataOnlyDifferenceConclusion'], 'UNAVAILABLE')

    def test_duplicate_names_are_not_collapsed(self):
        self.paths[0].write_bytes(archive((('same', b'one'), ('same', b'two'))))
        row = self.emit()['outputs'][0]
        self.assertIn('DUPLICATE_ZIP_ENTRIES', row['statuses'])
        self.assertEqual(row['zip']['entryCount'], 2)
        self.assertEqual(row['zip']['duplicateNameCount'], 1)

    def test_bounds_preserve_all_critical_identities(self):
        for constant, value, expected in [('MAX_FILE', 1, 'FILE_SIZE_LIMIT'),
                                           ('MAX_ENTRIES', 1, 'ZIP_ENTRY_LIMIT'),
                                           ('MAX_EXPANDED', 1, 'ZIP_EXPANDED_LIMIT'),
                                           ('MAX_HASH_WORK', 1, 'HASH_WORK_LIMIT')]:
            with self.subTest(constant=constant), mock.patch.object(diagnostics, constant, value):
                report = self.emit()
                self.assertFalse(report['complete'])
                self.assertEqual(len(report['outputs']), 3)
                self.assertIn(expected, report['outputs'][0]['statuses'])
                for row, pin in zip(report['outputs'], self.pins):
                    self.assertEqual(row['expectedSha256'], pin['sha256'])
                    self.assertEqual(row['actualBytes'], self.paths[0].stat().st_size)

    def test_dishonest_entry_count_rejected_before_zipfile_allocation(self):
        data = bytearray(archive())
        end = data.rfind(b'PK\x05\x06')
        struct.pack_into('<HH', data, end + 8, 1, 1)
        self.paths[0].write_bytes(data)
        with mock.patch.object(diagnostics, 'MAX_ENTRIES', 1):
            self.assertIn('ZIP_ENTRY_LIMIT', self.emit()['outputs'][0]['statuses'])

    def test_concatenated_directory_cannot_bypass_prescan_entry_limit(self):
        data = bytearray(archive((('a', b'a'), ('b', b'b')), comment=b''))
        end = data.rfind(b'PK\x05\x06')
        length, start = struct.unpack_from('<LL', data, end + 12)
        # A fake single-row directory at the declared offset passes the old
        # pre-scan, while ZipFile relocates to the real two-row directory.
        fake = bytearray(data[start:start + 46])
        struct.pack_into('<3H', fake, 28, length - 46, 0, 0)
        prefix = b'X' * start + bytes(fake) + b'x' * (length - 46)
        struct.pack_into('<HH', data, end + 8, 1, 1)
        combined = prefix + data
        with zipfile.ZipFile(io.BytesIO(combined)) as actual:
            self.assertEqual(len(actual.infolist()), 2)
            self.assertEqual(actual.read('a'), b'a')
        self.paths[0].write_bytes(combined)
        with mock.patch.object(diagnostics, 'MAX_ENTRIES', 1), \
             mock.patch.object(diagnostics.zipfile, 'ZipFile', side_effect=AssertionError('must reject before allocation')):
            report = self.emit()
        self.assertFalse(report['complete'])
        self.assertIn('UNSUPPORTED_ZIP_LAYOUT', report['outputs'][0]['statuses'])

    def test_bzip2_and_lzma_rejected_before_member_decompression(self):
        for compression in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(compression=compression):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w', compression=compression) as archive_file:
                    archive_file.writestr('x', b'x' * 1024 * 1024)
                data = bytearray(buffer.getvalue())
                central = data.index(b'PK\x01\x02')
                # Preserve the tiny compressed stream while lying about the
                # expanded length, as in the independent review reproduction.
                struct.pack_into('<L', data, 22, 1)
                struct.pack_into('<L', data, central + 24, 1)
                self.paths[0].write_bytes(data)
                with mock.patch.object(diagnostics, 'MAX_EXPANDED', 1), \
                     mock.patch.object(diagnostics.zipfile.ZipFile, 'open', side_effect=AssertionError('must not decompress')):
                    report = self.emit()
                self.assertFalse(report['complete'])
                self.assertIn('UNSUPPORTED_ZIP_COMPRESSION', report['outputs'][0]['statuses'])

    def test_deadline_skips_hashes_but_keeps_three_identity_records(self):
        report = self.emit(deadline=0)
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['outputs']), 3)
        for row in report['outputs']:
            self.assertIn('DEADLINE', row['statuses'])
            self.assertIsNone(row['actualSha256'])

    def test_whole_file_identities_precede_optional_zip_work(self):
        def exhausted(*args):
            raise diagnostics.Limited('DEADLINE')
        with mock.patch.object(diagnostics, '_zip', side_effect=exhausted):
            report = self.emit()
        self.assertTrue(all(row['actualSha256'] is not None for row in report['outputs']))

    def test_symlinks_and_pin_path_escape_are_rejected(self):
        outside = self.root / 'outside.jar'
        outside.write_bytes(b'outside data never read')
        self.paths[0].unlink()
        self.paths[0].symlink_to(outside)
        row = self.emit()['outputs'][0]
        self.assertEqual(row['statuses'], ['UNSAFE_PATH'])
        self.assertIsNone(row['actualSha256'])
        self.pins[0]['path'] = 'build/../../outside.jar'
        self.save_lock()
        self.assertEqual(self.emit()['error'], 'INVALID_LOCK')

    def test_non_regular_file_is_not_opened(self):
        self.paths[0].unlink()
        self.paths[0].mkdir()
        row = self.emit()['outputs'][0]
        self.assertEqual(row['statuses'], ['NOT_REGULAR_FILE'])
        self.assertTrue(row['exists'])
        self.assertFalse(row['regularFile'])

    def test_oversized_optional_samples_drop_without_losing_identities(self):
        for path in self.paths:
            path.write_bytes(archive(tuple((chr(0x1f680) * 254 + str(index), b'x') for index in range(8))))
        report = self.emit()
        self.assertTrue(report['optionalDetailsDropped'])
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['outputs']), 3)
        self.assertTrue(all(row['actualSha256'] for row in report['outputs']))
        self.assertTrue(all('samples' not in row['zip'] for row in report['outputs']))

    def test_manifest_reports_raw_identity_and_count_without_values(self):
        manifest = self.profile / 'build/tmp/createMinecraftArtifacts/nfrt_artifact_manifest.properties'
        manifest.parent.mkdir(parents=True)
        data = b'# comment\nnet.example\\:tool\\:1.0=/private/tool.jar\nother=/private/other.jar\n'
        manifest.write_bytes(data)
        report = self.emit()
        evidence = report['nfrtManifest']
        self.assertEqual(evidence['parsedRecordCount'], 2)
        self.assertEqual(evidence['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(evidence['resolvedInputIdentities'], 'UNAVAILABLE')
        self.assertEqual(evidence['invocationArgv'], 'UNAVAILABLE')
        self.assertNotIn('/private/tool.jar', json.dumps(report))
        for data, status in [(b'unsupported line\n', 'UNSUPPORTED_PROPERTIES_FORMAT'),
                             (b'key=value\\\ncontinuation\n', 'UNSUPPORTED_PROPERTIES_FORMAT'),
                             (b'key=value\n' * 161, 'MANIFEST_RECORD_LIMIT')]:
            manifest.write_bytes(data)
            self.assertEqual(self.emit()['nfrtManifest']['status'], status)

    def test_manifest_symlink_is_rejected(self):
        manifest = self.profile / 'build/tmp/createMinecraftArtifacts/nfrt_artifact_manifest.properties'
        manifest.parent.mkdir(parents=True)
        manifest.symlink_to(self.lock_path)
        evidence = self.emit()['nfrtManifest']
        self.assertEqual(evidence['status'], 'UNSAFE_PATH')
        self.assertIsNone(evidence['sha256'])

    def test_digest_work_rechecks_deadline(self):
        with mock.patch.object(diagnostics.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(diagnostics.Limited, 'DEADLINE'):
                diagnostics._digest([('entry', 'sha')], [1, diagnostics.MAX_HASH_WORK])

    def test_final_report_cap_drops_optional_details_not_identities(self):
        with mock.patch.object(diagnostics, '_zip', return_value={'duplicateNameCount': 0, 'detail': 'x' * 40000}):
            report = self.emit()
        self.assertTrue(report['optionalDetailsDropped'])
        self.assertFalse(report['complete'])
        self.assertTrue(all('zip' not in row for row in report['outputs']))
        for row, pin in zip(report['outputs'], self.pins):
            self.assertEqual(row['actualSha256'], pin['sha256'])
            self.assertEqual(row['expectedSha256'], pin['sha256'])


if __name__ == '__main__':
    unittest.main()
