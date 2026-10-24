"""Fixed-round clock admission and real harmless Python process shutdown tests."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import round_deadline as r
import driver

HERE = Path(__file__).resolve().parent


class RoundDeadlineTests(unittest.TestCase):
    def admit_at(self, now, seconds=1980, attempt='1'):
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS':'true','GITHUB_RUN_ATTEMPT':attempt}), \
             mock.patch.object(r.time, 'time', return_value=now), \
             mock.patch.object(r.time, 'monotonic', return_value=100 + now-r.utc(r.START_UTC) if type(now) in (int,float) else 100), \
             mock.patch.object(r.anchor, 'read_anchor', return_value={'capturedWall': r.utc(r.START_UTC), 'capturedMonotonic': 100}):
            return r.admit(r.ROUND_ID, seconds)

    def test_fixed_identity_and_budget(self):
        self.assertEqual(r.load(), r.EXPECTED)
        start=r.utc(r.START_UTC)
        early=self.admit_at(start)
        self.assertEqual(early.work_seconds, 1980)
        self.assertEqual(early.deadline, 2080)
        late=self.admit_at(r.utc(r.START_UTC)+360)
        self.assertEqual(late.work_seconds, 1620)
        self.assertEqual(late.wall_stop, r.utc(r.START_UTC)+1980)
        self.assertEqual(self.admit_at(r.utc(r.START_UTC)+420).work_seconds,1560)

    def test_expired_future_and_malformed_clocks_rejected(self):
        for now in (r.utc(r.START_UTC)-.01,r.utc(r.START_UTC)+420+.01,
                    r.utc(r.CUTOFF_UTC)-180,r.utc(r.CUTOFF_UTC),float('nan'),float('inf'),True,'bad',None):
            with self.subTest(now=now), self.assertRaises(ValueError):self.admit_at(now)
        for value in ('2026-10-23T18:55:00+00:00','2026-10-23 18:55:00Z','2026-10-23T18:55:00.1Z','bad',None):
            with self.subTest(value=value),self.assertRaises(ValueError):r.utc(value)

    def test_oversized_noninteger_and_tiny_allowances_rejected(self):
        for value in (0,-1,1559,1981,2280,2520,999999,True,False,1980.0,float('nan'),'1980'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.admit_at(r.utc(r.START_UTC),value)

    def test_attempt_and_identity_fail_closed(self):
        for value in ('','0','2','01','bad','1.0'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.admit_at(r.utc(r.START_UTC),attempt=value)
        with mock.patch.dict(os.environ,{'GITHUB_ACTIONS':'true'},clear=True),self.assertRaises(ValueError):r.admit(r.ROUND_ID)
        with self.assertRaises(ValueError):r.admit('stale')

    def test_metadata_mutation_rejected(self):
        for key,value in (('cleanupReserveSeconds',0),('schema',True),('cutoffUtc','2026-10-24T18:55:00Z'),('maximumWorkSeconds',9999),('minimumWorkSeconds',1)):
            data=dict(r.EXPECTED);data[key]=value
            with self.subTest(key=key),mock.patch.object(r.Path,'read_text',return_value=json.dumps(data)),self.assertRaises(ValueError):r.load()

    def test_clock_rollback_cannot_extend_monotonic_deadline(self):
        window=self.admit_at(r.utc(r.START_UTC))
        with mock.patch.object(r.time,'time',return_value=r.utc(r.START_UTC)-1000),mock.patch.object(r.time,'monotonic',return_value=2079):
            self.assertEqual(window.remaining(),1)
        with mock.patch.object(r.time,'time',return_value=r.utc(r.CUTOFF_UTC)),mock.patch.object(r.time,'monotonic',return_value=101):
            self.assertLess(window.remaining(),0)
        with mock.patch.object(r.time,'time',return_value=r.utc(r.START_UTC)),mock.patch.object(r.time,'monotonic',return_value=99),self.assertRaises(ValueError):window.remaining()

    def test_watchdog_requests_one_stop_and_joins_before_return(self):
        window=mock.Mock();window.remaining.side_effect=[1,0]
        with mock.patch.object(r.os,'kill') as kill:
            guard=r.Watchdog(window);guard.start();guard.thread.join(2);guard.close()
            kill.assert_called_once_with(os.getpid(),signal.SIGTERM)
            self.assertFalse(guard.thread.is_alive())
            self.assertIn('deadline',guard.reason)

    def test_cancelled_watchdog_cannot_signal_after_join(self):
        window=mock.Mock();window.remaining.return_value=100
        with mock.patch.object(r.os,'kill') as kill:
            guard=r.Watchdog(window);guard.start();guard.close();time.sleep(.12)
            kill.assert_not_called();self.assertFalse(guard.thread.is_alive())

    def test_runtime_command_expiry_does_not_round_up_or_spawn(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(driver.time,'monotonic',return_value=10),mock.patch.object(driver.bounded_process,'run') as run:
            with self.assertRaisesRegex(ValueError,'expired'):
                driver.execute_step(Path(folder),{'name':'fixture','timeoutSeconds':1},10)
            run.assert_not_called()

    def test_precheckout_inline_gate_matches_exact_reviewed_source(self):
        workflow=(HERE.parents[1]/'.github/workflows/network-pair.yml').read_text()
        self.assertEqual(workflow,(HERE/'network-pair.yml').read_text())
        self.assertLess(workflow.index('Reject stale'),workflow.index('uses: actions/checkout'))
        block=workflow.split("          python3 - <<'PY'\n",1)[1].split('          PY\n',1)[0]
        code='\n'.join(line[10:] for line in block.splitlines())+'\n'
        self.assertEqual(code,(HERE/'first_step_anchor.py').read_text())
        self.assertIn('timeout-minutes: 36',workflow)
        self.assertIn('--work-seconds 1980',workflow)
        self.assertIn('CANCELLATION_SECONDS = 300',code)
        self.assertNotIn('Authorization',code)

    def test_preparation_elapsed_time_is_not_renewed(self):
        first=self.admit_at(r.utc(r.START_UTC))
        second=self.admit_at(r.utc(r.START_UTC)+300)
        self.assertEqual(first.deadline,second.deadline)
        self.assertEqual(first.wall_stop,second.wall_stop)
        self.assertEqual(second.work_seconds,1680)
        self.assertEqual(second.owner_cutoff()['cleanup_wall'],r.utc(r.START_UTC)+2160)
        self.assertLessEqual(second.owner_cutoff()['cleanup_wall']+300,r.utc(r.CUTOFF_UTC))

    def test_plan_validation_cannot_consume_minimum_and_then_start_work(self):
        import test_driver_cleanup
        fixture=test_driver_cleanup.DriverCleanupTests()
        original=driver.execute
        window=mock.Mock(deadline=2620);window.receipt.return_value={};window.remaining.return_value=1559
        guard=mock.Mock(reason=None);guard.thread.is_alive.return_value=False
        with mock.patch.object(driver,'execute',side_effect=lambda *a,**k:original(*a,**k,round_id=r.ROUND_ID)), \
             mock.patch.object(r,'admit',return_value=window),mock.patch.object(r,'Watchdog',return_value=guard), \
             mock.patch.object(driver.runner_dependencies,'ensure') as setup:
            receipt,events,error,processes,graphics_calls=fixture.run_driver()
        self.assertIsInstance(error,ValueError)
        self.assertIn('consumed useful-work',str(error))
        setup.assert_not_called();self.assertEqual(processes,[]);self.assertEqual(graphics_calls,0)
        self.assertFalse(receipt['gameAcceptance'])

    def test_watchdog_join_failure_cannot_skip_owned_cleanup(self):
        import test_driver_cleanup
        fixture=test_driver_cleanup.DriverCleanupTests()
        original=driver.execute
        window=mock.Mock(deadline=2620);window.receipt.return_value={};window.remaining.return_value=2520
        guard=mock.Mock(reason='fixture');guard.close.side_effect=ValueError('join failed')
        guard.thread.is_alive.return_value=False
        primary=ValueError('primary pair failure')
        with mock.patch.object(driver,'execute',side_effect=lambda *a,**k:original(*a,**k,round_id=r.ROUND_ID)), \
             mock.patch.object(r,'admit',return_value=window),mock.patch.object(r,'Watchdog',return_value=guard):
            receipt,events,error,_,_=fixture.run_driver(failure=primary)
        self.assertIs(error,primary)
        self.assertTrue(receipt['pairCleanup']['reaped'])
        self.assertIn(('graphics.stop',),events)
        self.assertEqual(receipt['cleanupErrors'][0]['component'],'round-watchdog')
        self.assertFalse(receipt['gameAcceptance'])

    def test_real_watchdog_stops_owned_child_and_grandchild(self):
        # Isolate the self-SIGTERM test from unittest; no Java, native helper,
        # download or installation. Both descendants ignore TERM to test KILL.
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'exercise.py'
            script.write_text('''import os, signal, subprocess, sys, time
from pathlib import Path
import round_deadline as r
import bounded_process as b
root=Path(sys.argv[1])
child_code="import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(60)"
parent_code="import signal,subprocess,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); p=subprocess.Popen([sys.executable,'-c',sys.argv[1]]); print('parent',__import__('os').getpid(),flush=True); time.sleep(60)"
now=time.time();mono=time.monotonic()
window=r.Window(mono+.7,now+.7,now,mono,1)
guard=r.Watchdog(window)
signal.signal(signal.SIGTERM,lambda n,f: (_ for _ in ()).throw(RuntimeError('stop outside ownership')))
started=time.monotonic()
with (root/'pids.txt').open('w') as stream:
    try:
        guard.start()
        b.run([sys.executable,'-c',parent_code,child_code],cwd=root,env=os.environ.copy(),stdout=stream,stderr=stream,timeout=60)
        raise AssertionError('deadline did not stop work')
    except InterruptedError:
        pass
    finally:
        guard.close()
assert not guard.thread.is_alive()
print('OWNED_CHILD_AND_GRANDCHILD_CLEANED',time.monotonic()-started)
''')
            env=dict(os.environ,PYTHONPATH=str(HERE),PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run([sys.executable,str(script),folder],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('OWNED_CHILD_AND_GRANDCHILD_CLEANED',result.stdout)
            pids=[int(word) for word in (Path(folder)/'pids.txt').read_text().split() if word.isdigit()]
            self.assertEqual(len(pids),2)
            for pid in pids:
                stat=Path('/proc')/str(pid)/'stat'
                if stat.exists():self.assertIn(stat.read_text().rsplit(')',1)[1].split()[0],('Z','X'))

    def test_real_early_platform_style_interrupt_cleans_without_acceptance(self):
        # Simulate the documented first cancellation signal, not a real GitHub
        # cancellation. The always-alive outer test owns the isolated process.
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'exercise.py'
            script.write_text('''import os, signal, subprocess, sys, time, threading
from pathlib import Path
import round_deadline as r
import bounded_process as b
root=Path(sys.argv[1])
child_code="import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(60)"
parent_code="import signal,subprocess,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); p=subprocess.Popen([sys.executable,'-c',sys.argv[1]]); print('parent',__import__('os').getpid(),flush=True); time.sleep(60)"
now=time.time();mono=time.monotonic()
window=r.Window(mono+.7,now+.7,now,mono,1)
guard=threading.Timer(.7,lambda:os.kill(os.getpid(),signal.SIGINT))
signal.signal(signal.SIGTERM,lambda n,f: (_ for _ in ()).throw(RuntimeError('stop outside ownership')))
started=time.monotonic()
with (root/'pids.txt').open('w') as stream:
    try:
        guard.start()
        b.run([sys.executable,'-c',parent_code,child_code],cwd=root,env=os.environ.copy(),stdout=stream,stderr=stream,timeout=60)
        raise AssertionError('deadline did not stop work')
    except InterruptedError:
        pass
    finally:
        guard.cancel();guard.join(1)
assert not guard.is_alive()
print('EARLY_INTERRUPT_REJECTED_AND_OWNED_GROUP_CLEANED',time.monotonic()-started)
''')
            env=dict(os.environ,PYTHONPATH=str(HERE),PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run([sys.executable,str(script),folder],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('EARLY_INTERRUPT_REJECTED_AND_OWNED_GROUP_CLEANED',result.stdout)
            pids=[int(word) for word in (Path(folder)/'pids.txt').read_text().split() if word.isdigit()]
            self.assertEqual(len(pids),2)
            for pid in pids:
                stat=Path('/proc')/str(pid)/'stat'
                if stat.exists():self.assertIn(stat.read_text().rsplit(')',1)[1].split()[0],('Z','X'))


if __name__=='__main__':unittest.main()
