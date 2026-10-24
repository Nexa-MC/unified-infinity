"""Bounded isolated Linux lifecycle checks plus synthetic refusal/identity races."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import supervisor as s

PRIMARY_FAILURE = 'ValueError: Unexpected game descendant or CPU probe contract violation'


def identity(pid=302, parent=None, start=200, group=301, session=301, state='Z'):
    return dict(pid=pid, ppid=os.getpid() if parent is None else parent,
                start_ticks=start, pgrp=group, session=session, state=state, rss_bytes=0)


class ExactOwnedZombie(unittest.TestCase):
    def setUp(self):
        self.owner = identity(pid=301, start=100, state='S')
        self.row = identity()
        self.pair = s.Pair({'target': 'native-neoforge'}, Path('/unused'))
        self.addCleanup(self.pair.selector.close)
        self.pair.children = {'server': SimpleNamespace(pid=301)}
        self.pair.identities = {'server': self.owner}
        self.pair.report['failure'] = PRIMARY_FAILURE
        self.pair.cpu_helpers.failed = True
        self.pair.proc = SimpleNamespace(all_identities=lambda: [self.row],
                                         identity=Mock(side_effect=lambda _: dict(self.row)))

    def call(self, until=None):
        return self.pair.adopted_group_cleanup_pending(time.monotonic() + 1 if until is None else until)

    def test_exact_adopted_terminal_identity_reaped_by_pidfd_only(self):
        with patch.object(s.os, 'pidfd_open', return_value=77) as opened, \
             patch.object(s.os, 'waitid', return_value=SimpleNamespace(si_pid=302)) as waited, \
             patch.object(s.os, 'close') as closed, \
             patch.object(s.os, 'kill', side_effect=AssertionError('No PID signal')), \
             patch.object(s.os, 'killpg', side_effect=AssertionError('No new signal')):
            self.assertFalse(self.call())
        opened.assert_called_once_with(302, 0)
        waited.assert_called_once_with(os.P_PIDFD, 77, os.WEXITED | os.WNOHANG)
        closed.assert_called_once_with(77)
        self.assertEqual(self.pair.report['adopted_group_zombies_reaped'],
                         [dict(role='server', pid=302, start_ticks=200, pgrp=301, session=301)])
        self.assertEqual(self.pair.report['failure'], PRIMARY_FAILURE)
        self.assertTrue(self.pair.cpu_helpers.failed)
        self.assertFalse(self.pair.report['passed'])

    def test_direct_unrelated_out_of_group_or_older_child_is_not_reaped(self):
        for change in ({'pid': 301}, {'ppid': 999}, {'pgrp': 999}, {'session': 999},
                       {'start_ticks': 99}):
            with self.subTest(change=change), patch.object(s.os, 'pidfd_open') as opened:
                self.row = dict(identity(), **change)
                self.assertFalse(self.call())
                opened.assert_not_called()
        self.row = identity()
        self.pair.children = {}
        with patch.object(s.os, 'pidfd_open') as opened:
            self.assertFalse(self.call())
            opened.assert_not_called()

    def test_existing_retained_helper_owns_its_reaping(self):
        self.pair.cpu_helpers.records[(302, 200)] = {'pidfd': 88}
        with patch.object(s.os, 'pidfd_open') as opened:
            self.assertFalse(self.call())
            opened.assert_not_called()

    def test_live_adopted_child_keeps_bounded_cleanup_active_without_new_signal(self):
        self.row['state'] = 'S'
        with patch.object(s.os, 'pidfd_open') as opened:
            self.assertTrue(self.call())
            opened.assert_not_called()

    def test_deadline_prevents_new_pidfd_or_wait(self):
        with patch.object(s.os, 'pidfd_open') as opened:
            self.assertTrue(self.call(until=time.monotonic() - 1))
            opened.assert_not_called()

    def test_every_identity_field_is_resampled_after_pidfd_open(self):
        for key in ('pid', 'ppid', 'start_ticks', 'pgrp', 'session', 'state'):
            with self.subTest(key=key), patch.object(s.os, 'pidfd_open', return_value=77), \
                 patch.object(s.os, 'waitid') as waited, patch.object(s.os, 'close') as closed:
                self.pair.proc.identity = Mock(return_value=dict(self.row, **{key: 'S' if key == 'state' else 999}))
                self.assertTrue(self.call())
                waited.assert_not_called()
                closed.assert_called_once_with(77)
                self.assertTrue(self.pair.report['cleanup_incomplete'])
                self.assertEqual(self.pair.report['failure'], PRIMARY_FAILURE)

    def test_nonwaitable_pidfd_keeps_cleanup_pending(self):
        with patch.object(s.os, 'pidfd_open', return_value=77), \
             patch.object(s.os, 'waitid', return_value=None), patch.object(s.os, 'close'):
            self.assertTrue(self.call())
            self.assertNotIn('adopted_group_zombies_reaped', self.pair.report)
            self.assertEqual(self.pair.report['failure'], PRIMARY_FAILURE)

    def test_observation_denial_and_unwaitable_child_remain_incomplete(self):
        for error in (PermissionError('private detail'), ChildProcessError()):
            with self.subTest(error=type(error).__name__), \
                 patch.object(s.os, 'pidfd_open', return_value=77), \
                 patch.object(s.os, 'waitid', side_effect=error), patch.object(s.os, 'close'):
                self.assertTrue(self.call())
                self.assertTrue(self.pair.report['cleanup_incomplete'])
                self.assertEqual(self.pair.report['failure'], PRIMARY_FAILURE)
                self.assertNotIn('private detail', str(self.pair.report))


FIXTURE = r'''
import os, signal, sys, time
signal.alarm(12)
mode = sys.argv[1]
child = os.fork()
if child == 0:
    signal.alarm(12)
    if mode == 'outside_zombie':
        os.setsid()
    if mode == 'late_live':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(.02)
    os._exit(17)
print(child, flush=True)
if mode in ('initial_zombie', 'outside_zombie'):
    sys.stdin.buffer.read(1)
    os._exit(0)
while True:
    time.sleep(.02)
'''


def bounded(predicate, seconds=2):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Lifecycle fixture condition timed out')


def lifecycle(case):
    # This isolated process alone becomes a subreaper. No JVM/game/network/GUI.
    s.become_subreaper()
    def timed_out(*_):
        raise RuntimeError('Isolated lifecycle worker exceeded 18-second deadline')
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(18)
    proc = s.Proc()
    pair = leader = unrelated = None
    handles = []
    try:
        fixture_case = 'initial_zombie' if case == 'clean_zombie' else case
        leader = subprocess.Popen([sys.executable, '-c', FIXTURE, fixture_case], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        leader_identity = proc.identity(leader.pid)
        leader_fd = os.pidfd_open(leader.pid, 0)
        handles.append((leader_identity, leader_fd))
        descendant_pid = int(leader.stdout.readline())
        descendant = proc.identity(descendant_pid)
        descendant_fd = os.pidfd_open(descendant_pid, 0)
        handles.append((descendant, descendant_fd))
        assert proc.identity(descendant_pid)['start_ticks'] == descendant['start_ticks']
        with tempfile.TemporaryDirectory() as tmp:
            pair = s.Pair({'target': 'native-neoforge'}, Path(tmp))
            pair.children = {'server': leader}
            pair.identities = {'server': leader_identity}
            pair.group_members = {'server': [leader_identity]}
            pair.report['failure'] = PRIMARY_FAILURE
            pair.cpu_helpers.failed = True
            if fixture_case in ('initial_zombie', 'outside_zombie'):
                bounded(lambda: proc.identity(descendant_pid)['state'] == 'Z')
                leader.stdin.write(b'x')
                leader.stdin.flush()
                bounded(lambda: proc.identity(descendant_pid)['ppid'] == os.getpid())
            elif fixture_case == 'late_live':
                bounded(lambda: int(next(line.split()[1] for line in
                        Path('/proc', str(descendant_pid), 'status').read_text().splitlines()
                        if line.startswith('SigIgn:')), 16) & (1 << (signal.SIGTERM - 1)))
            else:
                raise AssertionError('Unknown lifecycle case')
            # An unrelated direct zombie in another session remains untouched.
            if case in ('initial_zombie', 'late_live'):
                unrelated = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(23)'], start_new_session=True)
                unrelated_identity = proc.identity(unrelated.pid)
                unrelated_fd = os.pidfd_open(unrelated.pid, 0)
                handles.append((unrelated_identity, unrelated_fd))
                bounded(lambda: proc.identity(unrelated.pid)['state'] == 'Z')
            started = time.monotonic()
            pair.cleanup()
            elapsed = time.monotonic() - started
            assert elapsed < 11, elapsed
            assert pair.report['failure'] == PRIMARY_FAILURE
            assert pair.report['passed'] is False and pair.report['status'] == 'INCONCLUSIVE'
            assert pair.cpu_helpers.failed and not pair.cpu_helpers.records
            assert leader.returncode == (-signal.SIGTERM if fixture_case == 'late_live' else 0), pair.report
            reaped = pair.report.get('adopted_group_zombies_reaped', [])
            if case == 'outside_zombie':
                assert reaped == [], pair.report
                assert proc.identity(descendant_pid)['state'] == 'Z'
                assert proc.identity(descendant_pid)['session'] != leader_identity['session']
                waited = os.waitid(os.P_PIDFD, descendant_fd, os.WEXITED | os.WNOHANG)
                assert waited.si_pid == descendant_pid and waited.si_status == 17
            else:
                assert [row['pid'] for row in reaped] == [descendant_pid], pair.report
                assert not Path('/proc', str(descendant_pid)).exists(), pair.report
            # The existing final inventory stays fail-closed for unrelated children.
            if unrelated is not None:
                assert pair.report.get('cleanup_incomplete') is True
                assert [row['pid'] for row in pair.report['surviving_owned_or_adopted_processes']] == [unrelated.pid], pair.report
                assert unrelated.wait(timeout=1) == 23
            elif case == 'outside_zombie':
                assert pair.report.get('cleanup_incomplete') is True
                assert [row['pid'] for row in pair.report['surviving_owned_or_adopted_processes']] == [descendant_pid], pair.report
            else:
                assert not pair.report.get('cleanup_incomplete'), pair.report
                assert not pair.report.get('surviving_owned_or_adopted_processes'), pair.report
            expected = ['SIGTERM', 'SIGKILL'] if fixture_case == 'late_live' else []
            assert [row['signal'] for row in pair.report['cleanup_signals']] == expected, pair.report
            print(json.dumps({'case': case, 'elapsed_seconds': round(elapsed, 3),
                              'reaped': reaped, 'primary_failure': pair.report['failure'],
                              'leader_exit': leader.returncode,
                              'unrelated_exit': unrelated.returncode if unrelated is not None else None,
                              'cleanup_incomplete': pair.report.get('cleanup_incomplete', False),
                              'refused_out_of_group': case == 'outside_zombie',
                              'owned_survivors': [], 'no_cpu_probe_admission': True}))
    finally:
        signal.alarm(0)
        # Test-owned retained handles clean up on assertions too; no broad wait
        # or PID-only signal. Fixture processes also have their own 12s lifetime.
        for row, fd in handles:
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 2
        pending = list(handles)
        while pending and time.monotonic() < deadline:
            remaining = []
            for row, fd in pending:
                try:
                    if os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG) is None:
                        remaining.append((row, fd))
                except ChildProcessError:
                    if Path('/proc', str(row['pid'])).exists():
                        remaining.append((row, fd))
            pending = remaining
            if pending:
                time.sleep(.01)
        for row, fd in handles:
            os.close(fd)
        if pair is not None:
            pair.selector.close()
        if leader is not None:
            for pipe in (leader.stdin, leader.stdout, leader.stderr):
                pipe.close()
        assert not pending, ('Lifecycle test cleanup incomplete', pending)
        assert not any(row['ppid'] == os.getpid() for row in proc.all_identities()), 'Test leaked child'


class RealIsolatedLifecycle(unittest.TestCase):
    def run_case(self, case):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--lifecycle-case', case],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=24,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence['primary_failure'], PRIMARY_FAILURE)
        self.assertEqual(evidence['owned_survivors'], [])
        self.assertTrue(evidence['no_cpu_probe_admission'])
        print('LIFECYCLE_EVIDENCE ' + result.stdout.strip())

    def test_already_adopted_unverified_zombie_is_reaped(self):
        self.run_case('initial_zombie')

    def test_adopted_out_of_group_zombie_is_not_reaped(self):
        self.run_case('outside_zombie')

    def test_owned_tree_cleanup_finishes_without_any_survivor(self):
        self.run_case('clean_zombie')

    def test_live_adoption_waits_through_escalation_and_is_reaped(self):
        self.run_case('late_live')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--lifecycle-case':
        lifecycle(sys.argv[2])
    else:
        unittest.main()
