"""Failure-only socket classification: synthetic sockets, actual read-only proc tables."""
import errno
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch
import supervisor as s
from socket_diagnostic_preservation import without_socket_diagnostic, PREDECESSOR_SHA256

TABLES = ('tcp','tcp6','udp','udp6','unix','netlink')
def row(table, inode='123'):
    if table == 'unix':return '0000: 2 0 0 0001 01 '+inode+' /DO_NOT_PUBLISH\n'
    if table == 'netlink':return '0000 0 42 0 0 0 0 2 0 '+inode+'\n'
    return '0: SECRET_LOCAL SECRET_REMOTE 01 0:0 0:0 0 1000 0 '+inode+'\n'

class SocketDiagnostic(unittest.TestCase):
    def setUp(self):
        self.proc=SimpleNamespace(root=Path('/fake'),same=Mock())
        self.identity={'pid':42,'start_ticks':10}
        self.tables={t:b'header\n' for t in TABLES}
    def call(self):
        with patch.object(s,'read_bounded',side_effect=lambda path,limit:self.tables[path.name]),patch.object(s.os,'readlink',return_value='socket:[123]'):
            return s.cpu_probe_socket_diagnostic(self.proc,self.identity,'/fake/42/fd/7','socket:[123]',time.monotonic()+1)
    def test_all_families_and_no_sensitive_table_data(self):
        for t in TABLES:
            with self.subTest(table=t):
                self.tables={k:b'header\n' for k in TABLES};self.tables[t]+=row(t).encode();d=self.call()
                self.assertEqual(d['status'],'OBSERVED');self.assertEqual(d['classification'],'MATCHED');self.assertEqual(d['matches'][0]['table'],t)
                self.assertEqual(d['fd'],7);self.assertEqual(d['inode'],'123');self.assertTrue(d['complete']);self.assertFalse(d['admission_evidence'])
                self.assertNotIn('SECRET',json.dumps(d));self.assertNotIn('DO_NOT_PUBLISH',json.dumps(d))
    def test_unresolved_is_not_safe(self):
        d=self.call();self.assertEqual(d['classification'],'UNRESOLVED');self.assertEqual(d['matches'],[])
    def test_multiple_tables_ambiguous(self):
        for t in ('tcp','unix'):self.tables[t]+=row(t).encode()
        self.assertEqual(self.call()['classification'],'AMBIGUOUS')
    def test_duplicate_inode_table_unavailable(self):
        self.tables['tcp']+=(row('tcp')*2).encode();d=self.call();self.assertFalse(d['complete']);self.assertEqual(d['matches'],[])
    def test_malformed_table_unavailable(self):
        self.tables['udp']+=b'invalid\n';d=self.call();self.assertFalse(d['complete'])
    def test_permission_tables_unavailable_not_raised(self):
        with patch.object(s,'read_bounded',side_effect=PermissionError(errno.EACCES,'denied')),patch.object(s.os,'readlink',return_value='socket:[123]'):
            d=s.cpu_probe_socket_diagnostic(self.proc,self.identity,'/fake/42/fd/7','socket:[123]',time.monotonic()+1)
        self.assertEqual(d['status'],'OBSERVED');self.assertFalse(d['complete']);self.assertEqual(d['matches'],[])
    def test_identity_change_unavailable(self):
        self.proc.same.side_effect=[None,ValueError('identity')];self.assertEqual(self.call()['status'],'UNAVAILABLE')
    def test_fd_change_unavailable(self):
        with patch.object(s.os,'readlink',return_value='socket:[124]'):
            d=s.cpu_probe_socket_diagnostic(self.proc,self.identity,'/fake/42/fd/7','socket:[123]',time.monotonic()+1)
        self.assertEqual(d['status'],'UNAVAILABLE')
    def test_expired_deadline_does_not_read(self):
        with patch.object(s,'read_bounded') as read:
            d=s.cpu_probe_socket_diagnostic(self.proc,self.identity,'/fake/42/fd/7','socket:[123]',time.monotonic()-1)
        read.assert_not_called();self.assertEqual(d['status'],'UNAVAILABLE')
    def test_row_bound(self):
        self.tables['tcp']=b'header\n'+row('tcp','99').encode()*1025
        self.assertFalse(self.call()['complete'])
    def test_byte_bound_actual_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            proc=SimpleNamespace(root=Path(directory),same=Mock());n=proc.root/'42/net';n.mkdir(parents=True)
            for t in TABLES:(n/t).write_bytes(b'header\n')
            (n/'tcp').write_bytes(b'x'*65537)
            with patch.object(s.os,'readlink',return_value='socket:[123]'):
                d=s.cpu_probe_socket_diagnostic(proc,self.identity,str(proc.root/'42/fd/7'),'socket:[123]',time.monotonic()+1)
            self.assertFalse(d['complete']);self.assertEqual(d['tables'][0]['status'],'UNAVAILABLE')
    def test_original_prohibition_preserved_and_in_memory_forwarded(self):
        from contextlib import contextmanager
        @contextmanager
        def scan(_):yield iter([SimpleNamespace(path='/fake/42/fd/7')])
        with patch.object(s.os,'scandir',scan),patch.object(s.os,'readlink',return_value='socket:[123]'),patch.object(s,'read_bounded',side_effect=PermissionError(errno.EACCES,'denied')):
            with self.assertRaisesRegex(ValueError,'^CPU probe socket descriptor forbidden$') as caught:s.cpu_probe_fds(self.proc,self.identity,time.monotonic()+1)
        with patch.object(s,'read_bounded',side_effect=AssertionError('no diagnostic reads')):
            d=s.cpu_probe_failure_diagnostic(caught.exception,self.identity,{})
        self.assertFalse(d['socket_diagnostic']['complete']);self.assertFalse(d['admission_evidence'])
    def test_read_only_real_proc_tables(self):
        # No socket is created: read this process namespace and use an unmatched
        # synthetic fd link at the classification seam. This is not socket ownership proof.
        proc=s.Proc();identity=proc.identity(os.getpid())
        with patch.object(s.os,'readlink',return_value='socket:[18446744073709551615]'):
            d=s.cpu_probe_socket_diagnostic(proc,identity,f'/proc/{os.getpid()}/fd/123','socket:[18446744073709551615]',time.monotonic()+1)
        self.assertEqual(d['status'],'OBSERVED');self.assertTrue(d['complete']);self.assertEqual(d['classification'],'UNRESOLVED')
    def test_deadline_expiring_during_tables_discards_classification(self):
        with patch.object(s.os,'readlink',return_value='socket:[123]'),patch.object(s,'read_bounded',return_value=b'header\n'),patch.object(s.time,'monotonic',side_effect=[0,0,2]):
            d=s.cpu_probe_socket_diagnostic(self.proc,self.identity,'/fake/42/fd/7','socket:[123]',1)
        self.assertEqual(d['status'],'UNAVAILABLE');self.assertNotIn('matches',d)
    def test_disappeared_process_evidence_unavailable(self):
        self.proc.same.side_effect=FileNotFoundError(errno.ENOENT,'gone')
        self.assertEqual(self.call()['status'],'UNAVAILABLE')
    def test_ascii_and_protocol_errors_unavailable(self):
        self.tables['tcp']=b'header\n\xff';self.tables['netlink']=b'header\n0000 999 42 0 0 0 0 2 0 123\n'
        d=self.call();self.assertFalse(d['complete']);self.assertEqual(d['matches'],[])
    def test_oversized_descriptor_identity_is_not_emitted(self):
        d=s.cpu_probe_socket_diagnostic(self.proc,self.identity,'/fake/42/fd/'+'7'*21,'socket:[123]',time.monotonic()+1)
        self.assertEqual(d['status'],'UNAVAILABLE');self.assertNotIn('fd',d)
    def test_exact_predecessor(self):
        source=Path(s.__file__).read_text();self.assertEqual(hashlib.sha256(without_socket_diagnostic(source).encode()).hexdigest(),PREDECESSOR_SHA256)

if __name__=='__main__':unittest.main()
