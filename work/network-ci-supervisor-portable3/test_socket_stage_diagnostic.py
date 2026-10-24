"""Bounded failure evidence, exact predecessor calls, and owned FD closure.

Socket targets/tables are synthetic, including in the real-process test. No
socket is created and no socket ownership, admission or game result is claimed.
"""
import ast
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import supervisor as s
import test_cpu_probe_policy as fixture
from socket_stage_preservation import (
    ORIGINAL, REVIEWED, PREDECESSOR_SHA256, without_socket_failure_stage)
from test_socket_diagnostic import TABLES, row

TARGET = 'socket:[123]'
PRIVATE = 'PRIVATE /secret/path 127.0.0.1:9999'
ERROR = 'CPU probe socket descriptor forbidden'


def predecessor():
    module = ModuleType('socket_stage_predecessor')
    module.__file__ = s.__file__
    exec(compile(without_socket_failure_stage(Path(s.__file__).read_text()),
                 s.__file__, 'exec'), module.__dict__)
    return module


class FailureStages(unittest.TestCase):
    def exercise(self, module=s, *, clocks=None, expired_from=None, identities=None,
                 links=None, tables=None, path='/fake/42/fd/7', target=TARGET):
        trace = []
        counts = dict(clock=0, same=0, link=0)
        table_data = {t: b'header\n' for t in TABLES}
        table_data['tcp'] += row('tcp').encode()
        table_data.update(tables or {})
        def take(kind, mapping, default):
            counts[kind] += 1
            value = (mapping or {}).get(counts[kind], default)
            if isinstance(value, BaseException):
                raise value
            return value
        def clock():
            trace.append(('clock',))
            default = 2 if expired_from is not None and counts['clock'] + 1 >= expired_from else 0
            return take('clock', clocks, default)
        def same(identity):
            trace.append(('same', dict(identity)))
            return take('same', identities, None)
        def readlink(path):
            trace.append(('readlink', str(path)))
            return take('link', links, TARGET)
        def read(path, bound):
            trace.append(('read', str(path), bound))
            value = table_data[path.name]
            if isinstance(value, BaseException):
                raise value
            return value
        real_require = module.require
        def require(condition, message):
            trace.append(('require', bool(condition), message))
            return real_require(condition, message)
        proc = SimpleNamespace(root=Path('/fake'), same=same)
        with patch.object(module.time, 'monotonic', side_effect=clock), \
                patch.object(module.os, 'readlink', side_effect=readlink), \
                patch.object(module, 'read_bounded', side_effect=read), \
                patch.object(module, 'require', side_effect=require):
            result = module.cpu_probe_socket_diagnostic(
                proc, {'pid': 42, 'start_ticks': 10}, path, target, 1)
        return result, trace

    def compare(self, **kwargs):
        old, old_trace = self.exercise(predecessor(), **kwargs)
        new, new_trace = self.exercise(**kwargs)
        self.assertEqual(new_trace, old_trace)
        projection = {k: v for k, v in new.items() if k not in ('failure', 'partial')}
        if 'tables' in projection:
            projection['tables'] = [{k: v for k, v in item.items() if k != 'failure'}
                                    for item in projection['tables']]
        self.assertEqual(projection, old)
        for secret in ('PRIVATE', '/secret', '127.0.0.1', 'SECRET', 'DO_NOT_PUBLISH', '/fake'):
            self.assertNotIn(secret, json.dumps(new))
        self.assertFalse(new['admission_evidence'])
        return new, new_trace

    def unavailable(self, stage, category='VALIDATION', number=None, **kwargs):
        result, trace = self.compare(**kwargs)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        failure = result['failure']
        self.assertEqual((failure['stage'], failure['error_category'], failure['errno']),
                         (stage, category, number))
        for key in ('matches', 'classification', 'complete'):
            self.assertNotIn(key, result)
        for key in ('admission_evidence', 'identity_verified', 'atomic_observation'):
            self.assertFalse(result['partial'][key])
        self.assertLessEqual(len(result['partial']['tables']), 6)
        self.assertLessEqual(len(result['partial']['matches']), 6)
        return result, trace

    def test_success_has_no_failure_or_partial_and_unchanged_trace(self):
        result, trace = self.compare()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertNotIn('failure', result)
        self.assertNotIn('partial', result)
        self.assertEqual(sum(t[0] == 'clock' for t in trace), 9)
        self.assertEqual(sum(t[0] == 'readlink' for t in trace), 2)
        self.assertEqual(sum(t[0] == 'same' for t in trace), 2)
        self.assertEqual(sum(t[0] == 'read' for t in trace), 6)

    def test_input_failure_no_io_or_unbounded_identity(self):
        for kwargs in ({'path': '/fake/fd/' + '7' * 21}, {'target': 'socket:[' + '9' * 21 + ']'},
                       {'target': PRIVATE}, {'path': None}):
            with self.subTest(kwargs=kwargs):
                result, trace = self.compare(**kwargs)
                self.assertEqual(result['failure']['stage'], 'INPUT')
                self.assertEqual(result['status'], 'UNAVAILABLE')
                self.assertEqual(result['partial']['tables'], [])
                self.assertNotIn('fd', result)
                self.assertFalse(any(t[0] in ('clock', 'same', 'readlink', 'read') for t in trace))

    def test_initial_deadline(self):
        result, trace = self.unavailable('INITIAL_BUDGET', expired_from=1)
        self.assertEqual(result['partial']['tables'], [])
        self.assertFalse(any(t[0] in ('same', 'readlink', 'read') for t in trace))

    def test_identity_before_value_does_not_claim_process_death(self):
        result, trace = self.unavailable('IDENTITY_BEFORE', identities={1: ValueError(PRIVATE)})
        self.assertEqual(result['failure']['error_category'], 'VALIDATION')
        self.assertFalse(any(t[0] in ('readlink', 'read') for t in trace))

    def test_identity_before_os_failures(self):
        for error, category in ((FileNotFoundError(errno.ENOENT, PRIVATE), 'NOT_FOUND'),
                                (ProcessLookupError(errno.ESRCH, PRIVATE), 'NO_PROCESS'),
                                (PermissionError(errno.EACCES, PRIVATE), 'PERMISSION')):
            with self.subTest(category=category):
                self.unavailable('IDENTITY_BEFORE', category, error.errno, identities={1: error})

    def test_initial_fd_read_and_changed(self):
        for error in (FileNotFoundError(errno.ENOENT, PRIVATE), PermissionError(errno.EACCES, PRIVATE)):
            with self.subTest(error=type(error)):
                result, trace = self.unavailable('FD_BEFORE',
                    'NOT_FOUND' if type(error) is FileNotFoundError else 'PERMISSION',
                    error.errno, links={1: error})
                self.assertFalse(any(t[0] == 'read' for t in trace))
        self.unavailable('FD_BEFORE', links={1: 'socket:[456]'})

    def test_table_budget_retains_only_completed_unverified_tables(self):
        result, trace = self.unavailable('TABLE_BUDGET', expired_from=4)
        self.assertEqual(result['failure']['table'], 'tcp6')
        self.assertEqual(result['partial']['tables'], [{'table': 'tcp', 'status': 'READ'}])
        self.assertEqual(result['partial']['matches'], [{'table': 'tcp'}])
        self.assertEqual(sum(t[0] == 'read' for t in trace), 1)

    def test_each_table_permission_read_decode_and_parse_remain_local(self):
        for table in TABLES:
            for value, stage, category, number in (
                (PermissionError(errno.EACCES, PRIVATE, '/secret/path'), 'TABLE_READ', 'PERMISSION', errno.EACCES),
                (FileNotFoundError(errno.ENOENT, PRIVATE), 'TABLE_READ', 'NOT_FOUND', errno.ENOENT),
                (OSError(errno.EIO, PRIVATE), 'TABLE_READ', 'OS_ERROR', errno.EIO),
                (ValueError(PRIVATE), 'TABLE_READ', 'VALIDATION', None),
                (b'header\n\xff', 'TABLE_DECODE', 'UNICODE', None),
                (b'header\nbad\n', 'TABLE_PARSE', 'VALIDATION', None),
            ):
                with self.subTest(table=table, stage=stage, category=category):
                    result, trace = self.compare(tables={table: value})
                    self.assertEqual(result['status'], 'OBSERVED')
                    self.assertFalse(result['complete'])
                    item = next(t for t in result['tables'] if t['table'] == table)
                    self.assertEqual(item, {'table': table, 'status': 'UNAVAILABLE', 'failure':
                        {'table': table, 'stage': stage, 'error_category': category, 'errno': number}})
                    self.assertEqual(sum(t[0] == 'read' for t in trace), 6)
                    self.assertFalse(any(hit['table'] == table for hit in result['matches']))

    def test_row_bound_duplicate_protocol_type_stages(self):
        cases = (
            ('tcp', b'header\n' + row('tcp', '999').encode() * 1025, 'TABLE_ROW_BOUND'),
            ('tcp', b'header\n' + row('tcp').encode() * 2, 'TABLE_MATCH'),
            ('netlink', b'header\n0000 999 42 0 0 0 0 2 0 123\n', 'TABLE_PROTOCOL'),
            ('unix', b'header\n0000: 2 0 0 INVALID 01 123 /secret/path\n', 'TABLE_TYPE'),
        )
        for table, value, stage in cases:
            with self.subTest(stage=stage):
                result, _ = self.compare(tables={table: value})
                item = next(t for t in result['tables'] if t['table'] == table)
                self.assertEqual(item['failure']['stage'], stage)
                self.assertFalse(any(hit['table'] == table for hit in result['matches']))

    def test_row_deadline_stays_local_then_next_table_budget_is_outer(self):
        result, _ = self.compare(clocks={3: 2})
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['tables'][0]['failure']['stage'], 'TABLE_ROW_BUDGET')
        self.assertEqual(result['matches'], [])
        result, _ = self.unavailable('TABLE_BUDGET', expired_from=3)
        self.assertEqual(result['failure']['table'], 'tcp6')
        self.assertEqual(result['partial']['tables'][0]['failure']['stage'], 'TABLE_ROW_BUDGET')
        self.assertEqual(result['partial']['matches'], [])

    def test_final_identity_retains_tables_but_never_classification(self):
        result, trace = self.unavailable('IDENTITY_AFTER', identities={2: ValueError(PRIVATE)})
        self.assertEqual(len(result['partial']['tables']), 6)
        self.assertEqual(result['partial']['matches'], [{'table': 'tcp'}])
        self.assertEqual(sum(t[0] == 'readlink' for t in trace), 1)
        self.assertNotIn('table', result['failure'])

    def test_final_fd_read_and_changed_keep_short_circuit(self):
        for value, category, number in (('socket:[456]', 'VALIDATION', None),
                (FileNotFoundError(errno.ENOENT, PRIVATE), 'NOT_FOUND', errno.ENOENT),
                (PermissionError(errno.EACCES, PRIVATE), 'PERMISSION', errno.EACCES)):
            with self.subTest(category=category):
                result, trace = self.unavailable('FD_AFTER', category, number, links={2: value})
                self.assertEqual(len(result['partial']['tables']), 6)
                self.assertEqual(sum(t[0] == 'clock' for t in trace), 8)
                self.assertNotIn('table', result['failure'])

    def test_final_deadline_only_after_matching_fd(self):
        result, trace = self.unavailable('FINAL_BUDGET', expired_from=9)
        self.assertEqual(len(result['partial']['tables']), 6)
        self.assertEqual(sum(t[0] == 'clock' for t in trace), 9)

    def test_partial_availability_keeps_local_error_and_completed_match(self):
        result, _ = self.unavailable('IDENTITY_AFTER',
            tables={'udp': PermissionError(errno.EACCES, PRIVATE)}, identities={2: ValueError(PRIVATE)})
        self.assertEqual(result['partial']['tables'][2]['failure']['error_category'], 'PERMISSION')
        self.assertEqual(result['partial']['matches'], [{'table': 'tcp'}])

    def test_unexpected_exception_keeps_only_already_completed_tables(self):
        result, trace = self.unavailable('TABLE_READ', 'OTHER',
            tables={'udp': RuntimeError(PRIVATE)})
        self.assertEqual(result['failure']['table'], 'udp')
        self.assertEqual([t['table'] for t in result['partial']['tables']], ['tcp', 'tcp6'])
        self.assertEqual(sum(t[0] == 'read' for t in trace), 3)

    def test_errno_is_bounded_and_never_stringified(self):
        for number in (-1, 4096, 10**50, True, PRIVATE, None, 0, 4095):
            error = OSError()
            error.errno = number
            result, _ = self.unavailable('IDENTITY_BEFORE', 'OS_ERROR',
                number if type(number) is int and 0 <= number <= 4095 else None,
                identities={1: error})
            self.assertLess(len(json.dumps(result)), 1024)

    def test_exception_errno_attribute_failure_does_not_mask_rejection(self):
        class HostileError(OSError):
            @property
            def errno(self):
                raise RuntimeError(PRIVATE)
        self.unavailable('FD_BEFORE', 'OS_ERROR', links={1: HostileError(PRIVATE)})

    def test_all_six_partial_matches_are_bounded_and_unverified(self):
        tables = {t: b'header\n' + row(t).encode() for t in TABLES}
        result, _ = self.unavailable('IDENTITY_AFTER', tables=tables, identities={2: ValueError(PRIVATE)})
        self.assertEqual(len(result['partial']['matches']), 6)
        self.assertLess(len(json.dumps(result)), 2048)

    def test_original_prohibition_and_scan_cleanup_on_diagnostic_failure(self):
        closed = []
        @contextmanager
        def scan(_):
            try:
                yield iter([SimpleNamespace(path='/fake/42/fd/7')])
            finally:
                closed.append(True)
        proc = SimpleNamespace(root=Path('/fake'), same=lambda identity: None)
        with patch.object(s.os, 'scandir', scan), patch.object(s.os, 'readlink', return_value=TARGET), \
                patch.object(s, 'read_bounded', side_effect=RuntimeError(PRIVATE)) as read:
            with self.assertRaisesRegex(ValueError, '^' + ERROR + '$') as caught:
                s.cpu_probe_fds(proc, {'pid': 42, 'start_ticks': 10}, time.monotonic() + 1)
        self.assertIs(type(caught.exception), ValueError)
        self.assertEqual(closed, [True])
        self.assertEqual(read.call_count, 1)
        self.assertEqual(caught.exception.socket_diagnostic['failure']['stage'], 'TABLE_READ')
        with patch.object(s, 'read_bounded', side_effect=AssertionError('No reads')):
            report = s.cpu_probe_failure_diagnostic(caught.exception, {'pid': 42, 'start_ticks': 10}, {})
        self.assertIs(report['socket_diagnostic'], caught.exception.socket_diagnostic)
        self.assertFalse(report['admission_evidence'])
        self.assertNotIn(PRIVATE, json.dumps(report))


