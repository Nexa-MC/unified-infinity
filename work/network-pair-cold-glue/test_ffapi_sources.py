"""Portable tests for the opt-in source profile; no downloads, JVM or games."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
AREA = 'work/network-pair-cold-glue'


def load(path):
    spec = importlib.util.spec_from_file_location('isolated_ffapi_source_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RefreshedSourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.repo = cls.root / 'repo'
        module = load(HERE / 'ffapi_sources.py')
        manifest = json.loads((HERE / 'source-manifest.json').read_text())
        files = [AREA + '/' + name for name in ('ffapi_sources.py', 'source_materialize.py', 'source-manifest.json', 'core-dependency-lock.json', 'build_candidate.py', 'bounded_process.py', 'fml_metadata.py', 'forge_fixture.py', 'generated_output_diagnostics.py', 'product_tuple_diagnostics.py', 'profiles/product-diagnostic-baseline.json')]
        files += [module.PROFILE_REL, module.DELTA_REL, module.MANIFEST_REL, module.LOCK_REL,
                  'portable-bootstrap/ffapi-refresh-source-overlay.zip']
        files += [row['path'] for row in manifest['archives'].values()]
        for relative in files:
            source = REPO / relative
            target = cls.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        cls.module = load(cls.repo / AREA / 'ffapi_sources.py')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_bundle_scope_and_runtime_aggregate_unchanged(self):
        result = self.module.verify_bundle()
        self.assertEqual(result['coreIdentity'], self.module.IDENTITY)
        self.assertFalse(result['runtimeAcceptance'])
        self.assertFalse(result['outputAcceptancePinsChanged'])

    def test_materialize_verify_and_refuse_overwrite(self):
        root = self.root / 'fresh-consumer'
        result = self.module.prepare(self.repo, root)
        self.assertEqual(result['identity']['candidate_identity'], self.module.IDENTITY)
        self.assertEqual(result['ffapiInputsSha256'], self.module.DELTA_SHA256)
        self.assertFalse(result['runtime_ready'])
        self.assertFalse(result['game_accepted'])
        checked = self.module.verify_sources(root)
        self.assertEqual(checked['source_records_verified'], 670)
        self.assertEqual(checked['dependency_records_preserved'], 169)
        self.assertEqual(checked['candidate_identity'], self.module.IDENTITY)
        for relative in (self.module.PROFILE_REL, self.module.DELTA_REL, self.module.LOCK_REL):
            self.assertEqual((root / relative).read_bytes(), (self.repo / relative).read_bytes())
        for relative, row in self.module._support_records(
                json.loads((root / self.module.PROFILE_REL).read_text())).items():
            data = (root / relative).read_bytes()
            self.assertEqual(len(data), row['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
        with self.assertRaisesRegex(ValueError, 'existing consumer root'):
            self.module.prepare(self.repo, root)

    def check_changed_input(self, relative, name):
        path = self.repo / relative
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        consumer = self.root / name
        try:
            with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
                self.module.prepare(self.repo, consumer)
            self.assertFalse(consumer.exists())
        finally:
            path.write_bytes(original)

    def test_tampered_delta_rejected_before_writes(self):
        self.check_changed_input(self.module.DELTA_REL, 'changed-delta')

    def test_tampered_profile_rejected_before_writes(self):
        self.check_changed_input(self.module.PROFILE_REL, 'changed-profile')

    def test_tampered_lock_rejected_before_writes(self):
        self.check_changed_input(self.module.LOCK_REL, 'changed-lock')

    def test_tampered_manifest_rejected_before_writes(self):
        self.check_changed_input(self.module.MANIFEST_REL, 'changed-manifest')

    def test_historical_materializer_replacement_rejected(self):
        self.check_changed_input(AREA + '/source_materialize.py', 'changed-materializer')

    def test_each_reviewed_support_source_rejected_before_writes_if_changed(self):
        for name in ('build_candidate.py', 'bounded_process.py', 'fml_metadata.py', 'forge_fixture.py', 'generated_output_diagnostics.py', 'product_tuple_diagnostics.py', 'profiles/product-diagnostic-baseline.json'):
            with self.subTest(name=name):
                self.check_changed_input(AREA + '/' + name, 'changed-support-' + name)

    def test_each_reviewed_consumer_support_copy_reverified(self):
        root = self.root / 'support-reverification'
        self.module.prepare(self.repo, root)
        for name in ('build_candidate.py', 'bounded_process.py', 'fml_metadata.py', 'forge_fixture.py', 'generated_output_diagnostics.py', 'product_tuple_diagnostics.py', 'profiles/product-diagnostic-baseline.json'):
            with self.subTest(name=name):
                path = root / AREA / name
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                try:
                    with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
                        self.module.verify_sources(root)
                finally:
                    path.write_bytes(original)
        self.assertEqual(self.module.verify_sources(root)['candidate_identity'], self.module.IDENTITY)

    def test_tampered_archive_rejected_before_writes(self):
        path = self.repo / 'portable-bootstrap/ffapi-refresh-source-overlay.zip'
        original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        consumer = self.root / 'changed-archive'
        try:
            with self.assertRaisesRegex(ValueError, 'BLOCKED_SOURCE_INPUTS'):
                self.module.prepare(self.repo, consumer)
            self.assertFalse(consumer.exists())
        finally:
            path.write_bytes(original)

    def test_symlink_selected_input_rejected(self):
        path = self.repo / self.module.LOCK_REL
        original = path.read_bytes()
        outside = self.root / 'outside'
        outside.write_bytes(original)
        path.unlink()
        path.symlink_to(outside)
        try:
            with self.assertRaisesRegex(ValueError, 'Symlink input rejected'):
                self.module.core_lock()
        finally:
            path.unlink()
            path.write_bytes(original)

    def test_historical_defaults_not_mutated(self):
        original = load(self.repo / AREA / 'source_materialize.py')
        before = (original.MANIFEST, original.MANIFEST_SHA256)
        selected = self.module._materializer()
        self.assertEqual((original.MANIFEST, original.MANIFEST_SHA256), before)
        self.assertEqual(original.MANIFEST_SHA256, self.module.BASE_MANIFEST_SHA256)
        self.assertEqual(selected.MANIFEST_SHA256, self.module.MANIFEST_SHA256)
        self.assertNotEqual(selected.MANIFEST, original.MANIFEST)

    def test_overlay_is_source_only(self):
        path = self.repo / 'portable-bootstrap/ffapi-refresh-source-overlay.zip'
        self.module._materializer()._source_only(path.read_bytes(), path.name)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist(), ['verification-metadata.xml', 'expected-build-identity.json'])

    def test_profile_metadata_has_no_machine_absolute_paths(self):
        for relative in (self.module.PROFILE_REL, self.module.DELTA_REL):
            text = (self.repo / relative).read_text()
            self.assertNotIn('/workspace/', text)
            self.assertNotIn('/home/agent/', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
