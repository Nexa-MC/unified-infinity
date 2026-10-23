"""Focused Python-only refreshed pair glue checks.

Synthetic unit fixtures below exercise fail-closed routing/path adaptation only.
They are NOT build receipts, runtime evidence, or a full four-role assembly test.
Run with the baseline glue modules on PYTHONPATH when reviewing this overlay.
"""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import pair_assembly as pair
import refreshed_candidate as gate

HERE = Path(__file__).resolve().parent
# In-repository use works directly. Overlay review may select the exact baseline.
BASE = Path(os.environ.get('PAIR_PROFILE_BASE', str(HERE.parents[1])))
FROZEN = BASE / pair.SOURCE_AREA


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class PairProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'consumer'
        self.root.mkdir()
        self.repo = Path(self.temp.name) / 'repo'
        self.repo.mkdir()

    def write(self, relative, content=b'unit fixture'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(content, bytes):
            content = (json.dumps(content, sort_keys=True) + '\n').encode()
        path.write_bytes(content)
        return gate.pin(self.root, path)

    def verified_fixture(self):
        profile = self.write('unit/profile.json', {'synthetic': 'profile'})
        self.write('unit/proof.json', {'synthetic': 'proof'})
        artifacts = {role: self.write('unit/' + role + '.jar', ('unit artifact ' + role).encode())
                     for role in pair.TUPLE_PINS}
        receipts = {role: self.write('unit/' + role + '-receipt.json', {'synthetic': role})
                    for role in ('core', 'product', 'fml')}
        proof = {'profileSha256': profile['sha256'], 'sourceIdentity': gate.CORE_IDENTITY,
                 'candidateIdentity': profile['sha256'], 'candidateIdentityKind': 'verified-refreshed-build-profile',
                 'artifacts': artifacts, 'receipts': receipts, 'runtimeAcceptance': False}
        for key in ('forgeFixture', 'fmlComparison', 'bundleVerification', 'fmlSourcePreparation'):
            proof[key] = self.write('unit/' + key + '.json', {'synthetic': key})
        sources = {}
        rows = []
        for number in range(195):
            relative = 'unit-fml/src/main/java/S' + str(number) + '.java'
            row = self.write('work/api1/source-workspace/' + relative, ('source ' + str(number)).encode())
            sources[relative] = row['sha256']
            rows.append(pair.pin(self.root / row['path']))
        source = {'sources': {'fixedSources': rows[:184], 'sharedSources': rows[184:]}}
        base = {'artifact': artifacts['fml']['path'], 'sha256': artifacts['fml']['sha256'],
                'profileSha256': profile['sha256'], 'sourceIdentitySha256': gate.CORE_IDENTITY,
                'candidateIdentity': profile['sha256'], 'candidateIdentityKind': proof['candidateIdentityKind'],
                'installationApproved': False, 'sourceBuildReceipt': receipts['fml']['path'],
                'baseBuildReceipt': receipts['core']['path'], 'sources': sources, 'compilationSources': sources}
        proof['baseReceipt'] = self.write('unit/base-receipt.json', base)
        proof['inputPins'] = [profile, self.write('unit/bound-build.log', b'synthetic log, not execution evidence')]
        return proof, source

    def build_inputs(self, verified):
        with mock.patch.object(gate, 'validate_full_build', return_value=verified), \
                mock.patch.object(pair.forge_fixture, 'verify_result',
                                  return_value=pair.pin(self.root / verified['forgeFixture']['path'])):
            return pair._profile_build_inputs(self.root, 'unit/profile.json', 'unit/proof.json')

    def test_profile_options_are_explicit_paired_and_relative(self):
        self.assertFalse(pair._profile_options(None, None))
        self.assertTrue(pair._profile_options('p.json', 'proof.json'))
        for profile, proof in [('p.json', None), (None, 'proof.json'), ('/p.json', 'proof.json'),
                               ('../p.json', 'proof.json'), ('p.json', 'a//b'), ('p.json', 'a/./b')]:
            with self.subTest(profile=profile, proof=proof), self.assertRaises(ValueError):
                pair._profile_options(profile, proof)

    def test_partial_build_never_prepares_or_creates_outputs(self):
        with mock.patch.object(gate, 'validate_full_build', side_effect=ValueError('Partial build proof')), \
                mock.patch.object(pair, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'Partial build proof'):
                pair.assemble(self.repo, self.root, profile='p.json', build_proof='proof.json',
                              offline_identity_reference='existing unit reference', eula_reference='existing unit acceptance')
            prepare.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_absolute_or_traversing_profile_fails_before_gate(self):
        with mock.patch.object(gate, 'validate_full_build') as verifier:
            with self.assertRaises(ValueError):
                pair._profile_build_inputs(self.root, '../p.json', 'proof.json')
            verifier.assert_not_called()

    def test_verified_relative_inputs_are_bound_to_current_consumer(self):
        verified, _ = self.verified_fixture()
        paths, pins, result = self.build_inputs(verified)
        self.assertEqual(result, verified)
        self.assertEqual(paths['artifact_service'], self.root / 'unit/service.jar')
        self.assertEqual(pins['portableBaseReceipt'], pair.pin(self.root / 'unit/base-receipt.json'))
        self.assertTrue(all(Path(row['path']).is_relative_to(self.root) for row in pins.values()))

    def test_mixed_profile_or_historical_identity_never_enters_inputs(self):
        verified, _ = self.verified_fixture()
        for key, value in [('profileSha256', '0' * 64), ('candidateIdentity', '0' * 64),
                           ('sourceIdentity', pair.IDENTITY), ('runtimeAcceptance', True),
                           ('candidateIdentityKind', 'reviewed-artifact-equivalence-reference')]:
            changed = dict(verified, **{key: value})
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'selected portable profile'):
                self.build_inputs(changed)

    def test_stale_artifact_pin_rejected_even_after_full_gate_return(self):
        verified, _ = self.verified_fixture()
        (self.root / verified['artifacts']['service']['path']).write_bytes(b'changed after verification')
        with self.assertRaisesRegex(ValueError, 'Changed pinned file'):
            self.build_inputs(verified)

    def test_absolute_artifact_and_symlink_rejected(self):
        verified, _ = self.verified_fixture()
        changed = copy.deepcopy(verified)
        changed['artifacts']['game']['path'] = str(self.root / changed['artifacts']['game']['path'])
        with self.assertRaises(ValueError):
            self.build_inputs(changed)
        original = self.root / verified['artifacts']['game']['path']
        target = self.root / 'unit/game-real.jar'
        original.rename(target)
        original.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Redirected'):
            self.build_inputs(verified)

    def test_current_exact_forge_fixture_still_required(self):
        verified, _ = self.verified_fixture()
        with mock.patch.object(gate, 'validate_full_build', return_value=verified), \
                mock.patch.object(pair.forge_fixture, 'verify_result', side_effect=ValueError('changed original Forge ABI')):
            with self.assertRaisesRegex(ValueError, 'Forge ABI'):
                pair._profile_build_inputs(self.root, 'unit/profile.json', 'unit/proof.json')

    def test_full_proof_closure_is_included_and_rehashed(self):
        verified, _ = self.verified_fixture()
        paths, pins, _ = self.build_inputs(verified)
        self.assertIn(self.root / 'unit/bound-build.log', paths.values())
        self.assertIn(pair.pin(self.root / 'unit/bound-build.log'), pins.values())
        (self.root / 'unit/bound-build.log').write_bytes(b'changed proof log')
        with self.assertRaisesRegex(ValueError, 'Changed pinned file'):
            self.build_inputs(verified)

    def test_missing_or_duplicate_full_proof_closure_is_rejected(self):
        verified, _ = self.verified_fixture()
        for closure in ([], [verified['inputPins'][0], verified['inputPins'][0]]):
            with self.subTest(closure=closure), self.assertRaises(ValueError):
                self.build_inputs(dict(verified, inputPins=closure))

    def test_lock_deduplicates_only_identical_refreshed_closure_pins(self):
        record = pair.pin(self.root / self.write('unit/file.bin')['path'])
        rows = pair._assembly_lock_rows(self.root, [record, record], refreshed=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['path'], 'unit/file.bin')
        with self.assertRaisesRegex(ValueError, 'Duplicate or conflicting'):
            pair._assembly_lock_rows(self.root, [record, record])
        with self.assertRaisesRegex(ValueError, 'Duplicate or conflicting'):
            pair._assembly_lock_rows(self.root, [record, dict(record, sha256='0' * 64)], refreshed=True)

    def test_refreshed_path_still_invokes_identical_runtime_and_probe_gates(self):
        verified, _ = self.verified_fixture()
        paths, pins, _ = self.build_inputs(verified)
        for relative in ('work/api1/run/api1-unified-client-build/official-client-launch-seal.json',
                         'work/api1/ci/runtime-restore/native-server-closure.json',
                         'work/api1/ci/runtime-restore/runtime-result.json',
                         pair.compile_probe.OUTPUT_RELATIVE + '/result.json',
                         pair.compile_probe.OUTPUT_RELATIVE + '/' + pair.compile_probe.ARTIFACT_NAME):
            self.write(relative, {'synthetic': 'routing-only'})
        with mock.patch.object(pair, '_verify_runtime_receipts') as runtime, \
                mock.patch.object(pair, '_verify_probe_receipts') as probe:
            result_paths, result_pins = pair._profile_runtime_inputs(self.root, paths, pins)
            runtime.assert_called_once_with(self.root, result_paths, result_pins,
                                            support_relative=pair.REFRESHED_SUPPORT)
            probe.assert_called_once_with(self.root, result_paths, result_pins)
        Path(paths['coreBuildReceipt']).write_bytes(b'changed current receipt')
        with self.assertRaisesRegex(ValueError, 'input changed before assembly'):
            pair._profile_runtime_inputs(self.root, paths, pins)

    def test_missing_runtime_inputs_block_before_any_profile_write(self):
        verified, _ = self.verified_fixture()
        paths, pins, _ = self.build_inputs(verified)
        with self.assertRaisesRegex(ValueError, 'Missing fresh consumer'):
            pair._profile_runtime_inputs(self.root, paths, pins)
        self.assertFalse((self.root / pair.REFRESHED_PROFILES).exists())
        self.assertFalse((self.root / pair.REFRESHED_ASSEMBLED).exists())

    def test_fml_adapter_preserves_portable_source_and_only_localizes_paths(self):
        verified, source = self.verified_fixture()
        paths, pins, _ = self.build_inputs(verified)
        original_bytes = paths['portableBaseReceipt'].read_bytes()
        with mock.patch.object(pair.fml_metadata, 'verify_sources', return_value=source), \
                mock.patch.object(pair.fml_metadata, 'FIXED_FML_SHA', verified['artifacts']['fml']['sha256']):
            adapted_paths, adapted_pins = pair._profile_adapters(self.root, paths, pins, verified)
        base = json.loads(adapted_paths['baseReceipt'].read_text())
        self.assertEqual(base['artifact'], str(self.root / verified['artifacts']['fml']['path']))
        self.assertEqual(base['sourceBuildReceipt'], str(paths['fmlBuildReceipt']))
        self.assertEqual(base['portableReceipt'], verified['baseReceipt'])
        self.assertEqual(base['sources'], json.loads(original_bytes)['sources'])
        self.assertEqual(paths['portableBaseReceipt'].read_bytes(), original_bytes)
        self.assertFalse(base['runtimeAcceptance'])
        self.assertFalse(base['installationApproved'])
        self.assertEqual(adapted_pins['baseReceipt'], pair.pin(adapted_paths['baseReceipt']))
        self.assertFalse((self.root / pair.SUPPORT).exists())

    def test_mixed_base_receipt_and_changed_source_rejected_before_adapter_write(self):
        verified, source = self.verified_fixture()
        paths, pins, _ = self.build_inputs(verified)
        base = json.loads(paths['portableBaseReceipt'].read_text())
        for key, value in [('profileSha256', '0' * 64), ('baseBuildReceipt', 'unit/stale.json'),
                           ('candidateIdentity', pair.fml_metadata.CANDIDATE_IDENTITY), ('installationApproved', True)]:
            self.write('unit/base-receipt.json', dict(base, **{key: value}))
            with self.subTest(field=key), mock.patch.object(pair.fml_metadata, 'FIXED_FML_SHA',
                    verified['artifacts']['fml']['sha256']), self.assertRaises(ValueError):
                pair._profile_adapters(self.root, paths, pins, verified)
            self.assertFalse((self.root / pair.REFRESHED_SUPPORT).exists())
        self.write('unit/base-receipt.json', base)
        Path(source['sources']['fixedSources'][0]['path']).write_bytes(b'changed source')
        with mock.patch.object(pair.fml_metadata, 'verify_sources', return_value=source), \
                mock.patch.object(pair.fml_metadata, 'FIXED_FML_SHA', verified['artifacts']['fml']['sha256']), \
                self.assertRaisesRegex(ValueError, 'source changed'):
            pair._profile_adapters(self.root, paths, pins, verified)
        self.assertFalse((self.root / pair.REFRESHED_SUPPORT).exists())

    def test_stale_adapter_outputs_are_never_reused_or_overwritten(self):
        verified, source = self.verified_fixture()
        paths, pins, _ = self.build_inputs(verified)
        self.write(pair.REFRESHED_SUPPORT + '/refreshed-built-tuple-artifacts.json', b'existing historical or stale unit bytes')
        before = (self.root / pair.REFRESHED_SUPPORT / 'refreshed-built-tuple-artifacts.json').read_bytes()
        with mock.patch.object(pair.fml_metadata, 'verify_sources', return_value=source), \
                mock.patch.object(pair.fml_metadata, 'FIXED_FML_SHA', verified['artifacts']['fml']['sha256']), \
                self.assertRaisesRegex(ValueError, 'existing refreshed assembly adapters'):
            pair._profile_adapters(self.root, paths, pins, verified)
        self.assertEqual((self.root / pair.REFRESHED_SUPPORT / 'refreshed-built-tuple-artifacts.json').read_bytes(), before)
        self.assertFalse((self.root / pair.REFRESHED_SUPPORT / 'refreshed-fml-base-build-receipt.json').exists())

    def test_refreshed_output_cannot_overlap_historical_trees(self):
        for relative in (pair.SUPPORT, pair.PROFILES + '/new', pair.ASSEMBLED, 'work'):
            with self.subTest(relative=relative), mock.patch.object(pair, '_profile_build_inputs') as verify:
                with self.assertRaisesRegex(ValueError, 'preserved historical'):
                    pair.assemble(self.repo, self.root, self.root / relative, profile='p.json', build_proof='proof.json',
                                  offline_identity_reference='existing', eula_reference='existing')
                verify.assert_not_called()

    def test_existing_profile_support_is_rejected_before_preparation(self):
        (self.root / pair.REFRESHED_SUPPORT).mkdir(parents=True)
        with mock.patch.object(pair, '_profile_build_inputs', return_value=({}, {}, {})), \
                mock.patch.object(pair, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'existing refreshed support/profile'):
                pair.assemble(self.repo, self.root, profile='p.json', build_proof='proof.json',
                              offline_identity_reference='existing', eula_reference='existing')
            prepare.assert_not_called()

    def test_historical_default_does_not_call_profile_gate(self):
        with mock.patch.object(pair, '_profile_build_inputs') as verify, \
                mock.patch.object(pair, 'prepare', side_effect=ValueError('historical prepare called')) as prepare:
            with self.assertRaisesRegex(ValueError, 'historical prepare called'):
                pair.assemble(self.repo, self.root, offline_identity_reference='existing', eula_reference='existing')
            prepare.assert_called_once_with(self.repo, self.root)
            verify.assert_not_called()

    def test_prepare_cli_cannot_mislabel_input_profile_as_build_proof(self):
        args = ['pair_assembly.py', 'prepare', '--repo-root', str(self.repo), '--consumer-root', str(self.root),
                '--profile', 'p.json', '--build-proof', 'proof.json']
        with mock.patch.object(sys, 'argv', args), mock.patch.object(pair, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'assemble only'):
                pair.main()
            prepare.assert_not_called()


class FrozenDerivativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = FROZEN / 'assemble_pairs.py'
        if not cls.source_path.is_file():
            raise RuntimeError('Set PAIR_PROFILE_BASE to the exact baseline checkout for frozen tests')
        cls.source = pair.pinned_read(cls.source_path, pair.SOURCE_PINS['assemble_pairs.py']).decode()

    def test_default_derivative_byte_identical_to_historical(self):
        # Computed from exact HEAD 2b8a561 pair source SHA d13dbf94... and the
        # frozen assembler, with only the input-lock digest set to 64 zeroes.
        text, changes = pair._derivative(self.source, '0' * 64)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         '72d48415500ebb696bd63f383774a5cf47805298f81dc7c3da38cfaf37d3bd9e')
        self.assertEqual(pair.IDENTITY, '54e5f302c1bad0de54a6845a50b128d6a2aa9f4fb9d44ec14c84c754d7fb21f6')
        self.assertEqual(pair.TUPLE_PINS, {
            'service': '7fbabf5eb18b590bd5a30410d076fd814f11d03e8842e3327b4468217e275aa7',
            'game': '9dc29ac8a8030f629dd7afea8b744114504a552c4fce022c6199b23a1024e162',
            'fml': '4d697ba080277ed270ddd427102e03da4d6cd58b2b9ed584db010b59f037c2e9',
            'product': 'b20903f821455682ff5fee62491483e833252dc1a4f4caaa15bef51a356f1409'})
        for name, expected in pair.SOURCE_PINS.items():
            pair.pinned_read(FROZEN / name, expected)

    def test_refreshed_derivative_changes_only_declared_five_substitutions(self):
        text, changes = pair._derivative(self.source, '1' * 64,
            tuple_relative=pair.REFRESHED_SUPPORT + '/refreshed-built-tuple-artifacts.json',
            base_relative=pair.REFRESHED_SUPPORT + '/refreshed-fml-base-build-receipt.json',
            profiles_relative=pair.REFRESHED_PROFILES)
        self.assertEqual(len(changes), 5)
        self.assertEqual(sum(row['occurrences'] for row in changes), 6)
        restored = text
        for row in reversed(changes):
            self.assertEqual(restored.count(row['after']), row['occurrences'])
            restored = restored.replace(row['after'], row['before'])
        self.assertEqual(restored, self.source)
        self.assertIn('require(len(apis)==46 and sum(len(r[\'primaryIds\']) for r in apis)==47', text)

    def test_changed_frozen_shape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'substitution shape changed'):
            pair._derivative(self.source.replace("LOCK_SHA = '", "LOCK_SHA='"), '0' * 64)

    def test_runtime_and_probe_gate_bodies_preserved(self):
        # Hashes of normalized AST statements from exact historical d13dbf94...
        # _input_receipts. The runtime support directory is the sole parameter.
        updated = ast.parse(Path(pair.__file__).read_text())
        functions = {x.name: x for x in updated.body if isinstance(x, ast.FunctionDef)}
        def digest(nodes):
            raw = json.dumps([ast.dump(x) for x in nodes], separators=(',', ':')).encode()
            return hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest(functions['_verify_runtime_receipts'].body[2:]),
                         'bf61eff495db84d0749400d46c9d2a0e0bb3527bca8ef27f7c265dace43b2c18')
        self.assertEqual(digest(functions['_verify_probe_receipts'].body[1:]),
                         '60ddd9a50cd3c3bca53fdd96ba4f97193f3101c7ff7fbfebb28ba06b5a96473f')

    def test_both_derivatives_pass_all_frozen_command_transform_checks(self):
        manifest = json.loads(pair.pinned_read(FROZEN / 'source-manifest.json', pair.SOURCE_PINS['source-manifest.json']))
        expected = next(x for x in manifest['files'] if x['path'] == 'test_assembly.py')
        test_path = FROZEN / 'test_assembly.py'
        pair.pinned_read(test_path, expected['sha256'])
        for refreshed in (False, True):
            with self.subTest(refreshed=refreshed), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'consumer'
                support = root / (pair.REFRESHED_SUPPORT if refreshed else pair.SUPPORT)
                support.mkdir(parents=True)
                options = {'tuple_relative': pair.REFRESHED_SUPPORT + '/refreshed-built-tuple-artifacts.json',
                           'base_relative': pair.REFRESHED_SUPPORT + '/refreshed-fml-base-build-receipt.json',
                           'profiles_relative': pair.REFRESHED_PROFILES} if refreshed else {}
                text, _ = pair._derivative(self.source, '0' * 64, **options)
                path = support / 'assemble_pairs.py'
                path.write_text(text)
                derivative = module('pair_derivative_for_test', path)
                self.assertEqual(derivative.ROOT, root)
                with mock.patch.dict(sys.modules, {'assemble_pairs': derivative}):
                    checks = module('frozen_checks_for_test', test_path)
                    suite = unittest.defaultTestLoader.loadTestsFromModule(checks)
                    capture = io.StringIO()
                    result = unittest.TextTestRunner(stream=capture).run(suite)
                self.assertEqual(result.testsRun, 11, capture.getvalue())
                self.assertTrue(result.wasSuccessful(), capture.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
