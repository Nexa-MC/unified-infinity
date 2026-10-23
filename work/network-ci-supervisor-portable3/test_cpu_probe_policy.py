"""Synthetic /proc and owned-handle models only; never execute lshw or a game."""
import ast
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import supervisor as s


def process(pid=102, parent=101, start=990, group=101, session=101, state='S', rss=4096):
    return dict(pid=pid, ppid=parent, start_ticks=start, pgrp=group, session=session,
                state=state, rss_bytes=rss)


def status(uid=1001, gid=1001):
    return (f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}\nGid:\t{gid}\t{gid}\t{gid}\t{gid}\n' +
            ''.join(key + ':\t0000000000000000\n' for key in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb')) +
            'Threads:\t1\nVmHWM:\t8 kB\n')


def proc_stat(row, cpu=10):
    fields = ['0'] * 22
    for index, value in {0: row['state'], 1: row['ppid'], 2: row['pgrp'], 3: row['session'],
                         11: cpu, 12: 0, 19: row['start_ticks'], 21: 1}.items():
        fields[index] = str(value)
    return f"{row['pid']} (lshw) " + ' '.join(fields)


class SampleContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.helper = process()
        self.parent = process(pid=101, parent=os.getpid(), start=100, group=101, session=101)
        self.java = self.root / 'java'; self.java.write_bytes(b'synthetic java')
        self.binary = self.root / 'lshw'; self.binary.write_bytes(b'synthetic trusted executable')
        self.binary.chmod(0o755)
        for row in (self.parent, self.helper):
            path = self.root / str(row['pid']); path.mkdir(); (path/'fd').mkdir()
            (path/'status').write_text(status()); (path/'stat').write_text(proc_stat(row))
        (self.root/'101/exe').symlink_to(self.java)
        (self.root/'102/exe').symlink_to(self.binary)
        (self.root/'101/cmdline').write_bytes(str(self.java).encode()+b'\0-cp\0sealed\0')
        (self.root/'102/cmdline').write_bytes(s.CPU_PROBE_ARGV)
        self.proc = s.Proc(self.root)
        self.command = [str(self.java), '-cp', 'sealed']
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(s.os, 'getresuid', return_value=(1001,)*3))
        self.stack.enter_context(patch.object(s.os, 'getresgid', return_value=(1001,)*3))
        self.stack.enter_context(patch.object(s.time, 'clock_gettime', return_value=10))
        self.stack.enter_context(patch.object(s.os, 'sysconf', side_effect=lambda key: 100 if key=='SC_CLK_TCK' else 4096))
        self.stack.enter_context(patch.object(s, 'CPU_PROBE_BYTES', self.binary.stat().st_size))
        self.stack.enter_context(patch.object(s, 'CPU_PROBE_SHA256', s.digest(self.binary)))
        self.stack.enter_context(patch.object(s, 'trusted_system_file_access'))
        self.stack.enter_context(patch.object(s, 'clean_path', side_effect=Path))
        real_readlink = os.readlink
        self.stack.enter_context(patch.object(s.os, 'readlink', side_effect=lambda path: s.CPU_PROBE_PATH if Path(path)==self.root/'102/exe' else real_readlink(path)))
        real_stat, real_fstat = os.stat, os.fstat
        def root_owned(info):
            if info.st_ino != self.binary.stat().st_ino:
                return info
            values = {key: getattr(info,key) for key in ('st_dev','st_ino','st_size','st_mode','st_nlink','st_mtime_ns','st_ctime_ns')}
            return SimpleNamespace(**values, st_uid=0, st_gid=0)
        inode = self.binary.stat().st_ino
        def metadata(info):
            if info.st_ino != inode: return info
            return SimpleNamespace(**{key:getattr(info,key) for key in ('st_dev','st_ino','st_size','st_mode','st_nlink','st_mtime_ns','st_ctime_ns')},st_uid=0,st_gid=0)
        self.stack.enter_context(patch.object(s.os, 'stat', side_effect=lambda *a,**k: metadata(real_stat(*a,**k))))
        self.stack.enter_context(patch.object(s.os, 'fstat', side_effect=lambda fd: metadata(real_fstat(fd))))
        self.stack.enter_context(patch.object(s.subprocess, 'Popen', side_effect=AssertionError('No launches')))
        self.stack.enter_context(patch.object(s.os, 'killpg', side_effect=AssertionError('No signals')))

    def sample(self, previous=None):
        return s.cpu_probe_sample(self.proc, self.helper, self.parent, self.command, previous)

    def test_exact_contract_rechecks_and_records_only_bounded_metrics(self):
        signature, metrics = self.sample()
        self.assertEqual(self.sample(signature)[0], signature)
        self.assertAlmostEqual(metrics['age_seconds'], .1)
        self.assertEqual(metrics['cpu_ticks'],10)
        self.assertNotIn(str(self.root), str(metrics))

    def test_other_argument_forms_and_secret_are_rejected_without_echo(self):
        for raw in (b'lshw\0-C\0display\0', b'lshw\0-C\0system\0', b'/usr/bin/lshw\0-class\0processor\0',
                    s.CPU_PROBE_ARGV+b'SECRET\0', s.CPU_PROBE_ARGV[:-1], b'lshw -class processor\0'):
            (self.root/'102/cmdline').write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'argument form') as err: self.sample()
            self.assertNotIn('SECRET',str(err.exception))

    def test_digest_size_mode_owner_and_executable_identity_fail_closed(self):
        with patch.object(s,'CPU_PROBE_SHA256','0'*64), self.assertRaisesRegex(ValueError,'digest'): self.sample()
        with patch.object(s,'CPU_PROBE_BYTES',123), self.assertRaisesRegex(ValueError,'metadata'): self.sample()
        self.binary.chmod(0o775)
        with self.assertRaisesRegex(ValueError,'metadata'): self.sample()
        self.binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError,'identity changed'): self.sample((0,))

    def test_changed_or_deleted_path_rejected(self):
        for path in ('/tmp/lshw', '/usr/bin/lshw (deleted)'):
            with patch.object(s.os,'readlink',return_value=path), self.assertRaisesRegex(ValueError,'path'): self.sample()

    def test_parentage_group_session_and_pid_reuse_rejected(self):
        for change in ({'ppid':999}, {'pgrp':999}, {'session':999}, {'start_ticks':991}, {'state':'Z'}):
            (self.root/'102/stat').write_text(proc_stat(dict(self.helper,**change)))
            with self.subTest(change=change), self.assertRaises(ValueError): self.sample()
        (self.root/'102/stat').write_text(proc_stat(self.helper))
        (self.root/'101/stat').write_text(proc_stat(dict(self.parent,ppid=999)))
        with self.assertRaisesRegex(ValueError,'direct-parent'): self.sample()

    def test_credentials_capabilities_threads_high_water_and_missing_evidence(self):
        base=status()
        cases=[status(uid=0),status(gid=999),base.replace('1001\t1001\t1001\t1001','1001\t0\t1001\t1001'),
               base.replace('Threads:\t1','Threads:\t2'),base.replace('8 kB','65537 kB'),base.replace('VmHWM:\t8 kB\n',''),
               base+'Uid: 1001 1001 1001 1001\n']
        cases += [base.replace(key+':\t0000000000000000',key+':\t0000000000000001') for key in ('CapInh','CapPrm','CapEff','CapAmb')]
        for value in cases:
            (self.root/'102/status').write_text(value)
            with self.subTest(value=value), self.assertRaises(ValueError): self.sample()

    def test_sampled_age_cpu_rss_and_socket_bounds(self):
        with patch.object(s.time,'clock_gettime',return_value=20),self.assertRaisesRegex(ValueError,'lifetime'):self.sample()
        (self.root/'102/stat').write_text(proc_stat(self.helper,cpu=201))
        with self.assertRaisesRegex(ValueError,'CPU budget'):self.sample()
        (self.root/'102/stat').write_text(proc_stat(self.helper))
        (self.root/'102/fd/7').symlink_to('socket:[123]')
        with self.assertRaisesRegex(ValueError,'socket'):self.sample()
        (self.root/'102/fd/7').unlink()
        original=self.proc.same
        with patch.object(self.proc,'same',side_effect=lambda row:dict(original(row),rss_bytes=s.CPU_PROBE_MAX_RSS+1) if row['pid']==102 else original(row)),self.assertRaisesRegex(ValueError,'RSS'):self.sample()

    def test_parent_command_and_executable_rechecked(self):
        (self.root/'101/cmdline').write_bytes(b'other\0')
        with self.assertRaisesRegex(ValueError,'parent command'):self.sample()
        (self.root/'101/cmdline').write_bytes(str(self.java).encode()+b'\0-cp\0sealed\0')
        (self.root/'101/exe').unlink();(self.root/'101/exe').symlink_to(self.binary)
        with self.assertRaisesRegex(ValueError,'parent executable'):self.sample()

    def test_argument_change_between_reads_and_permission_failure_not_admitted(self):
        original=s.read_bounded;count=0
        def read(path,limit):
            nonlocal count
            if Path(path)==self.root/'102/cmdline':
                count+=1
                if count==2:return b'changed\0'
            return original(path,limit)
        with patch.object(s,'read_bounded',side_effect=read),self.assertRaisesRegex(ValueError,'argument'):self.sample()
        with patch.object(self.proc,'same',side_effect=PermissionError('private')),self.assertRaises(PermissionError):self.sample()

    def test_known_zombie_is_bounded_terminal_observation_only(self):
        zombie = dict(self.helper, state='Z')
        (self.root/'102/stat').write_text(proc_stat(zombie))
        metrics = s.cpu_probe_zombie(self.proc,zombie,self.parent,self.command)
        self.assertEqual(metrics['rss_bytes'],0)
        for change in ({'pgrp':999}, {'session':999}, {'ppid':999}):
            wrong=dict(zombie,**change);(self.root/'102/stat').write_text(proc_stat(wrong))
            with self.assertRaises(ValueError):s.cpu_probe_zombie(self.proc,wrong,self.parent,self.command)
        (self.root/'102/stat').write_text(proc_stat(zombie))
        with patch.object(s.time,'clock_gettime',return_value=20),self.assertRaisesRegex(ValueError,'lifetime'):
            s.cpu_probe_zombie(self.proc,zombie,self.parent,self.command)
        (self.root/'102/status').write_text(status(uid=0))
        with self.assertRaisesRegex(ValueError,'credential'):s.cpu_probe_zombie(self.proc,zombie,self.parent,self.command)

    def test_parent_exec_after_helper_hash_is_rejected(self):
        original=self.proc.command;reads=0
        def changed(row):
            nonlocal reads
            reads+=1
            return original(row) if reads==1 else ['different']
        with patch.object(self.proc,'command',side_effect=changed),self.assertRaisesRegex(ValueError,'parent command'):
            self.sample()

    def test_ownership_hardlinks_and_mutation_are_rejected(self):
        original=s.os.fstat
        for field,value in [('st_uid',1001),('st_gid',1001),('st_nlink',2)]:
            def altered(fd):
                info=original(fd)
                if info.st_size==s.CPU_PROBE_BYTES:
                    return SimpleNamespace(**dict(vars(info),**{field:value}))
                return info
            with self.subTest(field=field),patch.object(s.os,'fstat',side_effect=altered),self.assertRaisesRegex(ValueError,'metadata'):
                self.sample()


    def test_helper_descriptor_count_is_bounded(self):
        for i in range(65):(self.root/'102/fd'/str(i)).symlink_to('/dev/null')
        with self.assertRaisesRegex(ValueError,'descriptor bound'):self.sample()



