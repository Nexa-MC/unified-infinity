"""Check recovered source/resource completeness without Java or downloads."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import compile_probe as probe
import source_materialize as sources

REPO = Path(__file__).resolve().parents[2]


class RecoveredSourceClosureTests(unittest.TestCase):
    def test_complete_probe011_sources_and_license(self):
        manifest = probe.verify_source(REPO/'work/network-ci-native-probe011')
        self.assertEqual(len(manifest['files']), 16)
        self.assertIn('LICENSE', {r['path'] for r in manifest['files']})
        self.assertEqual(probe.ARTIFACT_NAME, 'network-control-probe-0.1.1.jar')
        self.assertEqual(probe.REFERENCE_JAR_SHA, '791f6c303475ad9d32baaacc98f0350c027d6efe826dcd5aa9dc99a81da2918a')

    def test_missing_license_and_unrecorded_resource_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'probe';shutil.copytree(REPO/'work/network-ci-native-probe011',source)
            license_bytes=(source/'LICENSE').read_bytes();(source/'LICENSE').unlink()
            with self.assertRaisesRegex(ValueError,'source/resource'):
                probe.verify_source(source)
            (source/'LICENSE').write_bytes(license_bytes)
            (source/'extra-resource.txt').write_text('unrecorded')
            with self.assertRaisesRegex(ValueError,'closure differs'):
                probe.verify_source(source)

    def test_entry_payload_or_archive_identity_drift_rejected(self):
        entries=json.loads(probe.REFERENCE_ENTRIES.read_text())
        probe.verify_reference(entries,probe.REFERENCE_JAR_SHA)
        for mutation in ('missing','added','changed'):
            changed=dict(entries)
            if mutation=='missing':changed.pop('LICENSE')
            elif mutation=='added':changed['foreign.class']='0'*64
            else:changed['LICENSE']='0'*64
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError,'entry payload differs'):
                probe.verify_reference(changed,probe.REFERENCE_JAR_SHA)
        with self.assertRaisesRegex(ValueError,'output differs'):
            probe.verify_reference(entries,'0'*64)

    def test_recovered_product_inputs_materialize_with_base_identity(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch('subprocess.run',side_effect=AssertionError('No child allowed')), \
             mock.patch('subprocess.Popen',side_effect=AssertionError('No child allowed')):
            root=Path(folder)/'consumer'
            result=sources.prepare(REPO,root)
            self.assertEqual(result['identity']['source_records_verified'],670)
            self.assertEqual(len(result['archives']),5)
            api=root/'work/api1'
            inventory=json.loads((api/'docs/four-loader/quilt/bundled-tooltip.json').read_text())
            self.assertEqual([r['id'] for r in inventory['modules']],['quilt_base','quilt_lifecycle_events','quilt_tooltip'])
            self.assertTrue(os.access(api/'tools/java-env.sh',os.X_OK))
            self.assertEqual(probe.sha(api/'tools/java-env.sh'),'baf50fbe0b7d616a10b5158ad5b23636b3dfd435c0cd1522d1ddb968873a122d')
            prepared=probe.prepare(REPO,root)
            self.assertEqual(prepared['sourceManifestSha256'],probe.SOURCE_SHA)
            self.assertFalse(prepared['gameLaunched'])
            probe.verify_source(root/probe.SOURCE_RELATIVE)


if __name__ == '__main__':
    unittest.main()
