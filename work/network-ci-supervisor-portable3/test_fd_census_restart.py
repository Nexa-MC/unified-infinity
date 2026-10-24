"""Real owned Python FD lifecycles and synthetic fail-closed census boundaries.

No Java/lshw/game launch. Socket negative is synthetic: sandbox denies AF_UNIX creation.
"""
from contextlib import contextmanager
import errno
import hashlib
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
from fd_census_preservation import without_fd_census_restart, PREDECESSOR_SHA256


class SyntheticCensus(unittest.TestCase):
    def setUp(self):
        self.row = dict(pid=123, start_ticks=456, pgrp=123, session=123)
        self.proc = SimpleNamespace(root=Path('/synthetic'), same=Mock(return_value=self.row))
        self.until = time.monotonic() + 2

    def scan(self, names):
        @contextmanager
        def value():
            yield iter(SimpleNamespace(path='/synthetic/123/fd/'+str(n)) for n in names)
        return value()

    def call(self):
        return s.cpu_probe_fds(self.proc, self.row, self.until)

    def test_one_close_requires_whole_second_scan(self):
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan([0,1])) as scan, \
             patch.object(s.os,'readlink',side_effect=['pipe:[1]',FileNotFoundError(errno.ENOENT,'closed'),'pipe:[1]','/dev/null']) as read:
            self.assertIsNone(self.call())
        self.assertEqual(scan.call_count,2); self.assertEqual(read.call_count,4)
        self.assertEqual(self.proc.same.call_count,5)

    def test_exact_64_descriptors_allowed(self):
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan(range(64))), \
             patch.object(s.os,'readlink',return_value='/dev/null') as read:
            self.assertIsNone(self.call())
        self.assertEqual(read.call_count,64)

    def test_socket_on_second_scan_rejected(self):
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan([0])), \
             patch.object(s.os,'readlink',side_effect=[FileNotFoundError(errno.ENOENT,'closed'),'socket:[12]']), \
             self.assertRaisesRegex(ValueError,'socket descriptor'):
            self.call()

    def test_three_churned_scans_fail_without_fourth(self):
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan([0])) as scan, \
             patch.object(s.os,'readlink',side_effect=FileNotFoundError(errno.ENOENT,'closed')), \
             self.assertRaisesRegex(ValueError,'remained unstable'):
            self.call()
        self.assertEqual(scan.call_count,3)

    def test_missing_directory_never_retried(self):
        with patch.object(s.os,'scandir',side_effect=FileNotFoundError(errno.ENOENT,'directory')) as scan, \
             self.assertRaises(FileNotFoundError): self.call()
        self.assertEqual(scan.call_count,1)

    def test_permission_and_other_errors_not_retried(self):
        for error in (PermissionError(errno.EACCES,'denied'),OSError(errno.EIO,'io'),FileNotFoundError(errno.ENOTDIR,'invalid')):
            with self.subTest(error=error), patch.object(s.os,'scandir',side_effect=lambda _:self.scan([0])) as scan, \
                 patch.object(s.os,'readlink',side_effect=error), self.assertRaises(OSError): self.call()
            self.assertEqual(scan.call_count,1)

    def test_identity_change_after_closed_fd_fails(self):
        self.proc.same.side_effect=[self.row,ValueError('Process identity changed: start_ticks')]
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan([0])) as scan, \
             patch.object(s.os,'readlink',side_effect=FileNotFoundError(errno.ENOENT,'closed')), \
             self.assertRaisesRegex(ValueError,'identity changed'): self.call()
        self.assertEqual(scan.call_count,1)

    def test_65_descriptors_fail(self):
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan(range(65))), \
             patch.object(s.os,'readlink',return_value='/dev/null') as read, \
             self.assertRaisesRegex(ValueError,'bound exceeded'): self.call()
        self.assertEqual(read.call_count,64)

    def test_empty_scan_still_checks_expired_budget(self):
        self.until=time.monotonic()-1
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan([])) as scan, \
             self.assertRaisesRegex(ValueError,'bound exceeded'): self.call()
        scan.assert_not_called()

    def test_retry_does_not_renew_deadline(self):
        self.until=100
        with patch.object(s.time,'monotonic',side_effect=[99,99,100]), \
             patch.object(s.os,'scandir',side_effect=lambda _:self.scan([0])) as scan, \
             patch.object(s.os,'readlink',side_effect=FileNotFoundError(errno.ENOENT,'closed')), \
             self.assertRaisesRegex(ValueError,'bound exceeded'): self.call()
        self.assertEqual(scan.call_count,1)

    def test_complete_scan_checks_exit_identity(self):
        self.proc.same.side_effect=[self.row,FileNotFoundError(errno.ENOENT,'exited')]
        with patch.object(s.os,'scandir',side_effect=lambda _:self.scan([])), self.assertRaises(FileNotFoundError): self.call()


