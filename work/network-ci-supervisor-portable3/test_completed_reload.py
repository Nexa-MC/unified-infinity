"""Recovered v6 completed-reload boundary fixtures; no process or network."""
import io
import types
import unittest
from unittest.mock import patch
import supervisor


def emi(message, stamp='00:00:01'):
    return '[' + stamp + '] [EMI Reload/INFO] [EMI/]: [EMI] ' + message


def capture(rows=()):
    result = supervisor.Capture.__new__(supervisor.Capture)
    result.stream = io.BytesIO()
    result.raw, result.pending = bytearray(), bytearray()
    result.lines, result.line_observed_monotonic, result.events = [], [], {}
    for observed, message in rows:
        with patch.object(supervisor.time, 'monotonic', return_value=observed):
            result.feed((message + '\n').encode())
    return result


def ready_capture():
    return capture([(2, emi('Starting EMI reload...')), (3, emi('Reloaded EMI in 10ms'))])


class GateTests(unittest.TestCase):
    def gate(self, started=4, absent=1, hard=100):
        return supervisor.CompletedReloadGate(started, absent, hard)

    def test_missing_causal_observation_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'causal'):
            self.gate(absent=None)

    def test_causal_observation_cannot_follow_gate_entry(self):
        with self.assertRaisesRegex(ValueError, 'causal'):
            self.gate(absent=5)

    def test_exact_two_second_monotonic_dwell_required(self):
        gate = self.gate()
        gate.observe(ready_capture())
        self.assertFalse(gate.ready(4.999999, True))
        self.assertTrue(gate.ready(5, True))
        gate.before_release(5, True)
        gate.after_release(5.01)
        self.assertEqual(gate.report['observed_dwell_at_release_seconds'], 2)
        self.assertEqual(gate.report['release_call_started_monotonic'], 5)
        self.assertEqual(gate.report['release_call_returned_monotonic'], 5.01)
        self.assertTrue(gate.report['release_published'])
        self.assertEqual(gate.report['reload_start']['raw_line'], emi('Starting EMI reload...'))
        self.assertEqual(gate.report['reload_completed']['line'], 2)

    def test_dwell_not_inferred_from_log_wall_clock(self):
        gate = self.gate()
        gate.observe(capture([(2, emi('Starting EMI reload...', '00:00:01')),
                              (3, emi('Reloaded EMI in 100000ms', '23:59:59'))]))
        self.assertFalse(gate.ready(4, True))

    def test_missing_start_and_completion_never_release(self):
        gate = self.gate()
        gate.observe(capture())
        self.assertFalse(gate.ready(13.999, True))
        with self.assertRaisesRegex(ValueError, 'timeout'):
            gate.ready(14, True)
        self.assertFalse(gate.report['release_published'])

    def test_missing_completion_never_releases(self):
        gate = self.gate()
        gate.observe(capture([(2, emi('Starting EMI reload...'))]))
        with self.assertRaisesRegex(ValueError, 'two-second dwell'):
            gate.before_release(5, True)

    def test_stale_completion_without_start_rejected(self):
        gate = self.gate()
        with self.assertRaisesRegex(ValueError, 'Stale'):
            gate.observe(capture([(2, emi('Reloaded EMI in 10ms'))]))

    def test_restart_after_completion_rejected(self):
        gate = self.gate()
        log = ready_capture()
        gate.observe(log)
        with patch.object(supervisor.time, 'monotonic', return_value=4):
            log.feed((emi('Starting EMI reload...') + '\n').encode())
        with self.assertRaisesRegex(ValueError, 'later EMI reload'):
            gate.observe(log)

    def test_restart_before_completion_rejected(self):
        gate = self.gate()
        with self.assertRaisesRegex(ValueError, 'later EMI reload'):
            gate.observe(capture([(2, emi('Starting EMI reload...')), (3, emi('Starting EMI reload...'))]))

    def test_duplicate_completion_rejected(self):
        gate = self.gate()
        with self.assertRaisesRegex(ValueError, 'Duplicate EMI completion'):
            gate.observe(capture([(1, emi('Starting EMI reload...')), (2, emi('Reloaded EMI in 5ms')),
                                  (3, emi('Reloaded EMI in 5ms'))]))

    def test_cleanup_before_release_rejected(self):
        gate = self.gate()
        with self.assertRaisesRegex(ValueError, 'disconnected before'):
            gate.observe(capture([(2, emi('Disconnecting from server, EMI data cleared'))]))

    def test_late_ready_cannot_bypass_timeout(self):
        gate = self.gate()
        gate.observe(ready_capture())
        with self.assertRaisesRegex(ValueError, 'timeout'):
            gate.before_release(gate.cutoff, True)
        self.assertIsNone(gate.report['release_call_started_monotonic'])

    def test_ready_does_not_bypass_child_aliveness(self):
        gate = self.gate()
        gate.observe(ready_capture())
        with self.assertRaisesRegex(ValueError, 'process exited early'):
            gate.before_release(5, False)

    def test_absolute_causal_and_pair_deadlines_never_extended(self):
        self.assertEqual(self.gate(started=20, absent=19).cutoff, 30)
        self.assertEqual(self.gate(started=20, absent=9).cutoff, 23)
        self.assertEqual(self.gate(started=20, absent=19, hard=25).cutoff, 25)
        with self.assertRaisesRegex(ValueError, 'timeout'):
            self.gate(started=20, absent=5).ready(20, True)

    def test_publication_overrun_is_reported_failed(self):
        gate = self.gate()
        gate.observe(ready_capture())
        gate.before_release(13.9, True)
        with self.assertRaisesRegex(ValueError, 'publication exceeded'):
            gate.after_release(14)
        self.assertTrue(gate.report['release_published'])
        self.assertEqual(gate.report['release_call_returned_monotonic'], 14)

    def test_lookalike_malformed_and_wrong_logger_markers_do_not_count(self):
        log = capture([(1, 'junk ' + emi('Starting EMI reload...')),
                       (2, emi('Starting EMI reload...').replace('[EMI/]', '[Other/]')),
                       (3, emi('Reloaded EMI in nonsense'))])
        gate = self.gate()
        gate.observe(log)
        self.assertIsNone(gate.report['reload_start'])
        self.assertIsNone(gate.report['reload_completed'])

    def test_raw_bytes_and_original_probe_fail_checks_unchanged(self):
        log = capture()
        raw = (emi('Starting EMI reload...') + '\r\n').encode()
        with patch.object(supervisor.time, 'monotonic', return_value=2):
            log.feed(raw)
        self.assertEqual(bytes(log.raw), raw)
        self.assertEqual(log.stream.getvalue(), raw)
        self.assertEqual(log.line_observed_monotonic, [2])
        with self.assertRaisesRegex(ValueError, 'failure marker'):
            log.feed(b'NETWORK_CONTROL_FAIL synthetic\n')


