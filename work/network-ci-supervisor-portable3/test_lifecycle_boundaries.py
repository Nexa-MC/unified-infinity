"""Portable lifecycle regressions with bounded files and fake owned children only."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import supervisor as s
import test_supervisor

HERE = Path(__file__).resolve().parent
BASELINE = (HERE.parent / 'network-pair-assembly-local1/required-text-inputs/work/api1/run/'
            'api1-client-combined-plugin1/config/fabric/indigo-renderer.properties').read_bytes()


def pin(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': s.digest(path)}


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o644)
    path.write_bytes(content)
    path.chmod(0o444)


class RetainedChildRace(unittest.TestCase):
    def exercise(self, polls, error=None, delayed=None, remaining=10):
        identity = {'pid': 123, 'start_ticks': 7, 'pgrp': 123, 'session': 123}
        child = SimpleNamespace(pid=123, poll=Mock(side_effect=polls))
        def wait(timeout):
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 0.2)
            if delayed is None:
                raise subprocess.TimeoutExpired('synthetic-owned-child', timeout)
            return delayed
        child.wait = Mock(side_effect=wait)
        obj = SimpleNamespace(deadline=100 + remaining, logs={},
                              selector=SimpleNamespace(select=lambda _: []),
                              children={'client': child}, report={'exits': {}},
                              identities={'client': identity}, group_members={'client': [identity]},
                              proc=SimpleNamespace(same=Mock(side_effect=error, return_value=identity),
                                                   all_identities=lambda: []))
        with patch.object(s.time, 'monotonic', return_value=100):
            s.Pair.pump(obj, 0)
        return obj, child

    def test_clean_owned_exit_after_identity_race(self):
        for error in (ValueError('Expected live process'), FileNotFoundError(), ProcessLookupError()):
            with self.subTest(error=type(error).__name__):
                obj, child = self.exercise([None, 0], error)
                self.assertEqual(obj.report['exits'], {'client': 0})
                child.wait.assert_not_called()

    def test_delayed_clean_exit_waits_only_for_retained_child(self):
        obj, child = self.exercise([None, None], ValueError('Expected live process'), delayed=0)
        self.assertEqual(obj.report['exits'], {'client': 0})
        child.wait.assert_called_once_with(timeout=0.2)

    def test_wait_is_capped_by_remaining_pair_deadline(self):
        _, child = self.exercise([None, None], ValueError('Expected live process'), delayed=0, remaining=0.05)
        self.assertAlmostEqual(child.wait.call_args.kwargs['timeout'], 0.05)

    def test_nonzero_and_signal_exits_never_forgiven(self):
        for code in (1, -15):
            for polls, error, delayed in (([code], None, None),
                                          ([None, code], ValueError('Expected live process'), None),
                                          ([None, None], ValueError('Expected live process'), code)):
                with self.subTest(code=code, polls=polls), self.assertRaisesRegex(ValueError, 'Nonzero'):
                    self.exercise(polls, error, delayed)

    def test_live_identity_mismatch_malformed_or_denied_never_forgiven(self):
        for error in (ValueError('Process identity changed: start_ticks'),
                      ValueError('Process identity changed: pgrp'),
                      ValueError('Malformed process stat'), PermissionError('Denied')):
            with self.subTest(error=str(error)), self.assertRaises(type(error)):
                self.exercise([None, 0], error)

    def test_unwaitable_child_rejected_with_bounded_wait(self):
        with self.assertRaisesRegex(ValueError, 'reconciliation budget'):
            self.exercise([None, None], ValueError('Expected live process'))

    def test_normal_live_and_already_exited_remain_accepted(self):
        self.assertEqual(self.exercise([None])[0].report['exits'], {})
        self.assertEqual(self.exercise([0])[0].report['exits'], {'client': 0})


class CausalResultObservation(unittest.TestCase):
    def test_absence_is_captured_before_pass_and_not_replaced_after_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'network-control-client-result.json'
            obj = SimpleNamespace(deadline=100, logs={'client': SimpleNamespace(events={})},
                                  spec={'client': {'cwd': folder}}, client_result_absent_monotonic=None,
                                  selector=SimpleNamespace(select=lambda _: []), children={}, identities={},
                                  proc=SimpleNamespace(all_identities=lambda: []))
            with patch.object(s.time, 'monotonic', return_value=1):
                s.Pair.pump(obj, 0)
            self.assertEqual(obj.client_result_absent_monotonic, 1)
            path.write_bytes(b'{}')
            with patch.object(s.time, 'monotonic', return_value=2):
                s.Pair.pump(obj, 0)
            self.assertEqual(obj.client_result_absent_monotonic, 1)
            obj.logs['client'].events['NETWORK_CONTROL_JSON'] = {}
            path.unlink()
            with patch.object(s.time, 'monotonic', return_value=3):
                s.Pair.pump(obj, 0)
            self.assertEqual(obj.client_result_absent_monotonic, 1)


class ConfigBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'client/config/fabric/indigo-renderer.properties'
        self.baseline = self.root / 'pair-seals/indigo-baseline.properties'
        for path in (self.path, self.baseline):
            write(path, BASELINE)
        self.row, self.basepin = pin(self.path), pin(self.baseline)
        self.spec = {'pair_lock': str(self.baseline.parent / 'serial-pair.lock'), 'inputs': [self.basepin]}
        self.receipt = self.root / 'properties.json'

    def verify(self, content=BASELINE, row=None, spec=None, receipt=True):
        write(self.path, content)
        return s.verify_indigo_timestamp(row or self.row, spec or self.spec,
                                        self.receipt if receipt else None, None)

    def test_timestamp_only_with_exact_diff_and_seven_settings(self):
        after = BASELINE.replace(b'#Mon Oct 05 21:09:05 JST 2026\n', b'#Thu Oct 08 07:00:00 UTC 2026\n')
        self.assertEqual(self.verify(after), self.path)
        receipt = json.loads((self.root / 'properties-indigo-timestamp.json').read_text())
        self.assertEqual(receipt['beforeHex'], BASELINE.hex())
        self.assertEqual(receipt['afterHex'], after.hex())
        self.assertEqual(len(receipt['settings']), 7)
        self.assertEqual([line for line in receipt['diff'] if line.startswith(('-', '+')) and not line.startswith(('---', '+++'))],
                         ['-#Mon Oct 05 21:09:05 JST 2026\n', '+#Thu Oct 08 07:00:00 UTC 2026\n'])

    def test_unchanged_indigo_remains_exact(self):
        self.verify()
        receipt = json.loads((self.root / 'properties-indigo-timestamp.json').read_text())
        self.assertTrue(receipt['byteIdentical'])
        self.assertEqual(receipt['diff'], [])

    def test_settings_lines_comments_and_line_endings_rejected(self):
        variants = [BASELINE.replace(b'ambient-occlusion-mode=hybrid', b'ambient-occlusion-mode=flat'),
                    BASELINE + b'new-setting=1\n', BASELINE.replace(b'#Indigo properties file', b'#different header'),
                    BASELINE.replace(b'#Mon Oct 05 21:09:05 JST 2026\n', b'#arbitrary\n'),
                    b''.join(BASELINE.splitlines(keepends=True)[:-1]), BASELINE.replace(b'\n', b'\r\n')]
        for content in variants:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.verify(content)

    def test_unsealed_or_changed_baseline_rejected(self):
        with self.assertRaisesRegex(ValueError, 'baseline must be sealed'):
            self.verify(spec=dict(self.spec, inputs=[]))
        write(self.baseline, BASELINE.replace(b'hybrid', b'flat'))
        with self.assertRaises(ValueError):
            self.verify()

    def test_baseline_bytes_read_must_match_the_exact_verified_pin(self):
        read = s.read_bounded
        def changed_during_read(path, limit):
            return BASELINE.replace(b'hybrid', b'alterd') if Path(path) == self.baseline else read(path, limit)
        with patch.object(s, 'read_bounded', side_effect=changed_during_read), self.assertRaisesRegex(ValueError, 'baseline changed during'):
            self.verify()

    def test_original_pin_and_receipt_are_required(self):
        for row in (dict(self.row, sha256='0' * 64), dict(self.row, bytes=280)):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, 'original Indigo'):
                self.verify(row=row)
        with self.assertRaisesRegex(ValueError, 'evidence required'):
            self.verify(receipt=False)

    def test_symlink_and_writable_untrusted_baseline_rejected(self):
        self.baseline.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.verify()
        self.baseline.chmod(0o444)
        self.path.unlink()
        self.path.symlink_to(self.baseline)
        with self.assertRaisesRegex(ValueError, 'Noncanonical|Symlink'):
            s.verify_indigo_timestamp(self.row, self.spec, self.receipt, None)

    def test_ops_only_allows_exact_empty_array_with_optional_lf(self):
        path = self.root / 'ops.json'
        write(path, b'[]\n')
        row = pin(path)
        for index, content in enumerate((b'[]\n', b'[]')):
            write(path, content)
            s.verify_empty_ops_serialization(row, self.root / ('ops' + str(index) + '.json'), None)
        for content in (b'[ ]', b'[]\r\n', b'[]\n\n', b'{}', b'["player"]', b'null'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                write(path, content)
                s.verify_empty_ops_serialization(row, self.root / 'bad.json', None)

    def test_ops_needs_original_lf_pin_and_receipt(self):
        path = self.root / 'ops.json'
        write(path, b'[]')
        with self.assertRaisesRegex(ValueError, 'original exact'):
            s.verify_empty_ops_serialization(pin(path), self.receipt, None)
        row = dict(pin(path), bytes=3, sha256=hashlib.sha256(b'[]\n').hexdigest())
        with self.assertRaisesRegex(ValueError, 'evidence required'):
            s.verify_empty_ops_serialization(row, None, None)


class FullSpecConfigMembership(unittest.TestCase):
    def setUp(self):
        self.fixture = test_supervisor.SealTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.spec = self.fixture.make_synthetic_spec()
        self.spec.update(target='unified', port=25632)
        command = self.spec['client']['command']
        command[command.index('--quickPlayMultiplayer') + 1] = '127.0.0.1:25632'
        properties = self.root / 'server/server.properties'
        write(properties, properties.read_bytes().replace(b'25631', b'25632'))
        self.spec['inputs'] = [pin(properties) if row['path'] == str(properties) else row for row in self.spec['inputs']]
        self.config = self.root / 'client/config/fabric/indigo-renderer.properties'
        self.baseline = self.root / 'indigo-baseline.properties'
        for path in (self.config, self.baseline):
            write(path, BASELINE)
            self.spec['inputs'].append(pin(path))
        stack = ExitStack()
        self.addCleanup(stack.close)
        digest = hashlib.sha256(b'synthetic-only').hexdigest()
        stack.enter_context(patch.object(s, 'ORIGINAL_MODS', {'a.jar': digest, 'b.jar': digest}))
        stack.enter_context(patch.object(s, 'EMI_MODS', {'unified': ('c.jar', digest)}))
        stack.enter_context(patch.object(s.subprocess, 'Popen', side_effect=AssertionError('No process launch')))
        stack.enter_context(patch.object(s.os, 'killpg', side_effect=AssertionError('No signals')))

    def test_prestart_exact_pin_then_poststart_named_changes(self):
        before = s.capture_server_properties(self.spec)
        write(self.config, BASELINE.replace(b'21:09:05 JST', b'07:00:00 UTC'))
        write(self.root / 'server/ops.json', b'[]')
        with self.assertRaises(ValueError):
            s.capture_server_properties(self.spec)
        pins = s.verify_spec(self.spec, before, self.root / 'poststart.json')
        self.assertEqual(pins[str(self.config)]['sha256'], hashlib.sha256(BASELINE).hexdigest())

    def test_unsealed_config_member_is_still_rejected(self):
        before = s.capture_server_properties(self.spec)
        write(self.config.parent / 'extra.properties', b'extra=true\n')
        with self.assertRaisesRegex(ValueError, 'Unsealed file in immutable tree'):
            s.verify_spec(self.spec, before, self.root / 'poststart.json')

    def test_missing_or_changed_other_config_is_still_rejected(self):
        before = s.capture_server_properties(self.spec)
        other = self.root / 'client/config/neoforge-server.toml'
        write(other, b'advertiseDedicatedServerToLan=true\n')
        with self.assertRaises(ValueError):
            s.verify_spec(self.spec, before, self.root / 'poststart.json')


if __name__ == '__main__':
    unittest.main()
