"""No processes or OS signals: exercise owned spawn/interruption boundaries."""
import hashlib
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from unittest import mock
import bounded_process as b
import runner_dependencies as package


class SignalFixture:
    def __init__(self):
        self.handlers={number:signal.SIG_DFL for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
        self.original=dict(self.handlers)
    def bind(self,number,handler):
        previous=self.handlers[number];self.handlers[number]=handler;return previous
    def stop(self):
        self.handlers[signal.SIGTERM](signal.SIGTERM,None)
    def patches(self):
        stack=ExitStack()
        stack.enter_context(mock.patch.object(b.signal,'getsignal',side_effect=lambda n:self.handlers[n]))
        stack.enter_context(mock.patch.object(b.signal,'signal',side_effect=self.bind))
        return stack


class OwnedSpawnTests(unittest.TestCase):
    def post_spawn_interrupt(self, code, process, callback):
        previous=sys.gettrace();seen=[]
        def trace(frame,event,arg):
            if event=='line' and frame.f_code is code and frame.f_locals.get('process') is process and not seen:
                seen.append(frame.f_lineno)
                raise KeyboardInterrupt('exact post-spawn boundary')
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt):callback()
        finally:
            sys.settrace(previous)
        self.assertEqual(len(seen),1)

    def run_build(self,process,spawn=None,cleanup=None):
        state=SignalFixture()
        def create(*args,**kwargs):
            if spawn:spawn(state)
            return process
        with state.patches(), mock.patch.object(b.subprocess,'Popen',side_effect=create) as popen, \
             mock.patch.object(b,'members',return_value=[]), \
             mock.patch.object(b,'stop_group',side_effect=cleanup) as stop:
            try:
                result=b.run(['fixture'],cwd='/',env={},stdout=None,stderr=None,timeout=1)
                return result,stop
            finally:
                self.assertEqual(state.handlers,state.original)
                self.last_stop=stop

    def test_success_reaps_before_return_and_restores_handlers(self):
        p=mock.Mock(pid=123);p.wait.return_value=0
        result,stop=self.run_build(p)
        self.assertEqual(result.returncode,0);p.wait.assert_called_once();stop.assert_not_called()

    def test_stop_during_spawn_retains_exact_child_for_cleanup(self):
        p=mock.Mock(pid=123)
        with self.assertRaisesRegex(InterruptedError,'SIGTERM'):
            self.run_build(p,spawn=lambda state:state.stop())
        self.last_stop.assert_called_once_with(p)

    def test_wait_interrupt_cleans_exact_child(self):
        p=mock.Mock(pid=123);p.wait.side_effect=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_build(p)
        self.last_stop.assert_called_once_with(p)

    def test_exact_post_spawn_line_is_inside_build_cleanup(self):
        p=mock.Mock(pid=123)
        self.post_spawn_interrupt(b.run.__code__,p,lambda:self.run_build(p))
        self.last_stop.assert_called_once_with(p)

    def test_failed_spawn_never_signals_unknown_process(self):
        p=mock.Mock()
        def fail(_state):raise OSError('spawn failed')
        with self.assertRaisesRegex(OSError,'spawn failed'):self.run_build(p,spawn=fail)
        self.last_stop.assert_not_called();p.wait.assert_not_called()

    def test_cleanup_failure_retains_original_interruption(self):
        p=mock.Mock(pid=123);p.wait.side_effect=KeyboardInterrupt()
        def fail(_process):raise RuntimeError('cleanup fixture failure')
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_build(p,cleanup=fail)
        self.assertIn('cleanup fixture failure',str(caught.exception.__notes__))

    def test_nonzero_exit_is_not_reported_success(self):
        p=mock.Mock(pid=123);p.wait.return_value=7
        result,_=self.run_build(p);self.assertEqual(result.returncode,7)

    def test_expired_budget_never_spawns(self):
        with mock.patch.object(b.subprocess,'Popen') as popen:
            with self.assertRaises(TimeoutError):b.run([],cwd='/',env={},stdout=None,stderr=None,timeout=0)
            popen.assert_not_called()

    def test_stop_at_context_exit_cannot_be_lost(self):
        state=SignalFixture()
        with state.patches():
            with self.assertRaises(InterruptedError):
                with b.owned_stops() as check:
                    check();state.stop()
            self.assertEqual(state.handlers,state.original)

    def test_ignored_stop_remains_ignored(self):
        state=SignalFixture();state.handlers[signal.SIGHUP]=signal.SIG_IGN;state.original=dict(state.handlers)
        with state.patches():
            with b.owned_stops():self.assertEqual(state.handlers[signal.SIGHUP],signal.SIG_IGN)
            self.assertEqual(state.handlers,state.original)

    def install(self,process,spawn=None):
        state=SignalFixture();content=b'fixture only'
        def create(*args,**kwargs):
            if spawn:spawn(state)
            return process
        with tempfile.TemporaryDirectory() as folder, state.patches(), \
             mock.patch.object(package,'SIZE',len(content)), \
             mock.patch.object(package,'SHA256',hashlib.sha256(content).hexdigest()), \
             mock.patch.object(package,'query',return_value=mock.Mock(returncode=0,stdout='Package: mesa-utils-bin\nVersion: 9.0.0-2\nArchitecture: amd64\n')), \
             mock.patch.object(package.subprocess,'Popen',side_effect=create):
            path=Path(folder)/'fixture';path.write_bytes(content)
            try:return package.install_deb(path,time.monotonic()+120)
            finally:self.assertEqual(state.handlers,state.original)

    def test_package_spawn_stop_waits_for_owned_root_timeout(self):
        p=mock.Mock();p.wait.return_value=0
        with self.assertRaises(InterruptedError):self.install(p,spawn=lambda state:state.stop())
        p.wait.assert_called_once_with(timeout=70)

    def test_package_wait_interrupt_is_reaped(self):
        p=mock.Mock();p.wait.side_effect=[KeyboardInterrupt(),0]
        with self.assertRaises(KeyboardInterrupt):self.install(p)
        self.assertEqual(p.wait.call_count,2)

    def test_exact_post_spawn_line_is_inside_package_cleanup(self):
        p=mock.Mock();p.wait.return_value=0
        self.post_spawn_interrupt(package.install_deb.__code__,p,lambda:self.install(p))
        p.wait.assert_called_once_with(timeout=70)

    def test_package_spawn_failure_has_no_unowned_wait(self):
        p=mock.Mock()
        def fail(_state):raise OSError('package spawn failed')
        with self.assertRaises(OSError):self.install(p,spawn=fail)
        p.wait.assert_not_called()


if __name__=='__main__':unittest.main()
