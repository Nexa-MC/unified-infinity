"""Synthetic provenance fixtures only; never execute graphics or package tools."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import graphics_preflight as g
import test_graphics_preflight as baseline

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT.parent / 'network-graphics-ci-portable1'


def setUpModule():
    global PROCESS_GUARD
    PROCESS_GUARD = patch.object(g.subprocess, 'Popen', side_effect=AssertionError('No process in SYNTHETIC tests'))
    PROCESS_GUARD.start()


def tearDownModule():
    PROCESS_GUARD.stop()


class InstalledProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = baseline.LockTests('test_exact_synthetic_input_schema')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.lock = self.fixture.lock
        signed = json.loads(Path(self.lock['package_provenance']).read_text())
        self.receipt = {
            'schema': 1,
            'status': 'OBSERVED_INSTALLED_PACKAGES',
            'observation_reference': 'SYNTHETIC schema fixture; no actual package observation',
            'distribution': {'id': 'ubuntu', 'version_id': '24.04'},
            'runner': copy.deepcopy(self.lock['expected_runner']),
            'packages': [{key: row[key] for key in ('package', 'version', 'architecture')}
                         for row in signed['packages']],
            'file_packages': signed['file_packages'],
            'file_sha256': {row['path']: row['sha256'] for row in self.lock['inputs']
                            if row['path'] != self.lock['package_provenance']},
        }
        self.seal()

    def seal(self):
        path = Path(self.lock['package_provenance'])
        raw = json.dumps(self.receipt).encode()
        path.chmod(0o644)
        path.write_bytes(raw)
        path.chmod(0o444)
        pin = next(row for row in self.lock['inputs'] if row['path'] == str(path))
        pin.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    def reject(self, pattern):
        self.seal()
        with self.assertRaisesRegex(ValueError, pattern):
            g.validate_lock(self.lock, baseline.S)

    def test_observed_receipt_accepts_exact_pins_without_archive_chain(self):
        self.assertEqual(g.validate_lock(self.lock, baseline.S),
                         {row['path']: row['sha256'] for row in self.lock['inputs']})
        self.assertNotIn('snapshot', self.receipt)
        self.assertNotIn('signed_index_review_reference', self.receipt)

    def test_distribution_must_be_actual_target_ubuntu_24(self):
        for distribution in ({'id': 'debian', 'version_id': '12'},
                             {'id': 'ubuntu', 'version_id': '22.04'}):
            with self.subTest(distribution=distribution):
                self.receipt['distribution'] = distribution
                self.reject('Ubuntu 24.04')

    def test_observed_runner_must_match_exact_lock(self):
        runner = copy.deepcopy(self.receipt['runner'])
        for field, value in (('ImageOS', 'debian'), ('ImageVersion', '20261004.1.1'),
                             ('machine', 'aarch64')):
            with self.subTest(field=field):
                self.receipt['runner'] = {**runner, field: value}
                self.reject('differs from reviewed runner')

    def test_observation_reference_is_required_and_bounded(self):
        for value in ('', 'x' * 513, None):
            with self.subTest(value=str(value)[:20]):
                self.receipt['observation_reference'] = value
                self.reject('observation reference missing')

    def test_signed_claim_fields_are_not_allowed_on_observations(self):
        for field, value in (('snapshot', '20260927T000000Z'),
                             ('signed_index_review_reference', 'UNSUPPORTED CLAIM'),
                             ('signature_verified', True)):
            with self.subTest(field=field):
                self.receipt[field] = value
                self.reject('installed package observations')
                self.receipt.pop(field)

    def test_observations_cannot_be_relabelled_as_verified_archive_chain(self):
        self.receipt['status'] = 'VERIFIED_UBUNTU_CLOSURE'
        self.reject('package closure receipt')

    def test_package_archive_claims_are_not_allowed_on_observed_rows(self):
        self.receipt['packages'][0]['sha256'] = '0' * 64
        self.reject('installed package')

    def test_invalid_package_identity_and_duplicate_are_rejected(self):
        original = copy.deepcopy(self.receipt['packages'])
        for field, value in (('package', '../xvfb'), ('package', None),
                             ('version', ''), ('version', '1\nforged'),
                             ('version', 'x' * 129), ('architecture', 'arm64')):
            with self.subTest(field=field, value=value):
                self.receipt['packages'] = copy.deepcopy(original)
                self.receipt['packages'][0][field] = value
                self.reject('Invalid installed package identity')
        self.receipt['packages'] = original + [copy.deepcopy(original[0])]
        self.reject('Duplicate installed package identity')

    def test_architecture_all_and_debian_epoch_version_are_supported(self):
        self.receipt['packages'].append({'package': 'xkb-data', 'version': '2:1.0~rc1-0ubuntu1',
                                         'architecture': 'all'})
        self.seal()
        self.assertEqual(len(g.validate_lock(self.lock, baseline.S)), 4)

    def test_missing_mesa_inventory_is_rejected(self):
        self.receipt['packages'][2]['package'] = 'other-package'
        self.reject('Mesa DRI packages required')

    def test_every_pinned_file_needs_matching_package_ownership(self):
        original = copy.deepcopy(self.receipt['file_packages'])
        library = next(path for path in original if path.endswith('.so'))
        cases = [{path: value for path, value in original.items() if path != library},
                 {**original, '/unobserved': 'xvfb:amd64=1-synthetic'},
                 {**original, library: 'libgl1-mesa-dri:amd64=unobserved-version'},
                 {**original, library: None},
                 {**original, self.lock['package_provenance']: 'xvfb:amd64=1-synthetic'}]
        for mapping in cases:
            with self.subTest(mapping=mapping):
                self.receipt['file_packages'] = mapping
                self.reject('Every tool/library needs observed package ownership')

    def test_tools_cannot_claim_another_installed_package(self):
        self.receipt['file_packages'][self.lock['tools']['xvfb']] = 'mesa-utils-bin:amd64=1-synthetic'
        self.reject('Wrong observed official tool package')

    def test_every_file_hash_must_match_exact_reviewed_input_pin(self):
        original = copy.deepcopy(self.receipt['file_sha256'])
        first = next(iter(original))
        cases = [{path: value for path, value in original.items() if path != first},
                 {**original, '/unobserved': '0' * 64},
                 {**original, first: '0' * 64},
                 {**original, first: True}]
        for hashes in cases:
            with self.subTest(hashes=hashes):
                self.receipt['file_sha256'] = hashes
                self.reject('Every observed file SHA-256')

    def test_observation_receipt_and_input_bytes_remain_pinned(self):
        for field in ('package_provenance', 'xvfb'):
            with self.subTest(field=field):
                value = self.lock['package_provenance'] if field == 'package_provenance' else self.lock['tools'][field]
                path = Path(value)
                original, mode = path.read_bytes(), path.stat().st_mode & 0o777
                try:
                    path.chmod(0o755)
                    path.write_bytes(original + b'changed')
                    path.chmod(mode)
                    with self.assertRaises(ValueError):
                        g.validate_lock(self.lock, baseline.S)
                finally:
                    path.chmod(0o755)
                    path.write_bytes(original)
                    path.chmod(mode)

    def test_observation_receipt_does_not_authorize_local_graphics(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(g, 'OwnedChild') as spawn:
            with self.assertRaisesRegex(ValueError, 'GitHub CI'):
                g.execute(self.lock, {}, baseline.S, ROOT / 'must-not-exist')
            spawn.assert_not_called()


class PreservationTests(unittest.TestCase):
    def test_all_existing_functions_except_provenance_validator_are_unchanged(self):
        def definitions(path):
            return {node.name: ast.dump(node) for node in ast.parse(path.read_text()).body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        old = definitions(FROZEN / 'graphics_preflight.py')
        new = definitions(ROOT / 'graphics_preflight.py')
        self.assertEqual(set(new) - set(old), {'validate_installed_observations'})
        for name in old:
            if name != 'validate_lock':
                with self.subTest(name=name):
                    self.assertEqual(new[name], old[name])

    def test_fifteen_original_test_bodies_are_preserved(self):
        old = (FROZEN / 'test_graphics_preflight.py').read_text()
        new = (ROOT / 'test_graphics_preflight.py').read_text()
        self.assertEqual(new.replace('network-ci-supervisor-portable3/', 'network-ci-supervisor-portable1/'), old)


if __name__ == '__main__':
    unittest.main()