class PolicyContract(unittest.TestCase):
    def setUp(self):
        self.policy=s.CpuProbePolicy();self.parent=process(pid=101,parent=os.getpid(),start=100)
        self.child=SimpleNamespace(pid=101,poll=Mock(return_value=None))
        self.pair=SimpleNamespace(identities={'server':self.parent},children={'server':self.child},
                                  spec={'server':{'command':['java']}},proc=Mock(),report={})
        self.row=process();self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.sample=self.stack.enter_context(patch.object(s,'cpu_probe_sample',return_value=((1,),dict(age_seconds=.1,cpu_ticks=1,rss_bytes=1,high_water_rss_bytes=1))))
        self.open=self.stack.enter_context(patch.object(s.os,'pidfd_open',return_value=77))
        self.handle=self.stack.enter_context(patch.object(s,'cpu_probe_handle_live'))
        self.close=self.stack.enter_context(patch.object(s.os,'close'))
    def check(self,rows=None,members=None):
        rows=[self.row] if rows is None else rows
        return self.policy.check(self.pair,rows if members is None else members,rows)
    def test_rechecks_each_observation_and_retains_handle(self):
        self.assertEqual(self.check(),{(102,990)})
        self.check();self.assertEqual(self.sample.call_count,2);self.open.assert_called_once_with(102,0)
        self.assertEqual(self.sample.call_args.args[-1],(1,));self.assertEqual(self.pair.report['cpu_probe_policy']['observed'][0]['observations'],2)
    def test_simultaneous_limit(self):
        with self.assertRaisesRegex(ValueError,'simultaneous'):self.check([self.row,process(pid=103)])
    def test_total_count_retains_exited_and_pid_reuse_counts_fresh(self):
        for i in range(4):self.check([process(start=990+i)]);self.check([])
        with self.assertRaisesRegex(ValueError,'total instance'):self.check([process(start=994)])
    def test_adoption_unknown_parent_and_dead_parent_rejected(self):
        for parent in (os.getpid(),999):
            self.policy=s.CpuProbePolicy()
            with self.assertRaisesRegex(ValueError,'direct game parent'):self.check([process(parent=parent)])
        self.policy=s.CpuProbePolicy();self.child.poll.return_value=0
        with self.assertRaisesRegex(ValueError,'direct game parent'):self.check()
    def test_grandchild_even_outside_group_or_zombie_rejected(self):
        for state in ('R','Z'):
            self.policy=s.CpuProbePolicy()
            with self.assertRaisesRegex(ValueError,'descendants'):self.check(members=[self.row,process(pid=103,parent=102,group=999,session=999,state=state)])
    def test_failure_sticky_and_new_handle_closed(self):
        self.sample.side_effect=ValueError('wrong hash')
        with self.assertRaises(ValueError):self.check()
        self.close.assert_called_once_with(77)
        self.sample.side_effect=None
        with self.assertRaisesRegex(ValueError,'sticky'):self.check([])
    def test_parent_exit_during_verification_rejects_and_closes(self):
        self.child.poll.side_effect=[None,0]
        with self.assertRaisesRegex(ValueError,'parent exited'):self.check()
        self.close.assert_called_once_with(77)
    def test_reap_only_owned_pidfd_and_signal_owned_handle(self):
        self.check()
        with patch.object(s.os,'waitid',return_value=SimpleNamespace(si_pid=102)) as wait:
            self.assertFalse(self.policy.cleanup_pending(self.pair));wait.assert_called_once_with(s.os.P_PIDFD,77,s.os.WEXITED|s.os.WNOHANG)
        with patch.object(s.signal,'pidfd_send_signal') as send:
            self.policy.signal_owned(self.pair,s.signal.SIGTERM);send.assert_called_once_with(77,s.signal.SIGTERM)
    def test_cleanup_detects_live_helper_without_live_java(self):
        self.check();self.child.poll.return_value=0;self.pair.proc.identity.return_value=self.row
        with patch.object(s.os,'waitid',side_effect=ChildProcessError()):self.assertTrue(self.policy.cleanup_pending(self.pair))
        self.pair.proc.identity.side_effect=FileNotFoundError()
        with patch.object(s.os,'waitid',side_effect=ChildProcessError()):self.assertFalse(self.policy.cleanup_pending(self.pair))
    def test_terminal_transition_never_becomes_live_acceptance(self):
        self.check()
        zombie=dict(self.row,state='Z')
        with patch.object(s,'cpu_probe_zombie',return_value=dict(age_seconds=.2,cpu_ticks=2,rss_bytes=0,high_water_rss_bytes=0)):
            self.assertEqual(self.check([zombie]),set())
        self.assertEqual(self.pair.report['cpu_probe_policy']['observed'][0]['terminal_observations'],1)
        with self.assertRaisesRegex(ValueError,'revived'):self.check()
    def test_unverified_zombie_rejected(self):
        with self.assertRaisesRegex(ValueError,'unverified zombie'):self.check([dict(self.row,state='Z')])
    def test_fixed_policy_reason_and_private_error_suppression(self):
        self.sample.side_effect=ValueError('CPU probe lifetime exceeded')
        with self.assertRaises(ValueError):self.check()
        self.assertEqual(self.pair.report['cpu_probe_policy']['failure'],'CPU probe lifetime exceeded')
        self.policy=s.CpuProbePolicy();self.sample.side_effect=PermissionError('SECRET')
        with self.assertRaises(PermissionError):self.check()
        self.assertNotIn('SECRET',str(self.pair.report))
    def test_dead_pidfd_before_or_after_sample_fails_closed(self):
        for sequence in ([ValueError('CPU probe retained handle is not live')], [None,ValueError('CPU probe retained handle is not live')]):
            self.policy=s.CpuProbePolicy();self.handle.side_effect=sequence
            with self.assertRaisesRegex(ValueError,'handle'):self.check()
            self.assertEqual(self.policy.records,{})
    def test_cleanup_errors_are_bounded_and_do_not_mask_failure(self):
        self.check();self.pair.proc.identity.side_effect=FileNotFoundError()
        with patch.object(s.os,'waitid',side_effect=OSError('SECRET')):
            self.assertTrue(self.policy.cleanup_pending(self.pair))
        self.assertTrue(self.pair.report['cleanup_incomplete']);self.assertNotIn('SECRET',str(self.pair.report))
        self.close.side_effect=OSError('SECRET');self.policy.close(self.pair)
        self.assertEqual(self.pair.report['status'],'INCONCLUSIVE');self.assertNotIn('SECRET',str(self.pair.report))
    def test_pidfd_open_failure_is_not_accepted(self):
        self.open.side_effect=PermissionError('private')
        with self.assertRaises(PermissionError):self.check()
        self.assertTrue(self.policy.failed);self.assertEqual(self.policy.records,{})

class PumpContract(unittest.TestCase):
    def test_tracked_helper_with_changed_parent_and_group_is_still_rejected(self):
        helper=process();parent=process(pid=101,parent=os.getpid(),start=100)
        policy=s.CpuProbePolicy();policy.records[(102,990)]={'role':'server','observations':1,'metrics':{}}
        escaped=process(parent=999,group=999,session=999)
        obj=SimpleNamespace(deadline=999,logs={},selector=SimpleNamespace(select=lambda _:[]),
                            children={'server':SimpleNamespace(pid=101,poll=lambda:None)},
                            identities={'server':parent},group_members={'server':[parent]},cpu_helpers=policy,
                            report={'exits':{}},proc=SimpleNamespace(same=lambda _:parent,all_identities=lambda:[parent,escaped]))
        with patch.object(s.time,'monotonic',return_value=1),patch.object(s,'rejected_children_diagnostics',return_value={}),self.assertRaisesRegex(ValueError,'CPU probe contract'):
            s.Pair.pump(obj,0)
        self.assertEqual(obj.report['unexpected_descendants'],[escaped])

if __name__=='__main__':unittest.main()
