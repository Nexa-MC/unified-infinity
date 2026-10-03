"""Byte-only QSL deployment checks; none of these execute module code."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bundle_qsl_verifier', ROOT / 'runtime-bundle/tools/verify_bundle.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class QuiltMetadataInventoryTest(unittest.TestCase):
    def test_native_identity_without_fabric_descriptor(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('quilt.mod.json', json.dumps({'schema_version': 1, 'quilt_loader': {'id': 'quilt_example', 'version': '1.0.0'}}))
        self.assertEqual(v.inventory(data.getvalue(), 'fixture.jar')[0]['mod_ids'], ['quilt_example'])

    def test_unknown_schema_is_rejected(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('quilt.mod.json', '{"schema_version":99,"quilt_loader":{"id":"example"}}')
        with self.assertRaisesRegex(ValueError, 'schema'):
            v.inventory(data.getvalue(), 'fixture.jar')


BUNDLE = ROOT / 'runtime-bundle/build-quilt-candidate/libs/unified-infinity-0.1.0-dev.jar'
PIN = ROOT / 'docs/four-loader/quilt/bundled-initial.json'
FFAPI = ROOT / 'docs/research/upstream/ffapi-baseline.jar'


@unittest.skipUnless(BUNDLE.is_file() and PIN.is_file() and FFAPI.is_file(), 'requires explicit local structural candidate build')
class PinnedQuiltBundleTest(unittest.TestCase):
    def verify_modified_pin(self, mutate):
        data = json.loads(PIN.read_text())
        for row in data['modules']:
            row['file'] = str((PIN.parent / row['file']).resolve())
        mutate(data)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'pins.json'
            path.write_text(json.dumps(data))
            return v.verify(BUNDLE, FFAPI, path)

    def test_byte_identical_two_module_deployment(self):
        result = v.verify(BUNDLE, FFAPI, PIN)
        self.assertEqual(result['archive_count'], 47)
        self.assertEqual(set(result['bundled_qsl_ids']), {'quilt_base', 'quilt_lifecycle_events'})
        self.assertFalse(result['runtime_tested'])

    def test_unlisted_qsl_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, 'explicitly pinned'):
            v.verify(BUNDLE, FFAPI)

    def test_mismatched_payload_hash(self):
        with self.assertRaisesRegex(ValueError, 'checksum|version constraint|version pin'):
            self.verify_modified_pin(lambda d: d['modules'][0].update(sha256='0' * 64))

    def test_mismatched_logical_version(self):
        with self.assertRaisesRegex(ValueError, 'exact bundled QSL logical version'):
            self.verify_modified_pin(lambda d: d['modules'][0].update(version='999.0.0'))

    def test_duplicate_logical_provider(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate QSL'):
            self.verify_modified_pin(lambda d: d['modules'].append(dict(d['modules'][0])))


if __name__ == '__main__':
    unittest.main()