class ExecutableCleanup(unittest.TestCase):
    setUp = fixture.SampleContract.setUp
    ARGV = s.CPU_PROBE_ARGV
    sample = fixture.SampleContract.sample

    def test_socket_failure_closes_real_verification_descriptor(self):
        # The executable file/FD is real and owned; proc identity/metadata and
        # socket target are the existing synthetic verifier fixture.
        (self.root / '102/fd/7').symlink_to(TARGET)
        actual_open, actual_close = os.open, os.close
        opened, closed = [], []
        def open_file(*args, **kwargs):
            fd = actual_open(*args, **kwargs)
            if Path(args[0]) == self.root / '102/exe':
                opened.append(fd)
            return fd
        def close_file(fd):
            closed.append(fd)
            return actual_close(fd)
        with patch.object(s.os, 'open', side_effect=open_file), \
                patch.object(s.os, 'close', side_effect=close_file):
            with self.assertRaisesRegex(ValueError, '^' + ERROR + '$') as caught:
                self.sample()
        self.assertEqual(len(opened), 1)
        self.assertEqual(closed.count(opened[0]), 1)
        with self.assertRaises(OSError) as error:
            os.fstat(opened[0])
        self.assertEqual(error.exception.errno, errno.EBADF)
        self.assertFalse(caught.exception.socket_diagnostic['admission_evidence'])


