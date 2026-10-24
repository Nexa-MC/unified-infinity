"""Real retained pidfd retirement seam; exact lshw/Java admission is not simulated as passed."""
import hashlib
import errno
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
import test_cpu_probe_policy as base_tests

class SourcePreservation(unittest.TestCase):
    def test_exact_previous_source(self):
        from helper_retirement_preservation import without_helper_retirement, PREDECESSOR_SHA256
        original=without_helper_retirement(Path(s.__file__).read_text())
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),PREDECESSOR_SHA256)

class RealRetirement(unittest.TestCase):
    def setUp(self):
        self.proc=s.Proc()
        self.child=subprocess.Popen([sys.executable,'-c','import sys; sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE)
        self.fd=os.pidfd_open(self.child.pid,0)
        self.row=self.proc.identity(self.child.pid)
        parent=self.proc.identity(os.getpid())
        self.old=dict(role='server',identity=dict(self.row),observations=2,terminal_observations=0,pidfd=self.fd)
        self.pair=SimpleNamespace(proc=self.proc,identities={'server':parent},children={'server':SimpleNamespace(poll=Mock(return_value=None))},spec={'server':{'command':[sys.executable]}},cpu_helpers=SimpleNamespace(records={(self.row['pid'],self.row['start_ticks']):self.old}))
        self.members=self.proc.all_identities(); self.parent=parent
        self.parent_patch=patch.object(s,'cpu_probe_parent',return_value=('verified-parent',));self.parent_patch.start()
        self.addCleanup(self.cleanup)
    def cleanup(self):
        self.parent_patch.stop()
        if self.child.poll() is None:self.child.kill()
        self.child.wait(timeout=2)
        if self.child.stdin:self.child.stdin.close()
        os.close(self.fd)
    def exit(self):
        self.child.stdin.write(b'x');self.child.stdin.flush();self.child.wait(timeout=2)
        try:self.proc.identity(self.row['pid'])
        except FileNotFoundError as e:return e
        self.fail('Child was not reaped')
    def run_retire(self,error,old='default',deadline=None):
        s.cpu_probe_retired(self.pair,self.row,'server',self.old if old=='default' else old,self.members,error,time.monotonic()+1 if deadline is None else deadline)
    def test_real_reaped_pidfd_terminal_and_absence(self):
        error=self.exit();self.run_retire(error)
        self.assertEqual(self.old['observations'],2)
    def test_policy_uses_actual_retained_pidfd_after_real_stat_race(self):
        policy=s.CpuProbePolicy();self.pair.cpu_helpers=policy;self.pair.report={}
        self.old.update(signature=('test-only-prior-signature',),metrics=dict(age_seconds=0,cpu_ticks=0,rss_bytes=0,high_water_rss_bytes=0),reaped=False)
        policy.records[(self.row['pid'],self.row['start_ticks'])]=self.old
        def race(*args,**kwargs):
            error=self.exit()
            raise error
        with patch.object(s,'cpu_probe_sample',side_effect=race):
            result=policy.check(self.pair,self.members,[self.row])
        self.assertEqual(result,{(self.row['pid'],self.row['start_ticks'])})
        self.assertEqual(self.old['observations'],2)
        self.assertEqual(self.old['terminal_observations'],1)
        self.assertTrue(self.old['retired_after_stat_race'])
        self.assertFalse(policy.failed)

    def test_real_unverified_child_rejected(self):
        error=self.exit()
        with self.assertRaisesRegex(ValueError,'evidence unavailable'):self.run_retire(error,old=None)
    def test_real_live_handle_cannot_reconcile_fabricated_missing_stat(self):
        error=FileNotFoundError(2,'missing',str(Path('/proc')/str(self.row['pid'])/'stat'))
        with self.assertRaisesRegex(ValueError,'not terminal'):self.run_retire(error)
    def test_real_reaped_pidfd_but_reused_pid_in_fresh_census_rejected(self):
        error=self.exit();reused=dict(self.row,start_ticks=self.row['start_ticks']+1)
        with patch.object(self.proc,'all_identities',return_value=[self.parent,reused]),self.assertRaisesRegex(ValueError,'identity or descendants'):self.run_retire(error)
    def test_real_terminal_handle_new_unknown_child_rejected(self):
        error=self.exit();unknown=dict(self.row,pid=self.row['pid']+100000)
        with patch.object(self.proc,'all_identities',return_value=[self.parent,unknown]),self.assertRaisesRegex(ValueError,'census changed'):self.run_retire(error)
    def test_real_terminal_handle_parent_exit_rejected(self):
        error=self.exit();self.pair.children['server'].poll.return_value=1
        with self.assertRaisesRegex(ValueError,'parent exited'):self.run_retire(error)
    def test_exact_missing_stat_only(self):
        self.exit()
        for error in [FileNotFoundError(2,'missing',f'/proc/{self.row["pid"]}/status'),FileNotFoundError(2,'missing',f'/proc/{self.row["pid"]}/fd/3'),FileNotFoundError(),FileNotFoundError(3,'wrong',f'/proc/{self.row["pid"]}/stat')]:
            with self.subTest(error=error),self.assertRaisesRegex(ValueError,'evidence unavailable'):self.run_retire(error)
    def test_poll_invalid_error_unknown_and_hup_only_rejected(self):
        error=self.exit()
        for event in [select.POLLNVAL,select.POLLERR|select.POLLIN,select.POLLPRI|select.POLLIN,select.POLLHUP,0]:
            with patch.object(s.select,'poll',return_value=SimpleNamespace(register=lambda *_:None,poll=lambda _: [(self.fd,event)])),self.assertRaisesRegex(ValueError,'not terminal'):self.run_retire(error)
    def test_expired_original_budget_rejected(self):
        error=self.exit()
        with self.assertRaisesRegex(ValueError,'budget'):self.run_retire(error,deadline=time.monotonic()-1)
    def test_parent_identity_change_during_reconciliation_rejected(self):
        error=self.exit()
        with patch.object(s,'cpu_probe_parent',side_effect=[('a',),('b',)]),self.assertRaisesRegex(ValueError,'parent changed'):self.run_retire(error)
    def test_fresh_census_permission_failure_not_swallowed(self):
        error=self.exit()
        with patch.object(self.proc,'all_identities',side_effect=PermissionError(13,'denied')),self.assertRaises(PermissionError):self.run_retire(error)
    def test_identity_relationship_change_rejected(self):
        error=self.exit();self.old['identity']['ppid']+=1
        with self.assertRaisesRegex(ValueError,'identity changed'):self.run_retire(error)
    def test_deadline_not_renewed_after_census(self):
        error=self.exit()
        with patch.object(s.time,'monotonic',side_effect=[1,3]),self.assertRaisesRegex(ValueError,'budget'):self.run_retire(error,deadline=2)

class PolicyRetirement(unittest.TestCase):
    def setUp(self):
        self.f=base_tests.PolicyContract();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.pair.cpu_helpers=self.f.policy; self.f.pair.proc.root=Path('/proc')
        self.f.check()
    def test_retired_stale_row_is_distinct_from_new_live_observation(self):
        self.f.sample.side_effect=FileNotFoundError(2,'missing','/proc/102/stat')
        with patch.object(s,'cpu_probe_retired') as retired:
            self.assertEqual(self.f.check(),{(102,990)});retired.assert_called_once()
        record=self.f.policy.records[(102,990)]
        self.assertEqual(record['observations'],1);self.assertEqual(record['terminal_observations'],1);self.assertTrue(record['retired_after_stat_race'])
        self.assertFalse(self.f.policy.failed)
        with self.assertRaisesRegex(ValueError,'revived'):self.f.check()
    def test_valueerror_socket_permission_not_reconciled(self):
        for error in [ValueError('CPU probe socket descriptor forbidden'),PermissionError(13,'denied'),ValueError('CPU probe executable digest mismatch')]:
            self.f.policy.failed=False;self.f.sample.side_effect=error
            with patch.object(s,'cpu_probe_retired') as retired,self.assertRaises(type(error)):self.f.check()
            retired.assert_not_called();self.assertTrue(self.f.policy.failed)
    def test_unknown_child_missing_stat_never_reconciled(self):
        self.f.policy.records.clear();self.f.sample.side_effect=FileNotFoundError(2,'missing','/proc/102/stat')
        with patch.object(s,'cpu_probe_retired') as retired,self.assertRaises(FileNotFoundError):self.f.check()
        retired.assert_not_called();self.f.close.assert_called_once_with(77)

if __name__=='__main__':unittest.main()
