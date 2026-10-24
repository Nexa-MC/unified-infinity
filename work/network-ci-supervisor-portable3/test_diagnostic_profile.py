"""Diagnostic provenance fixtures only: no game, subprocess, socket or signals."""
import ast
import copy
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import supervisor as s
import test_supervisor


class DiagnosticProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_supervisor.SealTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.spec = self.fixture.make_synthetic_spec()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        sha = hashlib.sha256(b'synthetic-only').hexdigest()
        self.stack.enter_context(patch.object(s, 'ORIGINAL_MODS', {'a.jar': sha, 'b.jar': sha}))
        self.stack.enter_context(patch.object(s, 'EMI_MODS', {'native-neoforge': ('c.jar', sha)}))
        self.stack.enter_context(patch('supervisor.subprocess.Popen', side_effect=AssertionError('No subprocess')))
        self.stack.enter_context(patch('supervisor.os.killpg', side_effect=AssertionError('No process signal')))
        self.manifest = self.root / 'diagnostic-manifest.json'
        self.body = {'schema': 'fml-process-start-diagnostic-v1', 'diagnostic_only': True,
                     'baseline_acceptance': False, 'build_receipts': []}
        for name in ('native-build.json', 'unified-build.json'):
            # Contents intentionally not JSON: semantic parsing belongs to the producer.
            row = self.pin(self.root / name, b'producer-owned receipt semantics')
            self.body['build_receipts'].append(row)
        self.publish_manifest()

    def pin(self, path, raw):
        if path.exists():
            path.chmod(0o644)
        path.write_bytes(raw)
        path.chmod(0o444)
        row = {'path': str(path), 'bytes': len(raw), 'sha256': s.digest(path)}
        self.spec['inputs'] = [p for p in self.spec['inputs'] if p['path'] != str(path)] + [row]
        return row

    def publish_manifest(self, raw=None):
        row = self.pin(self.manifest, raw if raw is not None else json.dumps(self.body).encode())
        self.spec['diagnostic_profile'] = {'manifest_path': row['path'], 'manifest_sha256': row['sha256'],
                                           'diagnostic_only': True, 'baseline_acceptance': False}

    def test_valid_v1_and_v2_keep_all_ordinary_gates(self):
        s.verify_spec(self.spec)
        self.spec.update(schema='network-ci-pair-v2', preparation_roots=[str(self.root)], jdk_legal_links=[])
        s.verify_spec(self.spec)
        for mutate in (lambda p: p['server']['command'].append('-javaagent:forbidden'),
                       lambda p: p['server']['environment'].update(JAVA_TOOL_OPTIONS='forbidden'),
                       lambda p: p.update(port=25632)):
            changed = copy.deepcopy(self.spec)
            mutate(changed)
            with self.assertRaises(ValueError):
                s.verify_spec(changed)

    def test_absent_profile_preserves_old_spec_and_report_shape(self):
        del self.spec['diagnostic_profile']
        s.verify_spec(self.spec)
        self.assertEqual(s.diagnostic_report_fields(self.spec), {})
        pair = s.Pair(self.spec, self.root)
        self.addCleanup(pair.selector.close)
        self.assertEqual(pair.report, {'schema': 1, 'target': 'native-neoforge', 'status': 'INCONCLUSIVE',
                                      'passed': False, 'game_launched': False, 'phase': 'preflight',
                                      'observations': [], 'exits': {}, 'cleanup_signals': []})

    def test_profile_unknown_missing_null_and_bad_fields_rejected(self):
        original = copy.deepcopy(self.spec['diagnostic_profile'])
        cases = [None, {}, dict(original, extra=True)]
        for key in original:
            cases.append({k: v for k, v in original.items() if k != key})
        for value in (False, 1, 'true', None):
            cases.append(dict(original, diagnostic_only=value))
        for value in (True, 0, 'false', None):
            cases.append(dict(original, baseline_acceptance=value))
        for value in ('relative.json', '', 5):
            cases.append(dict(original, manifest_path=value))
        for value in ('0'*63, 'A'*64, 17, None):
            cases.append(dict(original, manifest_sha256=value))
        for profile in cases:
            with self.subTest(profile=profile), self.assertRaises((ValueError, OSError)):
                s.verify_spec(dict(self.spec, diagnostic_profile=profile))

    def test_manifest_must_be_pinned_and_digest_must_match(self):
        changed = copy.deepcopy(self.spec)
        changed['inputs'] = [p for p in changed['inputs'] if p['path'] != str(self.manifest)]
        with self.assertRaisesRegex(ValueError, 'existing sealed input'):
            s.verify_spec(changed)
        changed = copy.deepcopy(self.spec)
        changed['diagnostic_profile']['manifest_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'existing sealed input'):
            s.verify_spec(changed)
        self.manifest.chmod(0o644)
        self.manifest.write_bytes(b'changed')
        self.manifest.chmod(0o444)
        with self.assertRaises(ValueError):
            s.verify_spec(self.spec)
        self.manifest.unlink()
        with self.assertRaises(FileNotFoundError):
            s.verify_spec(self.spec)

    def test_manifest_header_unknown_missing_or_bad_boolean_rejected(self):
        original = copy.deepcopy(self.body)
        cases = [dict(original, extra=True), dict(original, schema='other'),
                 dict(original, diagnostic_only=1), dict(original, baseline_acceptance=0)]
        cases += [{k: v for k, v in original.items() if k != key} for key in original]
        for body in cases:
            with self.subTest(body=body):
                self.body = body
                self.publish_manifest()
                with self.assertRaises(ValueError):
                    s.verify_spec(self.spec)

    def test_two_distinct_exact_build_receipt_pins_required(self):
        original = copy.deepcopy(self.body['build_receipts'])
        cases = [[], original[:1], original + [original[0]], [original[0], original[0]], None,
                 [dict(original[0], extra=True), original[1]],
                 [dict(original[0], path='relative'), original[1]],
                 [dict(original[0], bytes=True), original[1]],
                 [dict(original[0], sha256='0'*64), original[1]],
                 [dict(original[0], bytes=original[0]['bytes']+1), original[1]]]
        for receipts in cases:
            with self.subTest(receipts=receipts):
                self.body['build_receipts'] = receipts
                self.publish_manifest()
                with self.assertRaises(ValueError):
                    s.verify_spec(self.spec)

    def test_build_receipts_cannot_be_unpinned_missing_or_changed(self):
        path = Path(self.body['build_receipts'][0]['path'])
        changed = copy.deepcopy(self.spec)
        changed['inputs'] = [r for r in changed['inputs'] if r['path'] != str(path)]
        with self.assertRaisesRegex(ValueError, 'sealed input'):
            s.verify_spec(changed)
        path.chmod(0o644)
        path.write_bytes(b'x' * self.body['build_receipts'][0]['bytes'])
        path.chmod(0o444)
        with self.assertRaisesRegex(ValueError, 'digest changed'):
            s.verify_spec(self.spec)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            s.verify_spec(self.spec)

    def test_manifest_bound_duplicate_keys_and_midread_change_rejected(self):
        self.publish_manifest(b' '*(16*1024+1))
        with self.assertRaisesRegex(ValueError, 'byte bound'):
            s.verify_spec(self.spec)
        self.publish_manifest(b'{"schema":1,"schema":2}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            s.verify_spec(self.spec)
        self.publish_manifest()
        with patch.object(s, 'read_bounded', return_value=b'{}'):
            with self.assertRaisesRegex(ValueError, 'changed during verification'):
                s.verify_diagnostic_profile(self.spec, {r['path']: r for r in self.spec['inputs']})

    def test_symlink_manifest_and_receipt_rejected(self):
        for path in (self.manifest, Path(self.body['build_receipts'][0]['path'])):
            with self.subTest(path=path):
                saved = path.with_suffix('.saved')
                path.rename(saved)
                path.symlink_to(saved)
                with self.assertRaises((ValueError, OSError)):
                    s.verify_spec(self.spec)
                path.unlink()
                saved.rename(path)

    def test_report_labels_are_copied_and_survive_failure_receipt(self):
        s.verify_spec(self.spec)
        expected = copy.deepcopy(self.spec['diagnostic_profile'])
        pair = s.Pair(self.spec, self.root)
        self.spec['diagnostic_profile']['manifest_sha256'] = 'f'*64
        self.assertEqual(pair.report['diagnostic_profile'], expected)
        with patch.object(s, 'verify_pair_seal', side_effect=ValueError('synthetic preflight failure')), \
                patch.object(pair, 'cleanup') as cleanup, patch.object(s.signal, 'setitimer'), \
                patch.object(s.signal, 'signal'):
            report = pair.run('a'*64, self.root/'unused-seal.json')
        cleanup.assert_called_once()
        self.assertEqual(report, json.loads((self.root/'result.json').read_text()))
        self.assertEqual(report['diagnostic_profile'], expected)
        self.assertIs(report['diagnostic_only'], True)
        self.assertIs(report['baseline_acceptance'], False)
        self.assertIs(report['passed'], False)
        self.assertIs(report['game_launched'], False)
        self.assertIn('synthetic preflight failure', report['failure'])

    def test_success_status_cannot_remove_diagnostic_labels(self):
        pair = s.Pair(self.spec, self.root)
        self.addCleanup(pair.selector.close)
        pair.report.update(passed=True, status='PASS', phase='complete')
        self.assertIs(pair.report['diagnostic_only'], True)
        self.assertIs(pair.report['baseline_acceptance'], False)

    def test_static_console_receipt_is_labelled_only_for_diagnostic_spec(self):
        for diagnostic in (True, False):
            spec = copy.deepcopy(self.spec)
            if not diagnostic:
                del spec['diagnostic_profile']
            path = self.root / ('static-' + str(diagnostic) + '.json')
            path.write_text(json.dumps(spec))
            path.chmod(0o444)
            with patch.object(sys, 'argv', ['supervisor.py', '--spec', str(path), '--sha256', s.digest(path)]), \
                    patch('sys.stdout', new_callable=io.StringIO) as output:
                self.assertEqual(s.main(), 0)
            receipt = json.loads(output.getvalue())
            expected = {'status': 'STATIC_INPUTS_VERIFIED_ONLY', 'game_launched': False,
                        'runtime_evidence_observed': False, 'passed': False}
            if diagnostic:
                expected.update(s.diagnostic_report_fields(spec))
            self.assertEqual(receipt, expected)

    def test_only_provenance_insertions_change_old_validation_and_reporting(self):
        # AST digest of reviewed candidate1209 supervisor source SHA256
        # 1b489c7cd6db677cb067cc6f3d564c2e813baacaada2b4d583d911953aee7183.
        # A fixed digest keeps the test portable without a sibling checkout.
        baseline_ast_sha = 'f8ae1276e4929dd42ddf2e2fcf46dbd12ad70086746578f99d07927f84327b3e'
        new = ast.parse(Path(s.__file__).read_text())
        class RemoveProvenance(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                if node.name in ('diagnostic_report_fields', 'verify_diagnostic_profile'):
                    return None
                return self.generic_visit(node)

            def visit_If(self, node):
                if ast.unparse(node.test) == "'diagnostic_profile' in spec":
                    return None
                return self.generic_visit(node)

            def visit_Expr(self, node):
                text = ast.unparse(node)
                if text in ('verify_diagnostic_profile(spec, pins)',
                            'self.report.update(diagnostic_report_fields(spec))'):
                    return None
                return self.generic_visit(node)

            def visit_Dict(self, node):
                rows = [(key, value) for key, value in zip(node.keys, node.values)
                        if not (key is None and ast.unparse(value) == 'diagnostic_report_fields(spec)')]
                node.keys, node.values = [r[0] for r in rows], [r[1] for r in rows]
                return self.generic_visit(node)
        normalized = RemoveProvenance().visit(new)
        self.assertEqual(hashlib.sha256(ast.dump(normalized).encode()).hexdigest(), baseline_ast_sha)


if __name__ == '__main__':
    unittest.main()
