"""Diagnostic-only tests, including real bounded Python process/fd lifecycles.

The real tests exercise failing existing verifier seams, not lshw admission.
They never execute Java, lshw, games, downloaded tools, ptrace, or network work.
"""
import ast
from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import supervisor as s
from console_capacity_preservation import without_console_capacity
import test_cpu_probe_policy as fixtures


PREDECESSOR_SHA256 = '12df46db6bf11127a3a95cbf3e813315aa909c83c329d0755c9690d24a9be8ef'
DIAGNOSTIC_HELPER_SHA256 = '3ec4e3cf888dd48c517d33478b8ea10c02a484054af1f262e137aaafca21f561'
ADDITIONS = (
    '        current = None\n',
    '                current = row\n',
    '''            try:
                self.failure_context = cpu_probe_failure_diagnostic(error, current, self.records)
            except Exception:
                self.failure_context = {'admission_evidence': False, 'status': 'UNAVAILABLE'}
''',
    "                'failure_context': getattr(self, 'failure_context', None),\n",
)


def without_probe_diagnostics(source):
    """Remove only the exact independently pinned diagnostic additions."""
    source = without_console_capacity(source)
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
             and n.name == 'cpu_probe_failure_diagnostic']
    if len(nodes) != 1:
        raise ValueError('Expected one diagnostic helper')
    node = nodes[0]
    block = ''.join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno]) + '\n\n'
    if hashlib.sha256(block.encode()).hexdigest() != DIAGNOSTIC_HELPER_SHA256 or source.count(block) != 1:
        raise ValueError('Diagnostic helper changed')
    source = source.replace(block, '', 1)
    for addition in ADDITIONS:
        if source.count(addition) != 1:
            raise ValueError('Diagnostic insertion changed')
        source = source.replace(addition, '', 1)
    return source


class SourcePreservation(unittest.TestCase):
    def test_all_predecessor_bytes_survive_exact_diagnostic_normalization(self):
        source = without_probe_diagnostics(Path(s.__file__).read_text())
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), PREDECESSOR_SHA256)

    def test_all_admission_mutations_remain_detectable(self):
        source = Path(s.__file__).read_text()
        for needle in ('CPU_PROBE_MAX_PER_ROLE = 4', 'CPU_PROBE_VERIFY_SECONDS = 1',
                       'CPU_PROBE_MAX_RSS = 64 * MIB', 'CPU probe socket descriptor forbidden',
                       'CPU probe unverified zombie forbidden', 'CPU probe executable digest mismatch',
                       'CPU probe argument form mismatch', 'CPU probe parent executable changed',
                       "cpu_probe_handle_live(fd)", 'CPU probe failure remains sticky'):
            with self.subTest(needle=needle):
                self.assertIn(needle, source)
                altered = without_probe_diagnostics(source.replace(needle, 'CHANGED_ADMISSION', 1))
                self.assertNotEqual(hashlib.sha256(altered.encode()).hexdigest(), PREDECESSOR_SHA256)

    def test_changed_or_duplicate_diagnostic_blocks_are_not_normalized(self):
        source = Path(s.__file__).read_text()
        cases = [source.replace('scanned < 32', 'scanned < 33', 1),
                 source.replace(ADDITIONS[0], ADDITIONS[0] * 2, 1),
                 source.replace(ADDITIONS[3], '', 1)]
        for changed in cases:
            with self.assertRaises(ValueError):
                without_probe_diagnostics(changed)


