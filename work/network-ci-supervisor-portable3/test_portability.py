"""Synthetic filesystem/proc and permission models only; no process or signal."""
import ast
from contextlib import ExitStack
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import supervisor as s


_forbid_launch = patch('supervisor.subprocess.Popen', side_effect=AssertionError('Synthetic tests never launch subprocesses'))
_forbid_signal = patch('supervisor.os.killpg', side_effect=AssertionError('Synthetic tests never send process signals'))


def setUpModule():
    _forbid_launch.start()
    _forbid_signal.start()


def tearDownModule():
    _forbid_signal.stop()
    _forbid_launch.stop()


class PortableInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('supervisor.subprocess.Popen', side_effect=AssertionError('No real process')))
        self.stack.enter_context(patch('supervisor.os.killpg', side_effect=AssertionError('No real signal')))
        self.path = self.root / 'system/tool'
        self.path.parent.mkdir()
        self.path.write_bytes(b'SYNTHETIC PINNED ROOT PACKAGE FILE')
        self.pin = {'path': str(self.path), 'bytes': self.path.stat().st_size, 'sha256': s.digest(self.path)}

    def permissions(self, mode=0o755, uid=0, writable=False, parent_writable=False, readable=True):
        original_stat = Path.stat
        def file_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == self.path:
                fields = list(result)
                fields[0] = stat.S_IFREG | mode
                fields[4] = uid
                return os.stat_result(fields)
            return result
        def access(path, kind, *, effective_ids):
            self.assertTrue(effective_ids)
            if Path(path) == self.path:
                return readable if kind == os.R_OK else writable
            return parent_writable and Path(path) == self.path.parent
        self.stack.enter_context(patch.object(Path, 'stat', file_stat))
        runner = self.stack.enter_context(patch.object(s, 'unprivileged_runner', return_value={'uid': 1001, 'gid': 1001}))
        checked = self.stack.enter_context(patch('supervisor.os.access', side_effect=access))
        return runner, checked

    def test_standard_root_owned_readable_0644_and_0755_pass(self):
        for mode in (0o644, 0o755):
            with self.subTest(mode=oct(mode)):
                with ExitStack() as temporary:
                    prior, self.stack = self.stack, temporary
                    runner, access = self.permissions(mode=mode)
                    self.assertEqual(s.file_pin(self.pin), self.path)
                    runner.assert_called_once()
                    access.assert_any_call(self.path, os.W_OK, effective_ids=True)
                    self.stack = prior

    def test_actually_writable_root_file_rejected(self):
        self.permissions(writable=True)
        with self.assertRaisesRegex(ValueError, 'actually writable'):
            s.file_pin(self.pin)

    def test_unreadable_system_file_rejected(self):
        self.permissions(readable=False)
        with self.assertRaisesRegex(ValueError, 'readable'):
            s.file_pin(self.pin)

    def test_replaceable_system_file_rejected(self):
        self.permissions(parent_writable=True)
        with self.assertRaisesRegex(ValueError, 'writable parent'):
            s.file_pin(self.pin)

    def test_runner_owned_mutable_input_still_requires_readonly_seal(self):
        runner, access = self.permissions(uid=1001)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            s.file_pin(self.pin)
        runner.assert_not_called()
        access.assert_not_called()

    def test_nonstandard_group_write_and_setid_modes_rejected(self):
        for mode in (0o664, 0o777, 0o4755, 0o2755, 0o600):
            with self.subTest(mode=oct(mode)), ExitStack() as temporary:
                prior, self.stack = self.stack, temporary
                self.permissions(mode=mode)
                with self.assertRaisesRegex(ValueError, 'read-only'):
                    s.file_pin(self.pin)
                self.stack = prior

    def test_system_file_hash_and_size_still_exact(self):
        self.permissions()
        for pin in (dict(self.pin, sha256='0'*64), dict(self.pin, bytes=self.pin['bytes']+1)):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                s.file_pin(pin)

    def test_missing_actual_access_evidence_fails_closed(self):
        self.permissions()
        with patch('supervisor.os.access', side_effect=PermissionError('synthetic denied')):
            with self.assertRaises(PermissionError):
                s.file_pin(self.pin)


class RunnerIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'self').mkdir()
        self.identity = 'Uid:\t1001\t1001\t1001\t1001\nGid:\t1001\t1001\t1001\t1001\n'
        self.capabilities = ''.join(k + ':\t0000000000000000\n' for k in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb'))
        (self.root / 'self/status').write_text(self.identity + self.capabilities)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('supervisor.os.getresuid', return_value=(1001, 1001, 1001)))
        self.stack.enter_context(patch('supervisor.os.getresgid', return_value=(1001, 1001, 1001)))

    def test_nonroot_matching_identity_passes(self):
        self.assertEqual(s.unprivileged_runner(self.root), {'uid': 1001, 'gid': 1001, 'capabilities': 'none'})

    def test_root_effective_saved_or_group_mismatch_rejected(self):
        for name, values in (('getresuid', (0, 0, 0)), ('getresuid', (1001, 0, 1001)),
                             ('getresuid', (1001, 1001, 0)), ('getresgid', (1001, 0, 1001))):
            with self.subTest(name=name, values=values), patch('supervisor.os.' + name, return_value=values):
                with self.assertRaisesRegex(ValueError, 'nonroot matching'):
                    s.unprivileged_runner(self.root)

    def test_filesystem_identity_mismatch_rejected(self):
        (self.root / 'self/status').write_text(self.identity.replace('1001\n', '0\n', 1) + self.capabilities)
        with self.assertRaisesRegex(ValueError, 'filesystem/effective identity'):
            s.unprivileged_runner(self.root)

    def test_effective_or_retained_capabilities_rejected(self):
        for key in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb'):
            with self.subTest(key=key):
                value = (self.identity + self.capabilities).replace(key + ':\t0000000000000000', key + ':\t0000000000000001')
                (self.root / 'self/status').write_text(value)
                with self.assertRaisesRegex(ValueError, 'capability evidence'):
                    s.unprivileged_runner(self.root)

    def test_missing_duplicate_or_malformed_identity_rejected(self):
        for value in (self.identity, self.identity + self.capabilities + 'Uid: 1001 1001 1001 1001\n',
                      (self.identity + self.capabilities).replace('CapEff:\t0000000000000000', 'CapEff: unknown')):
            with self.subTest(value=value):
                (self.root / 'self/status').write_text(value)
                with self.assertRaises(ValueError):
                    s.unprivileged_runner(self.root)

    def test_runtime_identity_checked_before_destination_or_launch(self):
        tree = ast.parse(Path(s.__file__).read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        text = ast.unparse(main)
        self.assertLess(text.index('unprivileged_runner()'), text.index('destination.mkdir'))
        self.assertLess(text.index('unprivileged_runner()'), text.index('Pair(spec, destination).run'))


class PortableMemory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.procroot, self.mount = self.root / 'proc', self.root / 'cgroup'
        (self.procroot / 'self').mkdir(parents=True)
        self.mount.mkdir()
        (self.procroot / 'self/cgroup').write_text('0::/\n')
        (self.procroot / 'self/mountinfo').write_text('1 2 0:1 / ' + str(self.mount) + ' rw - cgroup2 cgroup rw\n')
        (self.procroot / 'meminfo').write_text('MemAvailable: 8388608 kB\n')
        self.proc = s.Proc(self.procroot)
        self.graphics = {'reserve_bytes': 256*s.MIB}

    def cgroup(self, path, maximum='max', current=0, inactive=0, dirty=0, writeback=0):
        path.mkdir(parents=True, exist_ok=True)
        for name, value in {'memory.max': str(maximum), 'memory.current': str(current),
                            'memory.stat': f'inactive_file {inactive}\nfile_dirty {dirty}\nfile_writeback {writeback}\n',
                            'memory.events': 'oom 0\noom_kill 0\n'}.items():
            (path / name).write_text(value)

    def gate(self):
        return s.memory_gate(self.proc, self.graphics)

    def test_raw_vm_root_without_memory_max_uses_real_memavailable(self):
        result = self.gate()
        self.assertEqual(result['host_mem_available_bytes'], 8*1024*s.MIB)
        self.assertEqual(result['eligible_bytes'], result['host_mem_available_bytes'])
        self.assertEqual(result['effective_cgroup_limits'], [])
        self.assertEqual(result['memory_bound_source'], 'host_MemAvailable')
        self.assertEqual(result['cgroup_measurements'][0]['scope'], 'actual_hierarchy_root_without_memory_max')

    def test_raw_vm_with_verified_absence_of_cgroup_hierarchy(self):
        (self.procroot / 'self/cgroup').write_text('')
        (self.procroot / 'self/mountinfo').write_text('1 2 0:1 / / rw - ext4 /dev/sda rw\n')
        result = self.gate()
        self.assertEqual(result['cgroup_measurements'], [])
        self.assertEqual(result['eligible_bytes'], 8*1024*s.MIB)

    def test_unlimited_leaf_reports_actual_measurements_without_fictional_limit(self):
        leaf = self.mount / 'leaf'
        self.cgroup(leaf, current=32*s.MIB)
        (self.procroot / 'self/cgroup').write_text('0::/leaf\n')
        result = self.gate()
        self.assertEqual(result['effective_cgroup_limits'], [])
        self.assertEqual(result['cgroup_measurements'][0]['maximum_bytes'], None)
        self.assertEqual(result['cgroup_measurements'][0]['current_bytes'], 32*s.MIB)
        s.no_new_oom_events(result)
        (leaf / 'memory.events').write_text('oom 1\noom_kill 0\n')
        with self.assertRaisesRegex(ValueError, 'OOM'):
            s.no_new_oom_events(result)

    def test_minimum_finite_ancestor_headroom_including_current_usage(self):
        leaf = self.mount / 'parent/leaf'
        self.cgroup(leaf, 7*1024*s.MIB, current=1024*s.MIB)
        self.cgroup(leaf.parent, 6*1024*s.MIB, current=2*1024*s.MIB,
                    inactive=256*s.MIB, dirty=32*s.MIB, writeback=16*s.MIB)
        (self.procroot / 'self/cgroup').write_text('0::/parent/leaf\n')
        result = self.gate()
        self.assertEqual(result['eligible_bytes'], (4096+256-32-16)*s.MIB)
        self.assertEqual(len(result['effective_cgroup_limits']), 2)
        self.assertEqual(result['memory_bound_source'], 'host_and_finite_cgroup_minimum')
        (leaf.parent / 'memory.current').write_text(str(4*1024*s.MIB))
        with self.assertRaisesRegex(ValueError, 'Aggregate memory'):
            self.gate()

    def test_vm_memory_is_still_minimum_when_cgroup_larger(self):
        self.cgroup(self.mount, 16*1024*s.MIB)
        self.assertEqual(self.gate()['eligible_bytes'], 8*1024*s.MIB)

    def test_reclaim_credit_first_covers_existing_over_limit_usage(self):
        self.cgroup(self.mount, 4*1024*s.MIB, current=6*1024*s.MIB, inactive=4*1024*s.MIB)
        with self.assertRaisesRegex(ValueError, 'Aggregate memory'):
            self.gate()  # Only 2 GiB is eligible after reclaim, never 4 GiB.

    def test_unchanged_three_and_half_gib_plus_measured_reserve_threshold(self):
        self.assertEqual(s.PROCESS_BYTES, (1280+512)*s.MIB)
        self.assertEqual(s.PAIR_BYTES, 3758096384)
        for reserve in (256*s.MIB, 640*s.MIB):
            self.graphics['reserve_bytes'] = reserve
            required = 3758096384 + reserve
            (self.procroot / 'meminfo').write_text(f'MemAvailable: {required//1024} kB\n')
            self.assertEqual(self.gate()['required_bytes'], required)
            (self.procroot / 'meminfo').write_text(f'MemAvailable: {required//1024-1} kB\n')
            with self.assertRaisesRegex(ValueError, 'Aggregate memory'):
                self.gate()
        self.graphics['reserve_bytes'] = 256*s.MIB - 1
        with self.assertRaisesRegex(ValueError, 'graphics reserve'):
            self.gate()

    def test_missing_duplicate_wrong_unit_or_negative_memavailable_rejected(self):
        for value in ('MemTotal: 99999999 kB\n', 'MemAvailable: -1 kB\n', 'MemAvailable: 8388608 MB\n',
                      'MemAvailable: 8388608 kB\nMemAvailable: 8388608 kB\n', 'MemAvailable: NaN kB\n'):
            with self.subTest(value=value):
                (self.procroot / 'meminfo').write_text(value)
                with self.assertRaisesRegex(ValueError, 'MemAvailable'):
                    self.gate()
        (self.procroot / 'meminfo').unlink()
        with self.assertRaises(FileNotFoundError):
            self.gate()

    def test_unreadable_resource_evidence_rejected(self):
        original = s.read_bounded
        def denied(path, limit):
            if Path(path) == self.procroot / 'meminfo':
                raise PermissionError('synthetic permission denial')
            return original(path, limit)
        with patch.object(s, 'read_bounded', side_effect=denied), self.assertRaises(PermissionError):
            self.gate()

    def test_malformed_or_missing_cgroup_measurements_rejected(self):
        leaf = self.mount / 'leaf'
        (self.procroot / 'self/cgroup').write_text('0::/leaf\n')
        cases = [('memory.max', '-1'), ('memory.current', '-1'), ('memory.current', 'unknown'),
                 ('memory.stat', 'inactive_file 0\nfile_dirty 0\n'),
                 ('memory.stat', 'inactive_file 0\nfile_dirty 0\nfile_writeback 0\ninactive_file 1\n'),
                 ('memory.events', 'oom 0\n')]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                self.cgroup(leaf)
                (leaf / name).write_text(value)
                with self.assertRaises(ValueError):
                    self.gate()
        for name in ('memory.max', 'memory.current', 'memory.stat', 'memory.events'):
            with self.subTest(missing=name):
                self.cgroup(leaf)
                (leaf / name).unlink()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.gate()

    def test_missing_or_ambiguous_cgroup_location_is_not_raw_vm(self):
        original = (self.procroot / 'self/mountinfo').read_text()
        for value in (original + original, 'malformed mount row\n',
                      original.replace(' / ' + str(self.mount), ' /subtree ' + str(self.mount))):
            with self.subTest(value=value):
                (self.procroot / 'self/mountinfo').write_text(value)
                with self.assertRaises(ValueError):
                    self.gate()
        (self.procroot / 'self/mountinfo').unlink()
        with self.assertRaises(FileNotFoundError):
            self.gate()

    def test_competing_jvm_blocks_raw_vm_with_plenty_of_memory(self):
        identity = {'pid': 77, 'start_ticks': 1, 'state': 'S'}
        (self.procroot / '77').mkdir()
        (self.procroot / '77/comm').write_text('java\n')
        with patch.object(self.proc, 'all_identities', return_value=[identity]):
            with self.assertRaisesRegex(ValueError, 'competing-JVM'):
                self.gate()

    def test_owned_server_anonymous_credit_is_capped_and_identity_checked(self):
        identity = {'pid': 77, 'start_ticks': 1, 'state': 'S'}
        (self.procroot / '77').mkdir()
        (self.procroot / '77/comm').write_text('java\n')
        (self.procroot / '77/status').write_text('RssAnon: 9999999 kB\n')
        required = s.PAIR_BYTES + self.graphics['reserve_bytes']
        (self.procroot / 'meminfo').write_text(f'MemAvailable: {(required-s.PROCESS_BYTES)//1024} kB\n')
        with patch.object(self.proc, 'all_identities', return_value=[identity]), patch.object(self.proc, 'same') as same:
            result = s.memory_gate(self.proc, self.graphics, identity)
            self.assertEqual(result['owned_server_credit_bytes'], s.PROCESS_BYTES)
            self.assertGreaterEqual(same.call_count, 3)
        with patch.object(self.proc, 'all_identities', return_value=[identity]), \
                patch.object(self.proc, 'same', side_effect=ValueError('Process identity changed')):
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                s.memory_gate(self.proc, self.graphics, identity)


class FrozenContract(unittest.TestCase):
    def test_frozen_manifest_and_original_thirty_test_file_preserved(self):
        here = Path(__file__).resolve().parent
        frozen = here.parent / 'network-ci-supervisor'
        self.assertEqual(s.digest(frozen / 'source-manifest.json'), 'fae6495abb25b57634681d338b6cfd9eec21a52c777f2e71126ee6a1128f35e1')
        for row in json.loads((frozen / 'source-manifest.json').read_text())['files']:
            self.assertEqual((frozen / row['path']).stat().st_size, row['bytes'])
            self.assertEqual(s.digest(frozen / row['path']), row['sha256'])
        self.assertEqual((here / 'test_supervisor.py').read_bytes().replace(
            b"file('server/ops.json', b'[]\\n')", b"file('server/ops.json', b'[]')"),
            (frozen / 'test_supervisor.py').read_bytes())

    def test_pair_dependencies_and_graphics_contract_functions_unchanged(self):
        here = Path(__file__).resolve().parent
        upstream = ast.parse((here.parent / 'network-ci-supervisor/supervisor.py').read_text())
        current = ast.parse((here / 'supervisor.py').read_text())
        capture = next(node for node in current.body if isinstance(node, ast.ClassDef) and node.name == 'Capture')
        additions = {'self.line_observed_monotonic = []', 'self.line_observed_monotonic.append(time.monotonic())'}
        observed = []
        for node in ast.walk(capture):
            if hasattr(node, 'body') and isinstance(node.body, list):
                observed.extend(ast.unparse(child) for child in node.body if ast.unparse(child) in additions)
                node.body[:] = [child for child in node.body if ast.unparse(child) not in additions]
        self.assertEqual(set(observed), additions)
        self.assertEqual(len(observed), 2)
        def selected(tree):
            return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and
                    node.name in ('verify_graphics', 'verify_listeners', 'Proc', 'Capture',
                                  'validate_probe', 'validate_ready', 'validate_disconnect', 'verify_environment')}
        self.assertEqual(selected(upstream), selected(current))


if __name__ == '__main__':
    unittest.main()
