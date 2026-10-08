"""Pure Python ownership, interruption and receipt tests; no native/JVM processes."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest import mock
import driver as d

class FakePair:
    def __init__(self, events, outcomes):
        self.events, self.outcomes, self.returncode = events, list(outcomes), None
    def wait(self, timeout):
        self.events.append(('pair.wait', timeout))
        outcome = self.outcomes.pop(0)
        if callable(outcome): outcome = outcome()
        if isinstance(outcome, BaseException): raise outcome
        self.returncode = outcome
        return outcome
    def poll(self):
        self.events.append(('pair.poll', self.returncode))
        return self.returncode
    def terminate(self): self.events.append(('pair.terminate',))

class DriverCleanupTests(unittest.TestCase):
    def run_driver(self, outcomes=None, failure=None, graphics_error=None,
                   missing=False, interrupted=None, spawn_interrupted=False, graphics_primary=None, graphics_interrupted=None, repeat_on_cleanup=False):
        events, handlers, processes = [], {}, []
        with tempfile.TemporaryDirectory() as folder, ExitStack() as patches:
            repo = Path(folder) / 'repo'; repo.mkdir()
            consumer = Path(folder) / 'consumer'; consumer.mkdir()
            plan = {'repoRoot': str(repo), 'consumerRoot': str(consumer),
                    'sourceCodeFiles': {}, 'dataFiles': {}, 'graphics': {}, 'runtime': {'steps': []}}
            (consumer / 'cold-driver-plan.json').write_text(json.dumps(plan))
            patches.enter_context(mock.patch.dict(d.os.environ, {
                'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': d.REPO,
                'GITHUB_REF': 'refs/heads/' + d.BRANCH, 'GITHUB_EVENT_NAME': 'push'}, clear=True))
            patches.enter_context(mock.patch.object(d.os, 'getuid', return_value=1000))
            patches.enter_context(mock.patch.object(d.time, 'monotonic', return_value=100))
            patches.enter_context(mock.patch('builtins.print'))
            def set_handler(number, handler):
                old = handlers.get(number, signal.SIG_DFL)
                if repeat_on_cleanup and handler == signal.SIG_IGN and callable(old):
                    for extra in d.STOP_SIGNALS:
                        current = handlers.get(extra)
                        if callable(current):current(extra, None)
                handlers[number] = handler
                return old
            patches.enter_context(mock.patch.object(d.signal, 'signal', side_effect=set_handler))
            patches.enter_context(mock.patch.object(d.subprocess, 'run', side_effect=AssertionError('No commands')))
            patches.enter_context(mock.patch.object(d, 'restore_with_deadline'))
            for module, name in ((d.runtime_restore, 'verify'), (d.build_candidate, 'execute'),
                                 (d.compile_probe, 'execute'), (d.pair_assembly, 'assemble')):
                patches.enter_context(mock.patch.object(module, name))
            patches.enter_context(mock.patch.object(d.graphics_runner, 'availability',
                return_value={'missingInputs': ['fixture missing'] if missing else []}))
            class GraphicsResult(dict):
                def get(self, key, default=None):
                    if graphics_interrupted == 'handle-access' and key == 'handle':
                        handlers[signal.SIGTERM](signal.SIGTERM, None)
                    return super().get(key, default)
            def graphics_execute(*args, **kwargs):
                if graphics_primary: raise graphics_primary
                if graphics_interrupted == 'startup-cleanup':
                    handlers[signal.SIGTERM](signal.SIGTERM, None)
                    try:kwargs['interrupt_check']()
                    except d.DriverInterrupted as error:
                        handlers[signal.SIGINT](signal.SIGINT, None)
                        handlers[signal.SIGHUP](signal.SIGHUP, None)
                        events.append(('graphics.startup-cleanup',))
                        error.graphics_cleanup={'status':'GRAPHICS_COLLECTOR_CLEANED'}
                        raise
                if graphics_interrupted == 'before-return':
                    handlers[signal.SIGTERM](signal.SIGTERM, None)
                return GraphicsResult(status='GRAPHICS_PREFLIGHT_READY', handle=object(), readyPath='fixture')
            graphics = patches.enter_context(mock.patch.object(d.graphics_runner, 'execute', side_effect=graphics_execute))
            def stop(_handle):
                events.append(('graphics.stop',))
                if graphics_error: raise graphics_error
                return {'status': 'GRAPHICS_COLLECTOR_CLEANED'}
            patches.enter_context(mock.patch.object(d.graphics_runner, 'stop', side_effect=stop))
            patches.enter_context(mock.patch.object(d.seal_pair, 'create', return_value={
                'supervisor': {'path': '/fixture/supervisor.py'}, 'spec': {'path': '/fixture/spec', 'sha256': '0'*64}}))
            def spawn(args, **kwargs):
                events.append(('pair.spawn',))
                evidence = Path(args[-1]); evidence.mkdir()
                (evidence / 'result.json').write_text(json.dumps({'passed': True, 'status': 'PASS'}))
                values = [0]
                if not processes:
                    if interrupted: values = [lambda: handlers[interrupted](interrupted, None), -15]
                    elif failure: values = [failure, -15]
                    elif outcomes is not None: values = outcomes
                    elif spawn_interrupted: values = [-15]
                process = FakePair(events, values); processes.append(process)
                if spawn_interrupted:handlers[signal.SIGTERM](signal.SIGTERM, None)
                return process
            patches.enter_context(mock.patch.object(d.subprocess, 'Popen', side_effect=spawn))
            error = None
            try: d.execute(repo, consumer)
            except BaseException as caught: error = caught
            receipt = json.loads((consumer / 'cold-pair-result.json').read_text())
            self.assertTrue(all(handlers[n] == signal.SIG_DFL for n in d.STOP_SIGNALS))
            return receipt, events, error, processes, graphics.call_count

    def assert_pair_before_graphics(self, events):
        self.assertLess(events.index(('pair.terminate',)), events.index(('pair.wait', d.PAIR_CLEANUP_SECONDS)))
        self.assertLess(events.index(('pair.wait', d.PAIR_CLEANUP_SECONDS)), events.index(('graphics.stop',)))

    def test_both_serial_pairs_succeed_then_graphics_stops(self):
        receipt, events, error, processes, _ = self.run_driver()
        self.assertIsNone(error); self.assertEqual(len(processes), 2)
        self.assertTrue(receipt['gameAcceptance'])
        self.assertEqual(receipt['pairCleanup']['status'], 'NO_ACTIVE_PAIR')
        self.assertEqual(events[-1], ('graphics.stop',))
        self.assertEqual(sum(e == ('pair.wait', d.PAIR_SECONDS) for e in events), 2)

    def test_nonzero_pair_fails_without_starting_second_pair(self):
        receipt, events, error, processes, _ = self.run_driver(outcomes=[7])
        self.assertIsInstance(error, ValueError); self.assertEqual(len(processes), 1)
        self.assertFalse(receipt['gameAcceptance']); self.assertEqual(receipt['status'], 'FAILED')
        self.assertNotIn(('pair.terminate',), events)

    def test_timeout_reaps_pair_before_graphics(self):
        receipt, events, error, processes, _ = self.run_driver(outcomes=[subprocess.TimeoutExpired('fixture',650), -15])
        self.assertIn('Pair time budget exhausted', str(error))
        self.assertTrue(receipt['pairCleanup']['reaped']); self.assertFalse(receipt['gameAcceptance'])
        self.assert_pair_before_graphics(events); self.assertEqual(len(processes), 1)

    def test_term_int_hup_take_ordered_cleanup_path(self):
        for number in d.STOP_SIGNALS:
            with self.subTest(signal=number):
                receipt, events, error, processes, _ = self.run_driver(interrupted=number)
                self.assertIsInstance(error, d.DriverInterrupted)
                self.assertIn(signal.Signals(number).name, receipt['failure'])
                self.assertFalse(receipt['gameAcceptance'])
                self.assert_pair_before_graphics(events); self.assertEqual(len(processes), 1)

    def test_signal_after_spawn_still_has_owned_pair(self):
        receipt, events, error, _, _ = self.run_driver(spawn_interrupted=True)
        self.assertIsInstance(error, d.DriverInterrupted); self.assertTrue(receipt['pairCleanup']['reaped'])
        self.assert_pair_before_graphics(events)

    def test_unreaped_pair_fails_closed_and_keeps_graphics(self):
        timeout = subprocess.TimeoutExpired('fixture', 650)
        receipt, events, error, processes, _ = self.run_driver(outcomes=[timeout, timeout])
        self.assertIn('Pair time budget exhausted', str(error)); self.assertFalse(receipt['pairCleanup']['reaped'])
        self.assertEqual(receipt['graphicsCleanup']['status'], 'SKIPPED_PAIR_NOT_REAPED')
        self.assertFalse(receipt['gameAcceptance']); self.assertNotIn(('graphics.stop',), events)
        self.assertEqual(len(processes), 1)

    def test_graphics_cleanup_failure_writes_receipt_and_revokes_acceptance(self):
        receipt, _, error, _, _ = self.run_driver(graphics_error=OSError('fixture graphics cleanup'))
        self.assertIsInstance(error, RuntimeError); self.assertEqual(receipt['status'], 'CLEANUP_FAILED')
        self.assertFalse(receipt['gameAcceptance'])
        self.assertIn('fixture graphics cleanup', receipt['cleanupErrors'][0]['failure'])

    def test_cleanup_error_preserves_primary_exception(self):
        primary = ValueError('fixture primary pair failure')
        receipt, events, error, _, _ = self.run_driver(failure=primary, graphics_error=OSError('fixture cleanup'))
        self.assertIs(error, primary)
        self.assertEqual(receipt['failure'], 'ValueError: fixture primary pair failure')
        self.assertEqual(receipt['graphicsCleanup']['status'], 'GRAPHICS_CLEANUP_FAILED')
        self.assert_pair_before_graphics(events)

    def test_no_active_pair_does_not_signal_or_start_graphics(self):
        receipt, events, error, processes, graphics_calls = self.run_driver(missing=True)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(receipt['pairCleanup']['status'], 'NO_ACTIVE_PAIR')
        self.assertEqual(events, []); self.assertEqual(processes, []); self.assertEqual(graphics_calls, 0)

    def test_graphics_startup_cleanup_failure_survives_in_final_receipt(self):
        primary = ValueError('fixture graphics startup')
        primary.graphics_cleanup = {'status': 'GRAPHICS_CLEANUP_FAILED', 'failure': 'fixture stop failure'}
        receipt, events, error, processes, _ = self.run_driver(graphics_primary=primary)
        self.assertIs(error, primary)
        self.assertEqual(receipt['graphicsCleanup'], primary.graphics_cleanup)
        self.assertEqual(receipt['cleanupErrors'][0]['component'], 'graphics')
        self.assertFalse(receipt['gameAcceptance']); self.assertEqual(processes, [])
        self.assertEqual(events, [])

    def test_collector_return_and_handle_transfer_retain_cleanup_ownership(self):
        for phase in ('before-return', 'handle-access'):
            with self.subTest(phase=phase):
                receipt, events, error, processes, _ = self.run_driver(graphics_interrupted=phase)
                self.assertIsInstance(error, d.DriverInterrupted)
                self.assertEqual(receipt['graphicsCleanup']['status'], 'GRAPHICS_COLLECTOR_CLEANED')
                self.assertEqual(events, [('graphics.stop',)]); self.assertEqual(processes, [])

    def test_repeated_signals_during_cleanup_handler_transition_preserve_receipt(self):
        receipt, events, error, _, _ = self.run_driver(interrupted=signal.SIGTERM, repeat_on_cleanup=True)
        self.assertIsInstance(error, d.DriverInterrupted)
        self.assertIn('SIGTERM', receipt['failure'])
        self.assertTrue(receipt['pairCleanup']['reaped'])
        self.assert_pair_before_graphics(events)

    def test_repeated_signals_during_graphics_startup_cleanup_preserve_first_stop(self):
        receipt, events, error, processes, _ = self.run_driver(graphics_interrupted='startup-cleanup')
        self.assertIsInstance(error, d.DriverInterrupted)
        self.assertIn('SIGTERM', receipt['failure'])
        self.assertEqual(receipt['graphicsCleanup']['status'], 'GRAPHICS_COLLECTOR_CLEANED')
        self.assertEqual(events, [('graphics.startup-cleanup',)])
        self.assertEqual(processes, [])

    def test_graphics_budget_covers_both_pairs_and_workflow_reserve(self):
        root = Path(d.__file__).resolve().parents[2]; path = root / d.graphics_runner.COLLECTOR
        spec = importlib.util.spec_from_file_location('budget_collector', path)
        collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)
        self.assertEqual(collector.MAX_LIFETIME, d.WORK_SECONDS); self.assertEqual(collector.MAX_LIFETIME, 2520)
        self.assertGreaterEqual(collector.MAX_LIFETIME, 2 * d.PAIR_SECONDS)
        self.assertEqual(d.WORK_SECONDS + 3 * 60, 45 * 60); self.assertLess(d.PAIR_CLEANUP_SECONDS + 20, 3 * 60)
        workflow = (root / '.github/workflows/network-pair.yml').read_text()
        self.assertIn('timeout-minutes: 45', workflow)
        self.assertEqual(workflow, Path(d.__file__).with_name('network-pair.yml').read_text())

if __name__ == '__main__': unittest.main()