class SyntheticFailureDiagnostics(unittest.TestCase):
    def setUp(self):
        self.policy = s.CpuProbePolicy()
        self.row = fixtures.process()
        self.parent = fixtures.process(pid=101, parent=os.getpid(), start=100)
        self.pair = SimpleNamespace(identities={'server': self.parent},
                                   children={'server': SimpleNamespace(poll=lambda: None)},
                                   spec={'server': {'command': ['java']}}, proc=s.Proc(), report={})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(s.os, 'pidfd_open', return_value=77))
        self.stack.enter_context(patch.object(s, 'cpu_probe_handle_live'))
        self.close = self.stack.enter_context(patch.object(s.os, 'close'))

    def check(self):
        return self.policy.check(self.pair, [self.row], [self.row])

    def test_exception_categories_are_fixed_and_never_leak_private_data(self):
        for error, category, number in (
            (FileNotFoundError(errno.ENOENT, 'PRIVATE ERROR', '/secret/path'), 'NOT_FOUND', errno.ENOENT),
            (ProcessLookupError(errno.ESRCH, 'PRIVATE ERROR'), 'NO_PROCESS', errno.ESRCH),
            (PermissionError(errno.EACCES, 'PRIVATE ERROR', '/secret/path'), 'PERMISSION', errno.EACCES),
            (OSError(errno.EIO, 'PRIVATE ERROR'), 'OS_ERROR', errno.EIO),
            (ValueError('PRIVATE ERROR'), 'VALUE', None),
        ):
            with self.subTest(category=category):
                self.policy = s.CpuProbePolicy()
                with patch.object(s, 'cpu_probe_sample', side_effect=error), self.assertRaises(type(error)) as caught:
                    self.check()
                self.assertIs(caught.exception, error)
                value = self.pair.report['cpu_probe_policy']['failure_context']
                self.assertEqual(value['category'], category)
                self.assertEqual(value['errno'], number)
                self.assertEqual((value['pid'], value['start_ticks']), (102, 990))
                self.assertFalse(value['previously_verified'])
                self.assertFalse(value['admission_evidence'])
                self.assertEqual(self.policy.records, {})
                serialized = json.dumps(self.pair.report)
                for secret in ('PRIVATE', '/secret', '__mock_call', str(Path(__file__).parent)):
                    self.assertNotIn(secret, serialized)
                self.assertTrue(value['frames'])
                with self.assertRaisesRegex(ValueError, 'sticky'):
                    self.check()

    def test_pidfd_open_failure_is_classified_without_sampling_or_handle_close(self):
        with patch.object(s.os, 'pidfd_open', side_effect=ProcessLookupError(errno.ESRCH, 'private')), \
                patch.object(s, 'cpu_probe_sample') as sample, self.assertRaises(ProcessLookupError):
            self.check()
        sample.assert_not_called()
        self.close.assert_not_called()
        value = self.pair.report['cpu_probe_policy']['failure_context']
        self.assertEqual(value['category'], 'NO_PROCESS')
        self.assertEqual(value['frames'][0]['function'], 'check')

    def test_previously_verified_is_only_historical_not_readmission(self):
        metrics = dict(age_seconds=.1, cpu_ticks=1, rss_bytes=1, high_water_rss_bytes=1)
        with patch.object(s, 'cpu_probe_sample', return_value=((1,), metrics)):
            self.assertEqual(self.check(), {(102, 990)})
        with patch.object(s, 'cpu_probe_sample', side_effect=FileNotFoundError(errno.ENOENT, 'private')), \
                self.assertRaises(FileNotFoundError):
            self.check()
        report = self.pair.report['cpu_probe_policy']
        self.assertTrue(report['failed'])
        self.assertTrue(report['failure_context']['previously_verified'])
        self.assertEqual(report['observed'][0]['observations'], 1)
        with self.assertRaisesRegex(ValueError, 'sticky'):
            self.check()

    def test_diagnostic_error_cannot_replace_primary_failure_or_admit(self):
        error = PermissionError(errno.EACCES, 'private')
        with patch.object(s, 'cpu_probe_sample', side_effect=error), \
                patch.object(s, 'cpu_probe_failure_diagnostic', side_effect=RuntimeError('private')), \
                self.assertRaises(PermissionError) as caught:
            self.check()
        self.assertIs(caught.exception, error)
        self.assertEqual(self.policy.records, {})
        self.assertEqual(self.pair.report['cpu_probe_policy']['failure_context'],
                         {'admission_evidence': False, 'status': 'UNAVAILABLE'})

    def test_traceback_scan_and_output_are_strictly_bounded(self):
        # Use the same fixed source/function label for a constructed traceback.
        scope = {}
        exec(compile('def same(n):\n if n: return same(n-1)\n raise ValueError("PRIVATE")\n',
                     s.__file__, 'exec'), scope)
        try:
            scope['same'](40)
        except ValueError as error:
            value = s.cpu_probe_failure_diagnostic(error, self.row, {})
        self.assertEqual(len(value['frames']), 12)
        self.assertTrue(value['traceback_truncated'])
        self.assertNotIn('PRIVATE', json.dumps(value))