class OwnedProcessClosure(unittest.TestCase):
    def test_owned_live_process_actual_fd_closure_final_readlink(self):
        # Only an ordinary /dev/null FD is opened. The socket label and network
        # tables are synthetic. Real /proc identity and readlink observe closure.
        child = subprocess.Popen([sys.executable, '-u', '-c',
            'import os,sys\nfd=os.open("/dev/null",os.O_RDONLY)\nprint(fd,flush=True)\n'
            'for command in sys.stdin:\n'
            ' if command.strip()=="close":\n  os.close(fd)\n  print("CLOSED",flush=True)\n'
            ' else: break\n'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            fd = int(child.stdout.readline())
            proc = s.Proc()
            identity = proc.identity(child.pid)
            descriptor = f'/proc/{child.pid}/fd/{fd}'
            real_readlink, real_read = os.readlink, s.read_bounded
            self.assertEqual(real_readlink(descriptor), '/dev/null')
            calls = []
            def synthetic_link(path):
                calls.append(str(path))
                actual = real_readlink(path)
                self.assertEqual(actual, '/dev/null')
                return TARGET
            def synthetic_tables(path, bound):
                if path.parent.name != 'net':
                    return real_read(path, bound)
                if path.name == 'netlink':
                    child.stdin.write('close\n'); child.stdin.flush()
                    self.assertEqual(child.stdout.readline().strip(), 'CLOSED')
                return b'header\n' + (row('tcp').encode() if path.name == 'tcp' else b'')
            with patch.object(s.os, 'readlink', side_effect=synthetic_link), \
                    patch.object(s, 'read_bounded', side_effect=synthetic_tables):
                result = s.cpu_probe_socket_diagnostic(proc, identity, descriptor, TARGET,
                                                        time.monotonic() + 1)
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertEqual(result['failure'], {'stage': 'FD_AFTER', 'error_category': 'NOT_FOUND',
                                                 'errno': errno.ENOENT})
            self.assertEqual(len(result['partial']['tables']), 6)
            self.assertEqual(result['partial']['matches'], [{'table': 'tcp'}])
            self.assertFalse(result['partial']['identity_verified'])
            self.assertEqual(calls, [descriptor, descriptor])
            self.assertIsNone(child.poll())
            with self.assertRaises(FileNotFoundError):
                real_readlink(descriptor)
            child.communicate('exit\n', timeout=2)
            self.assertEqual(child.returncode, 0)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=2)


class Preservation(unittest.TestCase):
    def test_exact_predecessor_hash_and_only_collector_changed(self):
        source = Path(s.__file__).read_text()
        old = without_socket_failure_stage(source)
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(), PREDECESSOR_SHA256)
        from diagnostic_profile_preservation import without_diagnostic_profile
        current_ast, old_ast = ast.parse(without_diagnostic_profile(source)), ast.parse(old)
        for tree in (current_ast, old_ast):
            tree.body = [node for node in tree.body if not
                (isinstance(node, ast.FunctionDef) and node.name == 'cpu_probe_socket_diagnostic')]
        self.assertEqual(ast.dump(current_ast), ast.dump(old_ast))

    def test_reversal_rejects_missing_duplicate_and_mutated_delta(self):
        source = Path(s.__file__).read_text()
        cases = [source + source, source.replace(REVIEWED, ORIGINAL, 1)]
        for needle in ("stage = 'FD_AFTER'", "stage = 'FINAL_BUDGET'", "'identity_verified': False",
                       "'atomic_observation': False", "'errno': None", '0 <= number <= 4095',
                       "partial={", "'failure': failure(error)"):
            self.assertIn(needle, REVIEWED)
            cases.append(source.replace(needle, 'UNREVIEWED_CHANGE', 1))
        for changed in cases:
            with self.subTest(digest=hashlib.sha256(changed.encode()).hexdigest()):
                with self.assertRaises(ValueError):
                    without_socket_failure_stage(changed)

    def test_unchanged_guard_mutations_remain_visible_after_reversal(self):
        source = Path(s.__file__).read_text()
        for needle in ('CPU_PROBE_VERIFY_SECONDS = 1', 'CPU_PROBE_MAX_RSS = 64 * MIB',
                       'CPU probe socket descriptor forbidden', 'CPU probe failure remains sticky',
                       'CPU probe executable digest mismatch', 'CPU probe argument form mismatch'):
            self.assertIn(needle, source)
            changed = source.replace(needle, 'UNREVIEWED_CHANGE', 1)
            normalized = without_socket_failure_stage(changed)
            self.assertNotEqual(hashlib.sha256(normalized.encode()).hexdigest(), PREDECESSOR_SHA256)


if __name__ == '__main__':
    unittest.main()
