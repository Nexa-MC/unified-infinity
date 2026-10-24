"""Synthetic proc snapshots only. No Java, lshw, games, signals, or downloads."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import supervisor as s
import test_cpu_probe_policy as fixtures

REAL_READLINK = os.readlink


class SpawnTransition(unittest.TestCase):
    ARGV = s.CPU_PROBE_ARGV

    def setUp(self):
        fixtures.SampleContract.setUp(self)
        self.jdk = self.root / 'jdk'
        (self.jdk / 'bin').mkdir(parents=True)
        (self.jdk / 'lib').mkdir()
        new_java = self.jdk / 'bin/java'
        self.java.rename(new_java)
        self.java = new_java
        (self.root / '101/exe').unlink()
        (self.root / '101/exe').symlink_to(self.java)
        self.command = [str(self.java), '-cp', 'sealed']
        (self.root / '101/cmdline').write_bytes(b'\0'.join(map(os.fsencode, self.command)) + b'\0')
        self.spawn = self.jdk / 'lib/jspawnhelper'
        self.spawn.write_bytes(b'exact synthetic sealed helper')
        self.spawn.chmod(0o755)
        self.exe = self.root / '102/exe'
        self.exe.unlink()
        self.exe.symlink_to(self.spawn)
        self.helper_args = os.fsencode(self.spawn) + b'\0' + s.JDK_SPAWN_VERSION + b'\0' + b'6:7:9\0'
        (self.root / '102/cmdline').write_bytes(self.helper_args)
        self.stack.enter_context(patch.object(s, 'JDK_SPAWN_BYTES', self.spawn.stat().st_size))
        self.stack.enter_context(patch.object(s, 'JDK_SPAWN_SHA256', s.digest(self.spawn)))
        def readlink(path):
            actual = REAL_READLINK(path)
            return s.CPU_PROBE_PATH if Path(path) == self.exe and actual == str(self.binary) else actual
        self.stack.enter_context(patch.object(s.os, 'readlink', side_effect=readlink))
        previous_stat = s.os.stat
        self.stack.enter_context(patch.object(s.os, 'stat', side_effect=lambda path, *a, **k:
            previous_stat(self.binary if str(path) == s.CPU_PROBE_PATH else path, *a, **k)))
        self.handle = self.stack.enter_context(patch.object(s, 'cpu_probe_handle_live'))
        self.pair = SimpleNamespace(
            spec={'schema': 'network-ci-pair-v2', 'preparation_roots': [str(self.root)],
                  'immutable_trees': [str(self.jdk)],
                  'inputs': [{'path': str(self.spawn), 'bytes': s.JDK_SPAWN_BYTES, 'sha256': s.JDK_SPAWN_SHA256}],
                  'server': {'command': self.command}},
            identities={'server': self.parent}, children={'server': SimpleNamespace(poll=Mock(return_value=None))},
            proc=self.proc, report={}, deadline=s.time.monotonic() + 20)

    def target(self, argv=None):
        self.exe.unlink()
        self.exe.symlink_to(self.binary)
        (self.root / '102/cmdline').write_bytes(self.ARGV if argv is None else argv)

    def snapshot(self):
        return s.cpu_probe_spawn_sample(self.pair, self.helper, self.parent, self.command, s.time.monotonic() + 1)

    def transition(self, deadline=None):
        return s.cpu_probe_spawn_transition(self.pair, self.helper, self.parent, self.command, 77,
                                           s.time.monotonic() + 1 if deadline is None else deadline)

    def test_exact_helper_is_not_acceptance(self):
        self.assertFalse(self.snapshot())
        self.assertEqual(self.pair.report, {})

    def test_synchronous_transition_requires_full_target(self):
        with patch.object(s.time, 'sleep', side_effect=lambda _: self.target()):
            signature, metrics = self.transition()
        self.assertEqual(signature[-1], self.ARGV)
        self.assertGreaterEqual(metrics['high_water_rss_bytes'], 8192)
        self.assertEqual(self.pair.report['jdk_spawn_transitions'][0]['helper_observations'], 1)
        self.assertTrue(self.pair.report['jdk_spawn_transitions'][0]['target_verified'])
        self.assertTrue(all(call.args == (77,) for call in self.handle.call_args_list))

    def test_public_sample_only_enables_transition_for_unobserved_identity(self):
        with patch.object(s.time, 'sleep', side_effect=lambda _: self.target()):
            signature, _ = s.cpu_probe_sample(self.proc, self.helper, self.parent, self.command,
                                               transition_context=(self.pair, 77))
        self.exe.unlink(); self.exe.symlink_to(self.spawn)
        (self.root / '102/cmdline').write_bytes(self.helper_args)
        with self.assertRaisesRegex(ValueError, 'executable path'):
            s.cpu_probe_sample(self.proc, self.helper, self.parent, self.command, signature,
                               transition_context=(self.pair, 77))

    def test_transition_during_helper_hash_uses_fresh_full_target_sample(self):
        original = s.os.read
        changed = False
        def read(fd, size):
            nonlocal changed
            result = original(fd, size)
            if result == self.spawn.read_bytes() and not changed:
                changed = True
                self.target()
            return result
        with patch.object(s.os, 'read', side_effect=read):
            signature, _ = self.transition()
        self.assertTrue(changed)
        self.assertEqual(signature[-1], self.ARGV)

    def test_transition_between_readlink_and_open_is_reverified(self):
        original = s.os.open
        changed = False
        def opened(path, flags, *args, **kwargs):
            nonlocal changed
            if Path(path) == self.exe and flags & os.O_CLOEXEC and not changed:
                changed = True
                self.target()
            return original(path, flags, *args, **kwargs)
        with patch.object(s.os, 'open', side_effect=opened):
            signature, _ = self.transition()
        self.assertTrue(changed)
        self.assertEqual(signature[-1], self.ARGV)

    def test_argv_changes_to_exact_target_during_read_are_reverified(self):
        original = s.read_bounded
        reads = 0
        def read(path, limit):
            nonlocal reads
            if Path(path) == self.root / '102/cmdline':
                reads += 1
                if reads == 2:
                    self.target()
            return original(path, limit)
        with patch.object(s, 'read_bounded', side_effect=read):
            signature, _ = self.transition()
        self.assertEqual(signature[-1], self.ARGV)

    def test_wrong_target_argv_hash_or_socket_never_admitted(self):
        for failure in ('argv', 'hash', 'socket'):
            with self.subTest(failure=failure):
                self.exe.unlink(); self.exe.symlink_to(self.spawn)
                (self.root / '102/cmdline').write_bytes(self.helper_args)
                self.pair.report = {}
                def change(_):
                    self.target(b'lshw\0-C\0system\0' if failure == 'argv' else None)
                    if failure == 'socket':
                        (self.root / '102/fd/8').symlink_to('socket:[123]')
                with patch.object(s.time, 'sleep', side_effect=change):
                    if failure == 'hash':
                        with patch.object(s, 'CPU_PROBE_SHA256', '0' * 64), self.assertRaises(ValueError):
                            self.transition()
                    else:
                        with self.assertRaises(ValueError): self.transition()
                self.assertNotIn('jdk_spawn_transitions', self.pair.report)
                if failure == 'socket': (self.root / '102/fd/8').unlink()

    def test_wrong_helper_hash_pin_or_path_rejected(self):
        self.spawn.write_bytes(b'X' * s.JDK_SPAWN_BYTES)
        with self.assertRaisesRegex(ValueError, 'digest'): self.snapshot()
        self.spawn.write_bytes(b'exact synthetic sealed helper')
        self.pair.spec['inputs'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'pin missing'): self.snapshot()
        self.pair.spec['inputs'][0]['sha256'] = s.JDK_SPAWN_SHA256
        self.exe.unlink(); self.exe.symlink_to(self.java)
        with self.assertRaisesRegex(ValueError, 'target forbidden'): self.snapshot()

    def test_helper_argv_exact_version_and_fd_shape(self):
        for raw in (self.helper_args.replace(s.JDK_SPAWN_VERSION, b'other'),
                    self.helper_args.replace(b'6:7:9', b'6:6:9'),
                    self.helper_args.replace(b'6:7:9', b'6:7:2147483648'),
                    self.helper_args.replace(b'6:7:9', b'-1:7:9'),
                    self.helper_args.replace(b'6:7:9', b'06:7:9'),
                    self.helper_args + b'SECRET\0', self.helper_args[:-1]):
            (self.root / '102/cmdline').write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'argument form') as caught:
                self.snapshot()
            self.assertNotIn('SECRET', str(caught.exception))

    def test_helper_fd_limit_socket_credentials_parent_and_descendants_fail_closed(self):
        cases = [('socket', lambda: (self.root / '102/fd/8').symlink_to('socket:[123]')),
                 ('credential', lambda: (self.root / '102/status').write_text(fixtures.status(uid=0))),
                 ('direct-parent', lambda: (self.root / '102/stat').write_text(fixtures.proc_stat(dict(self.helper, ppid=999)))),
                 ('parent command', lambda: (self.root / '101/cmdline').write_bytes(b'other\0'))]
        for reason, change in cases:
            with self.subTest(reason=reason):
                change()
                with self.assertRaisesRegex(ValueError, reason): self.transition()
                if (self.root / '102/fd/8').is_symlink(): (self.root / '102/fd/8').unlink()
                (self.root / '102/status').write_text(fixtures.status())
                (self.root / '102/stat').write_text(fixtures.proc_stat(self.helper))
                (self.root / '101/cmdline').write_bytes(b'\0'.join(map(os.fsencode, self.command)) + b'\0')
        for i in range(65): (self.root / '102/fd' / str(i)).symlink_to('/dev/null')
        with self.assertRaisesRegex(ValueError, 'descriptor bound'): self.transition()

    def test_fresh_census_detects_new_child_and_descendant_during_wait(self):
        for relationship, reason in ((101, 'simultaneous'), (102, 'descendants')):
            self.exe.unlink(); self.exe.symlink_to(self.spawn)
            (self.root / '102/cmdline').write_bytes(self.helper_args)
            def change(_):
                self.target()
                child = self.root / '103'; child.mkdir()
                (child / 'stat').write_text(fixtures.proc_stat(fixtures.process(pid=103, parent=relationship)))
            with patch.object(s.time, 'sleep', side_effect=change), self.assertRaisesRegex(ValueError, reason):
                self.transition()
            (self.root / '103/stat').unlink(); (self.root / '103').rmdir()

    def test_no_deadline_reset_and_no_helper_only_acceptance(self):
        self.pair.deadline = 100
        ticks = iter(i / 100 for i in range(1000))
        with patch.object(s.time, 'monotonic', side_effect=lambda: next(ticks)), patch.object(s.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'budget'): self.transition(deadline=.25)
        self.assertEqual(self.pair.report, {})

    def test_pair_deadline_is_stricter_than_sample_budget(self):
        self.pair.deadline = .01
        with patch.object(s.time, 'monotonic', return_value=.02):
            with self.assertRaisesRegex(ValueError, 'budget'): self.transition(deadline=1)

    def test_helper_valid_argv_cannot_change_between_observations(self):
        def change(_):
            (self.root / '102/cmdline').write_bytes(self.helper_args.replace(b'6:7:9', b'10:11:12'))
        with patch.object(s.time, 'sleep', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'across observations'): self.transition()

    def test_permission_error_is_not_retried_as_transition(self):
        with patch.object(s, 'cpu_probe_fds', side_effect=PermissionError('SECRET')):
            with self.assertRaises(PermissionError): self.transition()
        self.assertEqual(self.pair.report, {})

    def test_known_fd_violation_cannot_be_erased_by_target_exec(self):
        def violated(*_):
            self.target()
            raise ValueError('CPU probe socket descriptor forbidden')
        with patch.object(s, 'cpu_probe_fds', side_effect=violated):
            with self.assertRaisesRegex(ValueError, 'socket'): self.transition()
        self.assertEqual(self.pair.report, {})

    def test_exit_zombie_pid_reuse_and_handle_death_fail_closed(self):
        for change in ({'state': 'Z'}, {'start_ticks': 991}):
            (self.root / '102/stat').write_text(fixtures.proc_stat(dict(self.helper, **change)))
            with self.assertRaises(ValueError): self.transition()
        (self.root / '102/stat').write_text(fixtures.proc_stat(self.helper))
        self.handle.side_effect = ValueError('CPU probe retained handle is not live')
        with self.assertRaisesRegex(ValueError, 'handle'): self.transition()
        self.handle.side_effect = None
        (self.root / '102/stat').unlink()
        with self.assertRaises(FileNotFoundError): self.transition()

    def test_limits_are_unchanged(self):
        self.assertEqual((s.CPU_PROBE_MAX_PER_ROLE, s.CPU_PROBE_MAX_SECONDS,
                          s.CPU_PROBE_MAX_CPU_SECONDS, s.CPU_PROBE_MAX_RSS,
                          s.CPU_PROBE_RESERVE_BYTES), (4, 10, 2, 64 * s.MIB, 128 * s.MIB))


if __name__ == '__main__':
    unittest.main()
