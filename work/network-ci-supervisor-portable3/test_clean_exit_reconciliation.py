"""Final owned exits: deterministic ordering, frozen gates, bounded real children.

The terminal slice is compiled from Pair.run itself, without running any game,
graphics, external input setup or downloaded executable. Pair.wait/pump/drain
are the actual production methods. Real fixtures use only this Python runtime.
"""
import ast
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import supervisor as s


RECONCILIATION_BLOCK = '''            # A wait predicate may reap after pump; console drain need not pump again.
            # Read the retained owned children, never infer success from cached exits.
            for role, child in self.children.items():
                require(role in self.identities and child.pid == self.identities[role]['pid'],
                        'Owned child identity mismatch at final exit reconciliation')
                self.report['exits'][role] = child.poll()
'''
PREDECESSOR_SHA256 = 'e88b507a406f57712c1b6f1d8bccd3e3bfb267412f1771b7f26244ef446aea81'
EXIT_GATE = "require(set(self.children) == {'server', 'client'} and self.report['exits'] == {'server': 0, 'client': 0}, 'Both owned clean exits required')"


def terminal_slice():
    """Compile only the actual final reconciliation, exit, group and adopted gates."""
    tree = ast.parse(Path(s.__file__).read_text())
    pair = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Pair')
    run = next(n for n in pair.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    body = next(n for n in run.body if isinstance(n, ast.Try)).body
    gate = next(i for i, n in enumerate(body) if ast.unparse(n) == EXIT_GATE)
    start = gate
    if isinstance(body[gate - 1], ast.For) and ast.unparse(body[gate - 1].iter) == 'self.children.items()':
        start -= 1
    return compile(ast.Module(body=body[start:], type_ignores=[]), s.__file__, 'exec')


def accept(pair):
    exec(terminal_slice(), dict(vars(s), self=pair))


def identity(pid):
    return dict(pid=pid, ppid=os.getpid(), start_ticks=5, pgrp=pid, session=pid, state='S')


class SyntheticExitReconciliation(unittest.TestCase):
    def setUp(self):
        self.pair = s.Pair({'target': 'fixture'}, Path('/unused'))
        self.addCleanup(self.pair.selector.close)
        self.pair.selector.close()
        self.pair.selector = SimpleNamespace(select=Mock(return_value=[]), close=lambda: None)
        self.pair.identities = {'server': identity(301), 'client': identity(302)}
        self.pair.group_members = {r: [i] for r, i in self.pair.identities.items()}
        self.pair.proc = SimpleNamespace(same=Mock(), all_identities=Mock(return_value=[]))

    def children(self, server=0, client=0):
        self.pair.children = {
            role: SimpleNamespace(pid=pid, poll=Mock(return_value=code))
            for role, pid, code in (('server', 301, server), ('client', 302, client))}

    def test_poll_after_pump_and_empty_drain_reconciles_final_zero(self):
        self.children()
        polls = iter((None, 0, 0))
        self.pair.children['server'].poll.side_effect = lambda: next(polls)
        self.pair.wait(lambda: self.pair.children['server'].poll() == 0, 1, 'Fixture stop')
        self.assertEqual(self.pair.report['exits'], {'client': 0})
        self.pair.drain()
        self.assertEqual(self.pair.report['exits'], {'client': 0})
        self.assertEqual(self.pair.children['server'].poll.call_count, 2)
        accept(self.pair)
        self.assertEqual(self.pair.report['exits'], {'server': 0, 'client': 0})
        self.assertTrue(self.pair.report['passed'])
        self.assertEqual(self.pair.children['server'].poll.call_count, 3)

    def test_stale_zero_never_accepts_live_nonzero_or_signal_exit(self):
        for role in ('server', 'client'):
            for code in (None, 1, 23, -signal.SIGTERM):
                with self.subTest(role=role, code=code):
                    self.children(**{role: code})
                    self.pair.report.update(passed=False, exits={'server': 0, 'client': 0})
                    with self.assertRaisesRegex(ValueError, 'Both owned clean exits required'):
                        accept(self.pair)
                    self.assertEqual(self.pair.report['exits'][role], code)
                    self.assertFalse(self.pair.report['passed'])

    def test_missing_role_rejected_even_with_cached_both_zero(self):
        for missing in ('server', 'client'):
            with self.subTest(missing=missing):
                self.children()
                del self.pair.children[missing]
                self.pair.report['exits'] = {'server': 0, 'client': 0}
                with self.assertRaisesRegex(ValueError, 'Both owned clean exits required'):
                    accept(self.pair)

    def test_extra_role_rejected_even_when_its_owned_child_exited_zero(self):
        self.children()
        self.pair.children['other'] = SimpleNamespace(pid=303, poll=Mock(return_value=0))
        self.pair.identities['other'] = identity(303)
        with self.assertRaisesRegex(ValueError, 'Both owned clean exits required'):
            accept(self.pair)

    def test_missing_identity_refused_before_that_child_is_polled(self):
        self.children()
        del self.pair.identities['server']
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        with self.assertRaisesRegex(ValueError, 'Owned child identity mismatch'):
            accept(self.pair)
        self.pair.children['server'].poll.assert_not_called()

    def test_retained_pid_mismatch_refused_before_that_child_is_polled(self):
        self.children()
        self.pair.children['server'].pid = 999
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        with self.assertRaisesRegex(ValueError, 'Owned child identity mismatch'):
            accept(self.pair)
        self.pair.children['server'].poll.assert_not_called()

    def test_poll_denial_propagates_without_acceptance(self):
        self.children()
        self.pair.children['server'].poll.side_effect = PermissionError('fixture denial')
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        with self.assertRaises(PermissionError):
            accept(self.pair)
        self.assertFalse(self.pair.report['passed'])

    def test_live_group_and_adopted_zombie_checks_still_reject(self):
        for row, message in ((dict(identity(900), pgrp=301, ppid=999), 'Game process group survived'),
                             (dict(identity(900), state='Z'), 'Adopted game helper survived')):
            with self.subTest(message=message):
                self.children()
                self.pair.report.update(passed=False, exits={})
                self.pair.proc.all_identities.return_value = [row]
                with self.assertRaisesRegex(ValueError, message):
                    accept(self.pair)
                self.assertFalse(self.pair.report['passed'])


class FrozenAcceptancePreservation(unittest.TestCase):
    def test_exact_addition_is_the_only_supervisor_byte_change(self):
        source = Path(s.__file__).read_text()
        self.assertEqual(source.count(RECONCILIATION_BLOCK), 1)
        self.assertEqual(source.count(RECONCILIATION_BLOCK + '            ' + EXIT_GATE), 1)
        original = source.replace(RECONCILIATION_BLOCK, '', 1)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), PREDECESSOR_SHA256)

    def test_gate_mutations_are_not_normalized_or_forgiven(self):
        source = Path(s.__file__).read_text()
        self.assertEqual(source.count(RECONCILIATION_BLOCK), 1)
        original = source.replace(RECONCILIATION_BLOCK, '', 1)
        for text in (EXIT_GATE, "self.probe_results(nonce)",
                     "no_new_oom_events(self.report['initial_memory_gate'])",
                     "verify_pair_seal(seal_path, seal_sha, self.spec)",
                     "require(any('All dimensions are saved' in line for line in self.logs['server'].lines[offset:]), 'Missing final all-dimensions save')",
                     "'Unexpected role/event combination'", "'Game process group survived'",
                     "'Adopted game helper survived or requires reaping'"):
            with self.subTest(gate=text):
                self.assertIn(text, original)
                altered = original.replace(text, 'REMOVED_GATE', 1)
                self.assertNotEqual(hashlib.sha256(altered.encode()).hexdigest(), PREDECESSOR_SHA256)


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'WNOWAIT'), 'Linux bounded waitid fixture')
class RealOwnedExitReconciliation(unittest.TestCase):
    def setUp(self):
        self.started = time.monotonic()
        self.processes = []
        self.pair = s.Pair({'target': 'fixture'}, Path('/unused'))
        self.pair.deadline = self.started + 8
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for child in self.processes:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)
            child.stdin.close()
        self.pair.selector.close()

    def child(self, role, code=0):
        program = 'import os,signal; signal.alarm(6); os.read(0,1); os._exit(%d)' % code
        child = subprocess.Popen([sys.executable, '-c', program], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        self.processes.append(child)
        self.pair.children[role] = child
        row = self.pair.proc.identity(child.pid)
        self.pair.identities[role] = row
        self.pair.group_members[role] = [row]
        return child

    def release_waitable_without_reaping(self, child):
        self.assertIsNone(child.returncode)
        child.stdin.write(b'x')
        child.stdin.flush()
        until = min(self.pair.deadline, time.monotonic() + 2)
        while time.monotonic() < until:
            if os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                self.assertIsNone(child.returncode)
                return
            time.sleep(.001)
        self.fail('Fixture child did not exit within its bounded budget')

    def test_real_wait_predicate_reaps_after_pump_and_empty_drain(self):
        server, client = self.child('server'), self.child('client')
        self.release_waitable_without_reaping(client)
        self.assertEqual(client.poll(), 0)
        pump = self.pair.pump
        def pump_then_release(timeout=.1):
            pump(0)
            self.assertNotIn('server', self.pair.report['exits'])
            self.release_waitable_without_reaping(server)
        self.pair.pump = pump_then_release
        self.pair.wait(lambda: server.poll() == 0, 2, 'Real fixture stop')
        self.pair.drain()
        self.assertEqual(self.pair.report['exits'], {'client': 0})
        self.assertEqual(server.returncode, 0)
        accept(self.pair)
        self.assertEqual(self.pair.report['exits'], {'server': 0, 'client': 0})
        self.assertTrue(self.pair.report['passed'])
        self.assertLess(time.monotonic() - self.started, 8)

    def test_real_nonzero_overwrites_stale_zero_and_rejects(self):
        server, client = self.child('server', 23), self.child('client')
        for child in (server, client):
            self.release_waitable_without_reaping(child)
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        with self.assertRaisesRegex(ValueError, 'Both owned clean exits required'):
            accept(self.pair)
        self.assertEqual(self.pair.report['exits'], {'server': 23, 'client': 0})
        self.assertFalse(self.pair.report['passed'])

    def test_real_live_overwrites_stale_zero_and_rejects_without_waiting(self):
        server, client = self.child('server'), self.child('client')
        self.release_waitable_without_reaping(client)
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        before = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'Both owned clean exits required'):
            accept(self.pair)
        self.assertIsNone(self.pair.report['exits']['server'])
        self.assertIsNone(server.poll())
        self.assertLess(time.monotonic() - before, 1)
        self.assertFalse(self.pair.report['passed'])

    def test_real_missing_role_rejects_even_with_stale_zero(self):
        client = self.child('client')
        self.release_waitable_without_reaping(client)
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        with self.assertRaisesRegex(ValueError, 'Both owned clean exits required'):
            accept(self.pair)
        self.assertFalse(self.pair.report['passed'])

    def test_real_retained_pid_mismatch_rejects(self):
        server, client = self.child('server'), self.child('client')
        for child in (server, client):
            self.release_waitable_without_reaping(child)
        self.pair.identities['server'] = dict(self.pair.identities['server'], pid=server.pid + 100000)
        self.pair.report['exits'] = {'server': 0, 'client': 0}
        with self.assertRaisesRegex(ValueError, 'Owned child identity mismatch'):
            accept(self.pair)
        self.assertIsNone(server.returncode)
        self.assertFalse(self.pair.report['passed'])


if __name__ == '__main__':
    unittest.main()
