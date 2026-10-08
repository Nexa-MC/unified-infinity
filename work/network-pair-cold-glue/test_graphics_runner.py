"""Source/mock-only graphics producer checks. Never run package or native tools."""
import ast
import driver
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('graphics_runner', HERE / 'graphics_runner.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class GraphicsProducerSourceTests(unittest.TestCase):
    def test_prepare_only_stages_frozen_text(self):
        with tempfile.TemporaryDirectory(prefix='graphics-source-check-') as folder, \
             mock.patch('subprocess.run', side_effect=AssertionError('No package/native commands')), \
             mock.patch('subprocess.Popen', side_effect=AssertionError('No graphics commands')):
            result = g.prepare(REPO, Path(folder) / 'consumer')
            self.assertEqual(result['collector']['sha256'], g.COLLECTOR_SHA)
            self.assertEqual(result['supervisor']['sha256'], g.SUPERVISOR_SHA)
            self.assertFalse(result['graphicsStarted'])
            self.assertFalse(Path(result['lockPath']).exists())
            self.assertFalse(Path(result['provenancePath']).exists())
            self.assertIn('<actual-produced-lock-sha256>', result['commandRecipe'])
            for key in ('collector', 'supervisor'):
                ast.parse(Path(result[key]['path']).read_text())
            with self.assertRaisesRegex(ValueError, 'already staged'):
                g.prepare(REPO, Path(folder) / 'consumer')

    def test_native_dependency_parser_retains_real_paths_and_rejects_missing(self):
        output = 'linux-vdso.so.1 (0x123)\nlibGL.so.1 => /lib/x86_64-linux-gnu/libGL.so.1 (0x456)\n/lib64/ld-linux-x86-64.so.2 (0x789)\n'
        self.assertEqual(g.parse_ldd(output), {'/lib/x86_64-linux-gnu/libGL.so.1', '/lib64/ld-linux-x86-64.so.2'})
        for bad in ('libGL.so.1 => not found\n', 'malformed dependency', ''):
            with self.assertRaises(ValueError): g.parse_ldd(bad)

    def test_missing_inputs_never_start_collector(self):
        with tempfile.TemporaryDirectory(prefix='graphics-source-check-') as folder:
            plan = g.prepare(REPO, Path(folder) / 'consumer')
            missing = {'status': 'MISSING_INSTALLED_GRAPHICS_INPUTS', 'missingInputs': [{'path': '/usr/bin/Xvfb'}]}
            with mock.patch.object(g, 'observe', return_value=missing), \
                 mock.patch.object(g.subprocess, 'Popen') as launch:
                self.assertEqual(g.execute(plan), missing)
                launch.assert_not_called()

    def test_wrong_runtime_is_blocked_before_inventory_commands(self):
        with mock.patch.dict(g.os.environ, {}, clear=True), mock.patch.object(g, 'query') as query:
            with self.assertRaisesRegex(ValueError, 'GitHub CI'):
                g.observe({'root': '/does-not-exist'})
            query.assert_not_called()

    def test_early_availability_never_starts_package_or_graphics_commands(self):
        with mock.patch.dict(g.os.environ, {}, clear=True), \
             mock.patch.object(g.subprocess, 'run') as run, \
             mock.patch.object(g.subprocess, 'Popen') as popen:
            result = g.availability({})
            self.assertEqual(result['status'], 'GRAPHICS_AVAILABILITY_BLOCKED')
            self.assertEqual(result['missingInputs'][0]['input'], 'runner')
            self.assertFalse(result['graphicsStarted'])
            run.assert_not_called()
            popen.assert_not_called()

    def test_cleanup_only_signals_owned_pidfd_and_checks_real_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='graphics-cleanup-fixture-') as folder:
            path = Path(folder) / 'lifecycle.json'
            path.write_text(json.dumps({'status': 'STOPPED_BY_ORCHESTRATOR'}))
            process = mock.Mock()
            process.poll.side_effect = [None, 0]
            handle = {'process': process, 'pidfd': 42, 'log': mock.Mock(), 'lifecyclePath': str(path)}
            with mock.patch.object(g.signal, 'pidfd_send_signal') as signal, \
                 mock.patch.object(g.os, 'close') as close:
                result = g.stop(handle)
                signal.assert_called_once_with(42, g.signal.SIGTERM)
                close.assert_called_once_with(42)
                process.wait.assert_called_once_with(timeout=20)
                self.assertEqual(result['status'], 'GRAPHICS_COLLECTOR_CLEANED')


