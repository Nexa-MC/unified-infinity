"""SYNTHETIC unit fixtures only: no graphics, subprocess, game or package fetch."""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import graphics_preflight as g

ROOT = Path(__file__).resolve().parent
SUPERVISOR = ROOT.parent / 'network-ci-supervisor-portable3/supervisor.py'
S = g.load_supervisor(SUPERVISOR)
GOOD = '''name of display: :91
display: :91  screen: 0
direct rendering: Yes
OpenGL renderer string: llvmpipe (LLVM 19.1.7, 256 bits)
OpenGL core profile version string: 4.5 (Core Profile) Mesa SYNTHETIC
'''


def setUpModule():
    global PROCESS_GUARD
    PROCESS_GUARD = patch.object(g.subprocess, 'Popen', side_effect=AssertionError('No native process in SYNTHETIC tests'))
    PROCESS_GUARD.start()


def tearDownModule():
    PROCESS_GUARD.stop()


class ParserTests(unittest.TestCase):
    def test_observed_direct_llvmpipe(self):
        result = g.parse_glxinfo(GOOD, ':91')
        self.assertTrue(result['direct_rendering'])
        self.assertEqual(result['renderer'], 'llvmpipe (LLVM 19.1.7, 256 bits)')

    def test_wrong_or_ambiguous_actual_observations_fail(self):
        cases = [GOOD.replace('Yes', 'No'), GOOD.replace('llvmpipe', 'hardware'),
                 GOOD.replace('name of display: :91', 'name of display: :92'),
                 GOOD + 'direct rendering: Yes\n',
                 GOOD.replace('4.5 (Core Profile)', '2.1'),
                 GOOD.replace('OpenGL core profile version string:', 'other:'),
                 'llvmpipe\n', 'x' * (g.MAX_LOG + 1)]
        for text in cases:
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                g.parse_glxinfo(text, ':91')

    def test_budget_uses_two_actual_peaks_plus_slack(self):
        self.assertEqual(g.measured_reserve(61 * g.MIB, 87 * g.MIB), 404 * g.MIB)
        for value in (0, -1, True, None):
            with self.assertRaises(ValueError):
                g.measured_reserve(value, 100)

    def test_loader_trace_resolves_actual_library_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libSynthetic.so'
            path.write_bytes(b'SYNTHETIC')
            alias = Path(directory) / 'alias.so'
            alias.symlink_to(path)
            text = '  812: calling init: ' + str(alias) + '\n'
            self.assertEqual(g.traced_libraries(text), {str(path.resolve())})
        with self.assertRaises(ValueError):
            g.traced_libraries('library searches alone do not establish loading')


class LockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.pins = []
        def pin(name, data, mode=0o444):
            path = root / name
            path.write_bytes(data)
            path.chmod(mode)
            self.pins.append({'path': str(path), 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
            return str(path)
        xvfb = pin('Xvfb', b'SYNTHETIC Xvfb input, not executable program', 0o555)
        glxinfo = pin('glxinfo.x86_64-linux-gnu', b'SYNTHETIC glxinfo input', 0o555)
        library = pin('libSynthetic.so', b'SYNTHETIC library')
        packages = []
        for name in ('xvfb', 'mesa-utils-bin', 'libgl1-mesa-dri'):
            packages.append({'package': name, 'version': '1-synthetic', 'architecture': 'amd64',
                             'uri': 'https://snapshot.ubuntu.com/ubuntu/20260927T000000Z/pool/universe/' + name + '.deb',
                             'bytes': 1, 'sha256': hashlib.sha256(name.encode()).hexdigest()})
        receipt = {'schema': 1, 'status': 'VERIFIED_UBUNTU_CLOSURE', 'snapshot': '20260927T000000Z',
                   'signed_index_review_reference': 'SYNTHETIC input parser test only', 'packages': packages,
                   'file_packages': {xvfb: 'xvfb:amd64=1-synthetic',
                                     glxinfo: 'mesa-utils-bin:amd64=1-synthetic',
                                     library: 'libgl1-mesa-dri:amd64=1-synthetic'}}
        provenance = pin('provenance.json', json.dumps(receipt).encode())
        self.lock = {'schema': 'network-graphics-lock-v1', 'status': 'COMPLETE_REVIEWED',
                     'review_reference': 'SYNTHETIC test only; not approval',
                     'expected_runner': {'ImageOS': 'ubuntu24', 'ImageVersion': '20260927.320.1',
                                         'machine': 'x86_64'}, 'display': ':91', 'inputs': self.pins,
                     'tools': {'xvfb': xvfb, 'glxinfo': glxinfo}, 'package_provenance': provenance}

    def tearDown(self):
        self.directory.cleanup()

    def test_exact_synthetic_input_schema(self):
        self.assertEqual(len(g.validate_lock(self.lock, S)), 4)

    def test_moving_image_incomplete_closure_and_extra_fields_fail(self):
        mutations = [('status', 'INCOMPLETE'), ('display', 'localhost:91'),
                     ('environment', {'MESA_GL_VERSION_OVERRIDE': '4.6'})]
        for key, value in mutations:
            lock = copy.deepcopy(self.lock)
            lock[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                g.validate_lock(lock, S)
        lock = copy.deepcopy(self.lock)
        lock['expected_runner']['ImageVersion'] = 'latest'
        with self.assertRaises(ValueError):
            g.validate_lock(lock, S)

    def test_unreviewed_file_change_fails(self):
        path = Path(self.lock['tools']['xvfb'])
        path.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            g.validate_lock(self.lock, S)
        path.write_bytes(b'changed')
        path.chmod(0o555)
        with self.assertRaises(ValueError):
            g.validate_lock(self.lock, S)

    def test_incomplete_provenance_fails_before_graphics(self):
        lock = copy.deepcopy(self.lock)
        lock['inputs'].pop(2)
        with self.assertRaisesRegex(ValueError, 'Every tool/library'):
            g.validate_lock(lock, S)

    def test_local_runtime_is_rejected_without_spawning(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(g, 'OwnedChild') as spawn:
            with self.assertRaisesRegex(ValueError, 'GitHub CI'):
                g.execute(self.lock, {}, S, Path(self.directory.name) / 'unused')
            spawn.assert_not_called()

    def test_changed_runner_is_rejected_without_spawning(self):
        env = {'GITHUB_ACTIONS': 'true', 'ImageOS': 'ubuntu24', 'ImageVersion': '20261004.1.1'}
        with patch.dict(os.environ, env, clear=True), patch.object(g, 'OwnedChild') as spawn:
            with self.assertRaisesRegex(ValueError, 'Runner image changed'):
                g.execute(self.lock, {}, S, Path(self.directory.name) / 'unused')
            spawn.assert_not_called()

    def test_absent_cgroup_capability_fails_before_spawning(self):
        env = {'GITHUB_ACTIONS': 'true', 'ImageOS': 'ubuntu24', 'ImageVersion': '20260927.320.1'}
        with patch.dict(os.environ, env, clear=True), patch.object(g, 'OwnedChild') as spawn, \
                patch.object(S, 'memory_gate', side_effect=ValueError('bounded cgroup missing')):
            with self.assertRaisesRegex(ValueError, 'bounded cgroup missing'):
                g.execute(self.lock, {}, S, Path(self.directory.name) / 'unused')
            spawn.assert_not_called()

    def test_receipt_is_bounded_for_unchanged_supervisor(self):
        with self.assertRaisesRegex(ValueError, 'frozen consumer bound'):
            g.write_receipt(Path(self.directory.name), 'oversized.json', {'data': 'x' * 8192}, S, 8192)
        self.assertFalse((Path(self.directory.name) / 'oversized.json').exists())


class OwnershipTests(unittest.TestCase):
    def test_wait4_measures_exact_child_peak(self):
        child = object.__new__(g.OwnedChild)
        child.pid, child.result, child.process = 444, None, Mock()
        with patch.object(os, 'wait4', return_value=(444, 0, types.SimpleNamespace(ru_maxrss=1234))) as wait:
            self.assertEqual(child.reap(), {'returncode': 0, 'peak_rss_bytes': 1234 * 1024})
            wait.assert_called_once_with(444, os.WNOHANG)
            child.reap()
            self.assertEqual(wait.call_count, 1)

    def test_cleanup_uses_owned_pidfd_only(self):
        child = object.__new__(g.OwnedChild)
        child.pid, child.fd = 444, 81
        child.reap = Mock(side_effect=[None, {'returncode': 0}, {'returncode': 0}])
        with patch.object(signal, 'pidfd_send_signal') as send, patch.object(os, 'close') as close, \
                patch.object(os, 'kill') as kill, patch.object(os, 'killpg') as killpg:
            child.stop()
            send.assert_called_once_with(81, signal.SIGTERM)
            close.assert_called_once_with(81)
            kill.assert_not_called()
            killpg.assert_not_called()

    def test_already_reaped_child_is_never_signalled(self):
        child = object.__new__(g.OwnedChild)
        child.pid, child.fd = 444, 81
        child.reap = Mock(return_value={'returncode': 0})
        with patch.object(signal, 'pidfd_send_signal') as send, patch.object(os, 'close'):
            child.stop()
            send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