class RealCensus(unittest.TestCase):
    def setUp(self): self.children=[]; self.addCleanup(self.cleanup)
    def cleanup(self):
        for child in self.children:
            if child.poll() is None: child.kill()
            child.wait(timeout=2);child.stdin.close();child.stdout.close()
    def line(self,child):
        self.assertTrue(select.select([child.stdout],[],[],2)[0],'Bounded handshake expired')
        return child.stdout.readline().strip()
    def child(self,body):
        child=subprocess.Popen([sys.executable,'-c','import os,signal,socket;signal.alarm(6);'+body],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        self.children.append(child);return child
    def exercise(self,after_close,expected_error=None):
        child=self.child('fd=os.open("/dev/null",os.O_RDONLY);print(fd,flush=True);os.read(0,1);os.close(fd);'+after_close)
        fd=int(self.line(child));proc=s.Proc();row=proc.identity(child.pid);folder=proc.root/str(child.pid)/'fd';original=os.scandir;calls=[]
        @contextmanager
        def scan(path):
            self.assertEqual(Path(path),folder);calls.append(path)
            with original(path) as entries: captured=list(entries)
            if len(calls)==1:
                self.assertIn(str(fd),[x.name for x in captured]);child.stdin.write(b'c');child.stdin.flush()
                self.assertEqual(self.line(child),b'closed')
                if expected_error is FileNotFoundError: self.assertEqual(child.wait(timeout=2),0)
            yield iter(captured)
        with patch.object(s.os,'scandir',side_effect=scan):
            if expected_error:
                with self.assertRaises(expected_error):s.cpu_probe_fds(proc,row,time.monotonic()+2)
            else:self.assertIsNone(s.cpu_probe_fds(proc,row,time.monotonic()+2))
        return child,proc,row,calls
    def test_live_fd_close_restarts_complete_census(self):
        child,proc,row,calls=self.exercise('print("closed",flush=True);os.read(0,1)')
        self.assertEqual(len(calls),2);self.assertIsNone(child.poll());self.assertEqual(proc.same(row)['start_ticks'],row['start_ticks'])
    def test_live_process_with_wrong_start_ticks_refused_before_scan(self):
        child=self.child('print("ready",flush=True);os.read(0,1)')
        self.assertEqual(self.line(child),b'ready')
        proc=s.Proc();row=proc.identity(child.pid);row['start_ticks']+=1
        with patch.object(s.os,'scandir',side_effect=AssertionError('Must not scan wrong identity')), \
             self.assertRaisesRegex(ValueError,'identity changed: start_ticks'):
            s.cpu_probe_fds(proc,row,time.monotonic()+2)
        self.assertIsNone(child.poll())

    def test_exit_and_reap_during_scan_not_admitted(self):
        child,proc,row,calls=self.exercise('print("closed",flush=True);os._exit(0)',FileNotFoundError)
        self.assertEqual(len(calls),1);self.assertEqual(child.returncode,0)


class Preservation(unittest.TestCase):
    def test_exact_predecessor_hash(self):
        self.assertEqual(hashlib.sha256(without_fd_census_restart(Path(s.__file__).read_text()).encode()).hexdigest(),PREDECESSOR_SHA256)
    def test_mutation_and_duplicate_rejected(self):
        source=Path(s.__file__).read_text()
        with self.assertRaises(ValueError):without_fd_census_restart(source+source)
        for needle in ('range(3)','count <= 64','except FileNotFoundError','proc.same(expected)','socket:\\[\\d+\\]'):
            # Restrict mutation to this function, since identity calls occur elsewhere.
            start=source.index('def cpu_probe_fds(');end=source.index('\n\ndef cpu_probe_sample',start)
            changed=source[:start]+source[start:end].replace(needle,'UNREVIEWED',1)+source[end:]
            with self.subTest(needle=needle),self.assertRaises(ValueError):without_fd_census_restart(changed)

if __name__=='__main__':unittest.main()