class GraphicsLifetimeAndFailureTests(unittest.TestCase):
    def exercise(self, lifetime=2520, primary=None, cleanup=None, pidfd_error=None, interrupted_at=None):
        with tempfile.TemporaryDirectory(prefix='graphics-mocked-run-') as folder:
            plan = g.prepare(REPO, Path(folder) / 'consumer')
            Path(plan['lockPath']).write_text(json.dumps({'expected_runner': {
                'ImageOS': 'ubuntu24', 'ImageVersion': '20261006.1.0'}}))
            destination = Path(plan['destination']); destination.mkdir()
            ready = {'status': 'GRAPHICS_PREFLIGHT_READY', 'collector_pid': 4321,
                     'pair_acceptance': False, 'maximum_lifetime_seconds': lifetime}
            (destination / 'ready.json').write_text(json.dumps(ready))
            supervisor = mock.Mock()
            supervisor.decode_json.side_effect = lambda data, limit: json.loads(data)
            supervisor.read_bounded.side_effect = lambda path, limit: Path(path).read_bytes()
            supervisor.verify_graphics.side_effect = primary
            collector = mock.Mock(MAX_LIFETIME=2520)
            collector.load_supervisor.return_value = supervisor
            process = mock.Mock(pid=4321)
            process.poll.return_value=None
            pending=[]
            def launch(*args, **kwargs):
                if interrupted_at == "spawn":pending.append(driver.signal.SIGTERM)
                return process
            def pidfd(_pid):
                if interrupted_at == "pidfd":pending.append(driver.signal.SIGTERM)
                if pidfd_error:raise pidfd_error
                return 42
            def check():
                if pending:driver.interrupt_driver(pending[0],None)
            if pidfd_error: process.wait.side_effect = cleanup
            spec = mock.Mock()
            observed = {'missingInputs': [], 'lock': {'sha256': '0'*64}}
            with mock.patch.object(g, 'observe', return_value=observed), \
                 mock.patch.object(g.importlib.util, 'spec_from_file_location', return_value=spec), \
                 mock.patch.object(g.importlib.util, 'module_from_spec', return_value=collector), \
                 mock.patch.object(g.subprocess, 'Popen', side_effect=launch), \
                 mock.patch.object(g.os, 'pidfd_open', side_effect=pidfd), \
                 mock.patch.object(g, 'stop', side_effect=cleanup) as stop:
                result = None; error = None
                try: result = g.execute(plan, deadline=1000000000, interrupt_check=check)
                except BaseException as caught: error = caught
                # The mocked stop deliberately performs no IO; close the real fixture log.
                if result is not None: result['handle']['log'].close()
                elif stop.call_args: stop.call_args.args[0]['log'].close()
                if pidfd_error:
                    process.terminate.assert_called_once_with()
                    process.wait.assert_called_once_with(timeout=20)
                return result, error, stop.call_count

    def test_reported_lifetime_is_actual_collector_receipt(self):
        result, error, calls = self.exercise()
        self.assertIsNone(error)
        self.assertEqual(result['maximumLifetimeSeconds'], result['ready']['maximum_lifetime_seconds'])
        self.assertEqual(result['maximumLifetimeSeconds'], 2520)
        self.assertEqual(calls, 0)

    def test_stale_lifetime_receipt_is_rejected(self):
        result, error, calls = self.exercise(lifetime=900)
        self.assertIsNone(result)
        self.assertIn('lifetime receipt differs', str(error))
        self.assertEqual(calls, 1)

    def test_startup_cleanup_failure_preserves_original_exception(self):
        primary = ValueError('fixture readiness failure')
        result, error, calls = self.exercise(primary=primary, cleanup=OSError('fixture stop failure'))
        self.assertIsNone(result)
        self.assertIs(error, primary)
        self.assertEqual(error.graphics_cleanup['status'], 'GRAPHICS_CLEANUP_FAILED')
        self.assertIn('fixture stop failure', error.graphics_cleanup['failure'])
        self.assertEqual(calls, 1)

    def test_pidfd_setup_cleanup_failure_preserves_original_exception(self):
        primary = OSError('fixture pidfd failure')
        result, error, calls = self.exercise(pidfd_error=primary, cleanup=OSError('fixture stop failure'))
        self.assertIsNone(result)
        self.assertIs(error, primary)
        self.assertIn('fixture stop failure', error.graphics_cleanup['failure'])
        self.assertEqual(calls, 0)

    def test_driver_interruption_during_pidfd_acquisition_reaps_owned_child(self):
        primary=driver.DriverInterrupted('Cold driver interrupted by SIGTERM')
        result,error,calls=self.exercise(pidfd_error=primary)
        self.assertIsNone(result);self.assertIs(error,primary);self.assertEqual(calls,0)
        self.assertEqual(error.graphics_cleanup['status'],'GRAPHICS_COLLECTOR_REAPED_BEFORE_READY')

    def test_deferred_spawn_and_pidfd_signals_cleanup_after_ownership(self):
        for phase in ('spawn','pidfd'):
            with self.subTest(phase=phase):
                result,error,calls=self.exercise(interrupted_at=phase)
                self.assertIsNone(result);self.assertIsInstance(error,driver.DriverInterrupted)
                self.assertEqual(calls,1)


if __name__ == '__main__':
    unittest.main()
