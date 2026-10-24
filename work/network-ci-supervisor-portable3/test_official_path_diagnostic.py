"""Rejected path categories only, with one owned Python /proc read.

The live observation is mapped synthetically to a fixed label. No lspci,
Java, game, sockets, ptrace, CI, downloads, or runtime acceptance are tested.
"""
import ast
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import supervisor as s
import test_jdk_spawn_transition as fixture
from official_path_preservation import (
    ORIGINAL, REVIEWED, PREDECESSOR_SHA256, without_official_path_diagnostic)

ERROR = 'CPU probe transition target forbidden'
PATH_LABELS = {
    '/usr/bin/lspci': 'PCI_QUERY_USR_BIN_PATH',
    '/usr/sbin/lspci': 'PCI_QUERY_USR_SBIN_PATH',
    '/bin/lspci': 'PCI_QUERY_BIN_PATH',
    '/sbin/lspci': 'PCI_QUERY_SBIN_PATH'}
REAL_POPEN = subprocess.Popen


def predecessor():
    module = ModuleType('official_path_predecessor')
    module.__file__ = s.__file__
    exec(compile(without_official_path_diagnostic(Path(s.__file__).read_text()),
                 s.__file__, 'exec'), module.__dict__)
    return module


class OfficialPathDiagnostic(unittest.TestCase):
    setUp = fixture.SpawnTransition.setUp
    ARGV = s.CPU_PROBE_ARGV
    snapshot = fixture.SpawnTransition.snapshot

    def reject(self, target):
        self.exe.unlink()
        self.exe.symlink_to(target)
        with self.assertRaisesRegex(ValueError, '^' + ERROR + '$') as caught:
            self.snapshot()
        error = caught.exception
        self.assertIs(type(error), ValueError)
        self.assertFalse(error.transition_target_diagnostic['admission_evidence'])
        self.assertFalse(error.transition_target_diagnostic['identity_verified'])
        self.assertEqual(self.pair.report, {})
        return error

    def test_each_exact_path_is_categorical_and_still_rejected(self):
        for target, label in PATH_LABELS.items():
            with self.subTest(target=target):
                error = self.reject(target)
                self.assertEqual(error.transition_target_diagnostic,
                    dict(admission_evidence=False, identity_verified=False,
                         path_label=label, deleted_suffix=False))
                encoded = json.dumps(error.transition_target_diagnostic)
                self.assertNotIn(target, encoded)
                self.assertNotIn('lspci', encoded)

    def test_deleted_exact_paths_are_labeled_not_admitted(self):
        for target, label in PATH_LABELS.items():
            with self.subTest(target=target):
                error = self.reject(target + ' (deleted)')
                self.assertEqual(error.transition_target_diagnostic,
                    dict(admission_evidence=False, identity_verified=False,
                         path_label=label, deleted_suffix=True))

    def test_mismatched_or_unrelated_paths_remain_private_and_unknown(self):
        paths = ('/usr/local/bin/lspci', '/private/secret/lspci', 'lspci',
                 '/usr/bin/LSPCI', '/usr/bin/lspci-extra', '/usr/bin/lspci/',
                 '/usr/bin/./lspci', '/usr/bin/../bin/lspci', '/usr//bin/lspci',
                 '//usr/bin/lspci', '/usr/bin/lspci (deleted) (deleted)',
                 '/usr/bin/lspci (deleted) ', '/private/secret/application')
        for target in paths:
            for suffix in ('', ' (deleted)'):
                with self.subTest(target=target, suffix=suffix):
                    error = self.reject(target + suffix)
                    diagnostic = error.transition_target_diagnostic
                    self.assertEqual(diagnostic['path_label'], 'OTHER_PATH')
                    self.assertEqual(diagnostic['deleted_suffix'],
                                     (target + suffix).endswith(' (deleted)'))
                    encoded = json.dumps(diagnostic)
                    for secret in (target, 'lspci', 'secret', 'application'):
                        self.assertNotIn(secret, encoded)

    def test_parent_and_deleted_helper_lshw_labels_are_unchanged(self):
        for target, label in ((str(self.java), 'PARENT_COMMAND_PATH'),
                              (str(self.java) + ' (deleted)', 'PARENT_COMMAND_PATH'),
                              (str(self.spawn) + ' (deleted)', 'OTHER_PATH'),
                              (s.CPU_PROBE_PATH + ' (deleted)', 'OTHER_PATH')):
            with self.subTest(target=target):
                error = self.reject(target)
                self.assertEqual(error.transition_target_diagnostic['path_label'], label)

    def test_exact_helper_and_lshw_sampling_behavior_is_unchanged(self):
        self.assertFalse(self.snapshot())
        fixture.SpawnTransition.target(self)
        self.assertTrue(self.snapshot())
        self.assertEqual(self.pair.report, {})

    def exercise(self, module, target):
        trace = []
        observed_target = False
        proc = module.Proc(self.root)
        pair = SimpleNamespace(**dict(vars(self.pair), proc=proc))
        # Only the pre-existing setup and identity reads are fixture-backed.
        # Both implementations run against exactly the same synthetic proc tree.
        with ExitStack() as stack:
            for name in ('JDK_SPAWN_BYTES', 'JDK_SPAWN_SHA256', 'clean_path'):
                stack.enter_context(patch.object(module, name, getattr(s, name)))
            for owner, name in ((module, 'read_bounded'), (module, 'preparation_root'),
                                (module, 'owned_preparation_access'),
                                (proc, 'same'), (module.os, 'stat'),
                                (module.os, 'open'), (module.os, 'read'),
                                (module.os, 'fstat')):
                original = getattr(owner, name)
                def traced(*args, _name=name, _original=original, **kwargs):
                    self.assertFalse(observed_target, 'Unexpected extra operation: ' + _name)
                    trace.append((_name, repr(args), repr(kwargs)))
                    return _original(*args, **kwargs)
                stack.enter_context(patch.object(owner, name, side_effect=traced))
            def observed(path):
                nonlocal observed_target
                self.assertFalse(observed_target, 'Unexpected repeated target read')
                trace.append(('readlink', str(path)))
                self.assertEqual(Path(path), self.exe)
                observed_target = True
                return target
            stack.enter_context(patch.object(module.os, 'readlink', side_effect=observed))
            # Rejecting the new categories must never open/hash the target or
            # add canonicalization, fresh reads, delays, or an admission sample.
            for owner, name in ((Path, 'resolve'),
                                (module.os.path, 'realpath'), (module, 'digest'),
                                (module.hashlib, 'sha256'), (module.time, 'sleep'),
                                (module, 'cpu_probe_sample')):
                stack.enter_context(patch.object(owner, name,
                    side_effect=AssertionError('Unexpected extra operation: ' + name)))
            stack.enter_context(patch.object(module.time, 'monotonic', return_value=10))
            with self.assertRaisesRegex(ValueError, '^' + ERROR + '$') as caught:
                module.cpu_probe_spawn_sample(
                    pair, self.helper, self.parent, self.command, 11)
        return caught.exception, trace

    def test_rejection_io_trace_matches_exact_predecessor(self):
        old = predecessor()
        targets = tuple(PATH_LABELS) + tuple(p + ' (deleted)' for p in PATH_LABELS)
        targets += ('/private/secret/lspci', str(self.java), str(self.spawn) + ' (deleted)')
        for target in targets:
            with self.subTest(target=target):
                before, before_trace = self.exercise(old, target)
                after, after_trace = self.exercise(s, target)
                self.assertEqual(type(after), type(before))
                self.assertEqual(str(after), str(before))
                self.assertEqual(after_trace, before_trace)
                self.assertEqual(sum(row[0] == 'readlink' for row in after_trace), 1)
                self.assertFalse(after.transition_target_diagnostic['admission_evidence'])
                self.assertFalse(after.transition_target_diagnostic['identity_verified'])

    def test_forwarding_is_in_memory_only_and_does_not_expose_paths(self):
        error = self.reject('/usr/bin/lspci')
        with patch.object(s.os, 'readlink', side_effect=AssertionError('No reread')), \
             patch.object(s, 'read_bounded', side_effect=AssertionError('No read')):
            result = s.cpu_probe_failure_diagnostic(error, self.helper, {})
        self.assertIs(result['transition_target_diagnostic'], error.transition_target_diagnostic)
        self.assertFalse(result['admission_evidence'])
        self.assertFalse(result['previously_verified'])
        self.assertNotIn('lspci', json.dumps(result))
        self.assertNotIn('/usr/bin', json.dumps(result))

    def test_identity_mismatch_precedes_path_observation_and_claim(self):
        original = ValueError('Process identity changed: start_ticks')
        with patch.object(self.proc, 'same', side_effect=original), \
             patch.object(s.os, 'readlink', side_effect=AssertionError('No target read')) as read:
            with self.assertRaises(ValueError) as caught:
                self.snapshot()
        self.assertIs(caught.exception, original)
        read.assert_not_called()
        self.assertFalse(hasattr(caught.exception, 'transition_target_diagnostic'))

    def test_readlink_denial_propagates_without_retry_or_path_claim(self):
        original = PermissionError('synthetic observation denied')
        with patch.object(s.os, 'readlink', side_effect=original) as read:
            with self.assertRaises(PermissionError) as caught:
                self.snapshot()
        self.assertIs(caught.exception, original)
        read.assert_called_once_with(self.exe)
        self.assertFalse(hasattr(caught.exception, 'transition_target_diagnostic'))

    def test_real_owned_proc_read_with_synthetic_category_mapping(self):
        child = REAL_POPEN([sys.executable, '-I', '-S', '-c',
            'import signal,sys; signal.alarm(5); sys.stdin.buffer.read(1)'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        observed = []
        real_path = Path('/proc') / str(child.pid) / 'exe'
        def observe(path):
            self.assertEqual(Path(path), self.exe)
            self.assertIsNone(child.poll())
            observed.append(fixture.REAL_READLINK(real_path))
            # Only infrastructure is real. This mapping is not lspci evidence.
            return '/usr/bin/lspci'
        try:
            with patch.object(s.os, 'readlink', side_effect=observe):
                with self.assertRaisesRegex(ValueError, '^' + ERROR + '$') as caught:
                    self.snapshot()
            self.assertEqual(len(observed), 1)
            self.assertTrue(Path(observed[0]).is_absolute())
            self.assertNotIn(observed[0], PATH_LABELS)
            diagnostic = caught.exception.transition_target_diagnostic
            self.assertEqual(diagnostic, dict(admission_evidence=False,
                identity_verified=False, path_label='PCI_QUERY_USR_BIN_PATH', deleted_suffix=False))
            self.assertNotIn(observed[0], json.dumps(diagnostic))
            child.communicate(input=b'x', timeout=2)
            self.assertEqual(child.returncode, 0)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=2)


class ExactPreservation(unittest.TestCase):
    def test_exact_predecessor_hash(self):
        original = without_official_path_diagnostic(Path(s.__file__).read_text())
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), PREDECESSOR_SHA256)

    def test_reversal_rejects_missing_changed_and_duplicate_delta(self):
        source = Path(s.__file__).read_text()
        mutations = [source + source, source.replace(REVIEWED, ORIGINAL, 1)]
        for needle in ('/usr/bin/lspci', '/usr/sbin/lspci', '/bin/lspci', '/sbin/lspci',
                       'PCI_QUERY_USR_BIN_PATH', 'PCI_QUERY_USR_SBIN_PATH',
                       'PCI_QUERY_BIN_PATH', 'PCI_QUERY_SBIN_PATH',
                       ".get(label, 'OTHER_PATH')"):
            mutations.append(source.replace(needle, 'UNREVIEWED', 1))
        for changed in mutations:
            with self.subTest(changed=hashlib.sha256(changed.encode()).hexdigest()):
                with self.assertRaises(ValueError):
                    without_official_path_diagnostic(changed)

    def test_only_path_label_value_changes_in_entire_source_ast(self):
        source = Path(s.__file__).read_text()
        previous = without_official_path_diagnostic(source)
        tree = ast.parse(source)
        old_tree = ast.parse(previous)
        replaced = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for index, key in enumerate(node.keys):
                    if isinstance(key, ast.Constant) and key.value == 'path_label':
                        node.values[index] = ast.parse(
                            "'PARENT_COMMAND_PATH' if label == command[0] else 'OTHER_PATH'",
                            mode='eval').body
                        replaced += 1
        self.assertEqual(replaced, 1)
        self.assertEqual(ast.dump(tree), ast.dump(old_tree))


if __name__ == '__main__':
    unittest.main()