class SyntheticVerifierSeams(unittest.TestCase):
    ARGV = s.CPU_PROBE_ARGV

    def setUp(self):
        fixtures.SampleContract.setUp(self)
        self.stack.enter_context(patch.object(s.os, 'pidfd_open', return_value=77))
        self.stack.enter_context(patch.object(s, 'cpu_probe_handle_live'))
        self.closed = []
        original_close = os.close
        self.stack.enter_context(patch.object(s.os, 'close', side_effect=lambda fd:
            self.closed.append(fd) if fd == 77 else original_close(fd)))
        self.pair = SimpleNamespace(identities={'server': self.parent},
                                   children={'server': SimpleNamespace(poll=lambda: None)},
                                   spec={'server': {'command': self.command}}, proc=self.proc, report={})

    def test_exact_exe_vs_argv_read_failure_lines_are_distinguishable(self):
        lines = Path(s.__file__).read_text().splitlines()
        real_readlink, real_read = os.readlink, s.read_bounded
        for location in ('exe', 'cmdline'):
            policy = s.CpuProbePolicy()
            path = self.root / '102' / location
            def readlink(value):
                if Path(value) == path:
                    raise FileNotFoundError(errno.ENOENT, 'PRIVATE', '/secret/path')
                return real_readlink(value)
            def read(value, limit):
                if Path(value) == path:
                    raise FileNotFoundError(errno.ENOENT, 'PRIVATE', '/secret/path')
                return real_read(value, limit)
            with self.subTest(location=location), patch.object(s.os, 'readlink', side_effect=readlink), \
                    patch.object(s, 'read_bounded', side_effect=read), self.assertRaises(FileNotFoundError):
                policy.check(self.pair, [self.helper], [self.helper])
            context = self.pair.report['cpu_probe_policy']['failure_context']
            self.assertEqual(context['errno'], errno.ENOENT)
            frame = next(frame for frame in reversed(context['frames']) if frame['function'] == 'cpu_probe_sample')
            self.assertIn('os.readlink(path)' if location == 'exe' else 'read_bounded(args, 128)', lines[frame['line'] - 1])
            self.assertEqual(policy.records, {})
            self.assertNotIn('PRIVATE', json.dumps(context))

    def test_success_has_no_failure_context_and_no_extra_probe_reads(self):
        policy = s.CpuProbePolicy()
        with patch.object(s, 'cpu_probe_failure_diagnostic', side_effect=AssertionError('No diagnostic on success')):
            self.assertEqual(policy.check(self.pair, [self.helper], [self.helper]), {(102, 990)})
        self.assertIsNone(self.pair.report['cpu_probe_policy']['failure_context'])
        policy.close(self.pair)


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'), 'Linux pidfd/proc fixture')
class RealLifecycleDiagnostics(unittest.TestCase):
    def setUp(self):
        self.children = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)
            child.stdin.close()
            child.stdout.close()

    def line(self, child):
        self.assertTrue(select.select([child.stdout], [], [], 2)[0], 'Bounded child handshake timed out')
        return child.stdout.readline().strip()

    def child(self, body):
        program = 'import os,signal; signal.alarm(6); ' + body
        child = subprocess.Popen([sys.executable, '-c', program], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        self.children.append(child)
        return child

    def run_failure(self, child, seam):
        proc = s.Proc()
        row = proc.identity(child.pid)
        policy = s.CpuProbePolicy()
        parent = dict(row, pid=os.getpid(), start_ticks=0)
        pair = SimpleNamespace(identities={'server': parent},
                               children={'server': SimpleNamespace(poll=lambda: None)},
                               spec={'server': {'command': ['not-executed']}}, proc=proc, report={})
        handles = []
        original = os.pidfd_open
        def opened(pid, flags):
            descriptor = original(pid, flags)
            handles.append(descriptor)
            return descriptor
        # Only sample dispatch is substituted. The failing proc/fd reads and
        # owned pidfd creation, liveness, closure and rejection are real.
        with patch.object(s, 'cpu_probe_sample', side_effect=lambda *a, **k: seam(proc, row)), \
                patch.object(s.os, 'pidfd_open', side_effect=opened), self.assertRaises(FileNotFoundError):
            policy.check(pair, [row], [row])
        self.assertEqual(policy.records, {})
        self.assertTrue(policy.failed)
        self.assertEqual(len(handles), 1)
        with self.assertRaises(OSError) as closed:
            os.fstat(handles[0])
        self.assertEqual(closed.exception.errno, errno.EBADF)
        with self.assertRaisesRegex(ValueError, 'sticky'):
            policy.check(pair, [], [])
        value = pair.report['cpu_probe_policy']['failure_context']
        self.assertEqual(value['category'], 'NOT_FOUND')
        self.assertEqual(value['errno'], errno.ENOENT)
        self.assertFalse(value['previously_verified'])
        self.assertFalse(value['admission_evidence'])
        return proc, row, value

    def test_real_exit_then_reap_between_pidfd_and_process_stat_stays_rejected(self):
        child = self.child('print("ready",flush=True); os.read(0,1); os._exit(0)')
        self.assertEqual(self.line(child), b'ready')
        def seam(proc, row):
            child.stdin.write(b'x'); child.stdin.flush()
            self.assertEqual(child.wait(timeout=2), 0)
            return proc.same(row)
        proc, row, value = self.run_failure(child, seam)
        self.assertIn('identity', [frame['function'] for frame in value['frames']])
        self.assertIn('read_bounded', [frame['function'] for frame in value['frames']])
        self.assertEqual(s.rejected_child_executable(proc, row, time.monotonic() + 1)['status'], 'GONE')

    def test_real_fd_close_after_scandir_remains_rejection_not_child_disappearance(self):
        child = self.child('fd=os.open("/dev/null",os.O_RDONLY); print(fd,flush=True); '
                           'os.read(0,1); os.close(fd); print("closed",flush=True); os.read(0,1)')
        descriptor = int(self.line(child))
        original = os.scandir
        def seam(proc, row):
            folder = proc.root / str(row['pid']) / 'fd'
            class ClosedAfterEnumeration:
                def __enter__(self):
                    with original(folder) as entries:
                        self.entries = list(entries)
                    self.assert_found = any(entry.name == str(descriptor) for entry in self.entries)
                    if not self.assert_found:
                        raise AssertionError('Expected real descriptor in enumeration')
                    child.stdin.write(b'c'); child.stdin.flush()
                    if self_outer.line(child) != b'closed':
                        raise AssertionError('Expected close acknowledgment')
                    return iter(self.entries)
                def __exit__(self, *args):
                    return False
            self_outer = self
            with patch.object(s.os, 'scandir', side_effect=lambda path: ClosedAfterEnumeration()
                              if Path(path) == folder else original(path)):
                return s.cpu_probe_fds(proc, row, time.monotonic() + 2)
        proc, row, value = self.run_failure(child, seam)
        self.assertIsNone(child.poll())
        self.assertEqual(proc.same(row)['start_ticks'], row['start_ticks'])
        self.assertIn('cpu_probe_fds', [frame['function'] for frame in value['frames']])
        self.assertNotIn('identity', [frame['function'] for frame in value['frames']])


if __name__ == '__main__':
    unittest.main()