class WaitTests(unittest.TestCase):
    def exercise(self, completion=4, exit_at=None, disconnect_at=None, restart_on_drain=False):
        clock = [3.0]
        pair = supervisor.Pair.__new__(supervisor.Pair)
        pair.deadline = 100
        pair.client_result_absent_monotonic = 1
        pair.report = {}
        pair.logs = {'client': capture([(2, emi('Starting EMI reload...'))])}
        pair.children = {r: types.SimpleNamespace(poll=lambda: 0 if exit_at is not None and clock[0] >= exit_at else None)
                         for r in ('client', 'server')}
        pending = [] if completion is None else [(completion, emi('Reloaded EMI in 10ms'))]
        socket_checks, pump_calls = [], []
        def pump(timeout):
            pump_calls.append(timeout)
            clock[0] += timeout
            while pending and pending[0][0] <= clock[0]:
                _, line = pending.pop(0)
                pair.logs['client'].feed((line + '\n').encode())
        def observe(label, connected=False):
            self.assertTrue(connected)
            if disconnect_at is not None and clock[0] >= disconnect_at:
                raise ValueError('Synthetic established loopback connection lost')
            socket_checks.append(clock[0])
        def drain():
            if restart_on_drain:
                pair.logs['client'].feed((emi('Starting EMI reload...') + '\n').encode())
        pair.pump, pair.observe, pair.drain = pump, observe, drain
        with patch.object(supervisor.time, 'monotonic', side_effect=lambda: clock[0]):
            gate = pair.wait_for_completed_reload()
        return gate, socket_checks, pump_calls

    def test_wait_keeps_pumping_and_checks_connected_through_dwell(self):
        gate, sockets, pumps = self.exercise()
        self.assertGreaterEqual(sockets[-1] - gate.report['reload_completed']['observed_monotonic'], 2)
        self.assertGreater(len(sockets), 20)
        self.assertEqual(len(sockets), len(pumps))
        self.assertLess(sockets[-1] - gate.report['gate_started_monotonic'], 10)

    def test_wait_missing_completion_times_out_without_release(self):
        with self.assertRaisesRegex(ValueError, 'timeout'):
            self.exercise(completion=None)

    def test_wait_exit_during_dwell_fails(self):
        with self.assertRaisesRegex(ValueError, 'process exited early'):
            self.exercise(exit_at=5)

    def test_wait_lost_socket_during_dwell_fails(self):
        with self.assertRaisesRegex(ValueError, 'connection lost'):
            self.exercise(disconnect_at=5)

    def test_final_drain_detects_late_restart(self):
        with self.assertRaisesRegex(ValueError, 'later EMI reload'):
            self.exercise(restart_on_drain=True)


if __name__ == '__main__':
    unittest.main()
