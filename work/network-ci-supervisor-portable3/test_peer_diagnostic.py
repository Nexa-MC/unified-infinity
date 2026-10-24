"""Synthetic socket fixtures plus one real owned child's stat/FD census.

No sockets, ptrace, Java/game, CI or network actions. Real process observations
are not real TCP lifecycle or socket ownership proof; tables remain synthetic.
"""
import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import supervisor as s
from peer_diagnostic_preservation import without_failed_peer_diagnostic, PREDECESSOR_SHA256

ERROR='Expected matching client-owned established loopback peer'
PORT=25631
SERVER='0100007F:641F'
CLIENT='0100007F:C001'
SERVER_ID={'pid':101}
CLIENT_ID={'pid':202}
REAL_POPEN=subprocess.Popen

def row(local,remote,inode,state='01'):
    return f'0: {local} {remote} {state} 0:0 0:0 0 0 0 {inode}\n'

def sample(state='01',copies=1,unrelated=''):
    tables=dict.fromkeys(s.TABLES,'header\n')
    tables['tcp']+=row(SERVER,'00000000:0000','42','0A')+row(SERVER,CLIENT,'43')
    tables['tcp']+=row(CLIENT,SERVER,'44',state)*copies+unrelated
    return tables

def connection():
    return dict(protocol='tcp',state='01',local=SERVER,remote=CLIENT,inode='43',role='server')

def predecessor():
    module=ModuleType('unchanged_predecessor');module.__file__=s.__file__
    exec(compile(without_failed_peer_diagnostic(Path(s.__file__).read_text()),s.__file__,'exec'),module.__dict__)
    return module

class FailedPeerFixtures(unittest.TestCase):
    def exercise(self,module=s,*,tables=None,server_inodes=None,client_inodes=None,late_inodes=None):
        tables=sample() if tables is None else tables
        server_inodes={'42','43'} if server_inodes is None else server_inodes
        client_inodes={'44'} if client_inodes is None else client_inodes
        trace=[];proc=module.Proc(Path('/synthetic-proc'));calls={'server':0,'client':0}
        def inodes(identity):
            role='server' if identity==SERVER_ID else 'client';calls[role]+=1;trace.append(('inodes',role))
            if late_inodes is not None and calls[role]>1:return late_inodes[role]
            return set(server_inodes if role=='server' else client_inodes)
        def read(path,limit):
            trace.append(('table',path.name,limit));value=tables[path.name]
            if isinstance(value,BaseException):raise value
            return value.encode('ascii')
        with ExitStack() as stack:
            stack.enter_context(patch.object(proc,'inodes',side_effect=inodes))
            stack.enter_context(patch.object(proc,'same',side_effect=lambda identity:trace.append(('same',identity['pid']))))
            stack.enter_context(patch.object(module,'read_bounded',side_effect=read))
            stack.enter_context(patch.object(module.os,'readlink',side_effect=AssertionError('No new FD reads')))
            stack.enter_context(patch.object(module.time,'monotonic',side_effect=AssertionError('No diagnostic deadlines')))
            try:return proc.sockets(SERVER_ID,PORT,CLIENT_ID),None,trace
            except Exception as error:return None,error,trace
    def reject(self,**kwargs):
        result,error,trace=self.exercise(**kwargs)
        self.assertIsNone(result);self.assertIs(type(error),ValueError);self.assertEqual(str(error),ERROR)
        self.assertEqual(trace,[('inodes','server'),('inodes','client')]+[('table',p,2*s.MIB) for p in s.TABLES])
        d=error.peer_sample_diagnostic
        for key in ('admission_evidence','identity_verified','atomic_observation'):self.assertFalse(d[key])
        return d,error
    def test_healthy_path_exactly_matches_predecessor_and_skips_diagnostic(self):
        expected=self.exercise(predecessor())
        with patch.object(s,'failed_peer_sample_diagnostic',side_effect=AssertionError('Not failure-only')) as diagnostic:
            actual=self.exercise()
        diagnostic.assert_not_called();self.assertEqual(actual,expected);self.assertTrue(actual[0]['connected'])
        self.assertIsNone(actual[1]);self.assertNotIn('peer_sample_diagnostic',actual[0])
    def test_missing_client_fd_retains_reverse_row_with_neither_membership(self):
        d,_=self.reject(client_inodes=set())
        self.assertEqual(d['matching_client_established_rows'],0)
        self.assertEqual(d['reverse_candidates'],[dict(protocol='tcp',state_code='01',fd_membership='NEITHER',relation='EXACT_REVERSE')])
        self.assertTrue(d['scan_complete'])
    def test_missing_table_row_is_not_clean_disconnect_claim(self):
        d,_=self.reject(tables=sample(copies=0))
        self.assertEqual(d['reverse_candidates'],[]);self.assertEqual(d['reverse_rows_seen'],0)
        self.assertFalse(d['reverse_row_count_is_lower_bound']);self.assertNotIn('disconnect',json.dumps(d).lower())
    def test_fin_wait1_retained_without_admitting_or_explaining_disconnect(self):
        d,_=self.reject(tables=sample(state='04'))
        self.assertEqual(d['matching_client_established_rows'],0);self.assertEqual(d['reverse_candidates'][0]['state_code'],'04')
        self.assertEqual(d['reverse_candidates'][0]['fd_membership'],'CLIENT_ONLY');self.assertNotIn('disconnect',json.dumps(d).lower())
    def test_duplicate_peer_rows_stay_duplicate_and_fail_exactly(self):
        d,_=self.reject(tables=sample(copies=2))
        self.assertEqual(d['matching_client_established_rows'],2);self.assertEqual(d['reverse_rows_seen'],2)
        self.assertEqual(len(d['reverse_candidates']),2);self.assertEqual(d['reverse_candidates'][0],d['reverse_candidates'][1])
    def test_each_failure_io_trace_and_error_match_predecessor(self):
        for kwargs in [dict(client_inodes=set()),dict(tables=sample(copies=0)),dict(tables=sample(state='04')),dict(tables=sample(copies=2))]:
            with self.subTest(kwargs=kwargs):
                old,new=self.exercise(predecessor(),**kwargs),self.exercise(**kwargs)
                self.assertIsNone(old[0]);self.assertIsNone(new[0]);self.assertEqual(type(new[1]),type(old[1]))
                self.assertEqual(str(new[1]),str(old[1]));self.assertEqual(new[2],old[2])
    def test_diagnostic_exception_neither_masks_nor_admits(self):
        with patch.object(s,'failed_peer_sample_diagnostic',side_effect=RuntimeError('diagnostic failed')):
            d,error=self.reject(client_inodes=set())
        self.assertEqual(str(error),ERROR);self.assertEqual(d['status'],'UNAVAILABLE')
    def test_original_require_error_object_is_rethrown(self):
        original=ValueError(ERROR);real_require=s.require
        def require(condition,message):
            if not condition and message==ERROR:raise original
            return real_require(condition,message)
        with patch.object(s,'require',side_effect=require):_,error=self.reject(client_inodes=set())
        self.assertIs(error,original)
    def test_unrelated_endpoints_ports_and_inodes_are_not_reported(self):
        secret=row('DEADBEEF:8888','FEEDFACE:9999','987654321')
        d,_=self.reject(tables=sample(unrelated=secret),client_inodes=set());encoded=json.dumps(d)
        for value in ('DEADBEEF','FEEDFACE','987654321',SERVER,CLIENT,'641F','C001','"inode"','"local"','"remote"'):
            self.assertNotIn(value,encoded)
        self.assertEqual(d['reverse_rows_seen'],1)
    def test_missing_table_file_preserves_original_exception_without_diagnostic(self):
        tables=sample();missing=FileNotFoundError('synthetic missing table');tables['udp6']=missing
        _,error,_=self.exercise(tables=tables)
        self.assertIs(error,missing);self.assertFalse(hasattr(error,'peer_sample_diagnostic'))
    def test_other_socket_rejections_are_not_reclassified(self):
        cases=[dict(server_inodes=set()),dict(server_inodes={'42','43','44'}),
               dict(tables={**sample(),'tcp':'header\n'+row(SERVER,'00000000:0000','42','0A')}),
               dict(late_inodes={'server':{'42'},'client':{'44'}})]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                old,new=self.exercise(predecessor(),**kwargs),self.exercise(**kwargs)
                self.assertIsNotNone(new[1]);self.assertEqual(str(new[1]),str(old[1]));self.assertEqual(new[2],old[2])
                self.assertFalse(hasattr(new[1],'peer_sample_diagnostic'))

class InMemoryDiagnosticBounds(unittest.TestCase):
    def call(self,tables,server={'42','43'},client={'44'}):
        with patch.object(s,'read_bounded',side_effect=AssertionError('No reads')),patch.object(s.os,'readlink',side_effect=AssertionError('No FD reads')),patch.object(s.time,'monotonic',side_effect=AssertionError('No deadline reads')):
            return s.failed_peer_sample_diagnostic(tables,server,client,connection(),0)
    def test_all_protocols_are_categorical_and_never_admit(self):
        for protocol in s.TABLES:
            with self.subTest(protocol=protocol):
                tables=dict.fromkeys(s.TABLES,'header\n');tables[protocol]+=row(CLIENT,SERVER,'44');d=self.call(tables)
                self.assertEqual(d['reverse_candidates'][0]['protocol'],protocol);self.assertFalse(d['admission_evidence'])
        # IPv4 strings in tcp6/udp6 are classification fixtures, not valid IPv6 table rows.
    def test_fd_membership_has_only_four_categories(self):
        for server,client,expected in [({'44'},set(),'SERVER_ONLY'),(set(),{'44'},'CLIENT_ONLY'),({'44'},{'44'},'BOTH'),(set(),set(),'NEITHER')]:
            with self.subTest(expected=expected):
                d=self.call(sample(),server,client);self.assertEqual(d['reverse_candidates'][0]['fd_membership'],expected)
                self.assertFalse(d['identity_verified'])
    def test_candidate_cap_preserves_duplicates_and_exact_count(self):
        d=self.call(sample(copies=20));self.assertEqual(len(d['reverse_candidates']),8);self.assertEqual(d['reverse_rows_seen'],20)
        self.assertTrue(d['truncated']);self.assertTrue(d['scan_complete']);self.assertFalse(d['reverse_row_count_is_lower_bound'])
        self.assertLess(len(json.dumps(d)),8192)
    def test_scan_cap_marks_partial_count_not_missing_peer(self):
        tables=sample(copies=0);tables['tcp']+=row('0200007F:C002','0200007F:C003','88')*4095+row(CLIENT,SERVER,'44')
        d=self.call(tables);self.assertEqual(d['rows_scanned'],4096);self.assertEqual(d['reverse_rows_seen'],0)
        self.assertTrue(d['truncated']);self.assertFalse(d['scan_complete']);self.assertTrue(d['reverse_row_count_is_lower_bound'])
        self.assertEqual(d['tables'][0]['status'],'TRUNCATED')
    def test_missing_malformed_tables_have_unavailable_markers(self):
        for value in (None,b'header\n','x'*(2*s.MIB+1),'header\nbroken\n','header\n'+row(CLIENT,SERVER,'44','NOT_A_STATE')):
            with self.subTest(kind=type(value).__name__):
                tables=sample();tables['tcp']=value;d=self.call(tables)
                self.assertEqual(d['tables'][0]['status'],'UNAVAILABLE');self.assertFalse(d['scan_complete'])
                self.assertTrue(d['reverse_row_count_is_lower_bound'])
        tables=sample();del tables['udp6'];self.assertEqual(self.call(tables)['tables'][-1]['status'],'UNAVAILABLE')
    def test_unavailable_fd_sets_connection_or_failure_count(self):
        for server,client,conn,count in [(None,set(),connection(),0),(set(),None,connection(),0),(set(),set(),None,0),(set(),set(),connection(),1)]:
            d=s.failed_peer_sample_diagnostic(sample(),server,client,conn,count)
            self.assertEqual(d['status'],'UNAVAILABLE');self.assertFalse(d['admission_evidence'])

class PairForwarding(unittest.TestCase):
    def pair(self,sockets):
        pair=s.Pair.__new__(s.Pair);pair.proc=SimpleNamespace(sockets=sockets)
        pair.identities={'server':SERVER_ID,'client':CLIENT_ID};pair.spec={'port':PORT}
        pair.report={'observations':[],'passed':False,'status':'INCONCLUSIVE'}
        return pair
    def test_failed_report_is_copied_without_io_and_exact_error_rethrown(self):
        error=ValueError(ERROR);d=s.failed_peer_sample_diagnostic(sample(),{'42','43'},set(),connection(),0)
        error.peer_sample_diagnostic=d;pair=self.pair(Mock(side_effect=error))
        with patch.object(s,'read_bounded',side_effect=AssertionError('No reads')),patch.object(s.os,'readlink',side_effect=AssertionError('No reads')),self.assertRaises(ValueError) as caught:
            pair.observe('during_completed_reload_dwell',connected=True)
        self.assertIs(caught.exception,error);self.assertEqual(pair.report['observations'],[])
        self.assertFalse(pair.report['passed']);self.assertEqual(pair.report['status'],'INCONCLUSIVE')
        saved=pair.report['failed_peer_observation'];self.assertEqual(saved['phase'],'during_completed_reload_dwell')
        self.assertEqual(saved['diagnostic'],d);self.assertIsNot(saved['diagnostic'],d)
        d['reverse_candidates'].clear();self.assertEqual(len(saved['diagnostic']['reverse_candidates']),1)
    def test_copy_failures_do_not_mask_original(self):
        for diagnostic in (object(),{'oversized':'x'*8193},{'nan':float('nan')}):
            error=ValueError(ERROR);error.peer_sample_diagnostic=diagnostic;pair=self.pair(Mock(side_effect=error))
            with self.assertRaises(ValueError) as caught:pair.observe('fixture',True)
            self.assertIs(caught.exception,error);self.assertEqual(pair.report['observations'],[])
            self.assertNotIn('failed_peer_observation',pair.report)
    def test_report_assignment_failure_does_not_mask_original(self):
        class BrokenReport(dict):
            def __setitem__(self,key,value):raise RuntimeError('report failure')
        error=ValueError(ERROR);error.peer_sample_diagnostic={'status':'UNAVAILABLE'}
        pair=self.pair(Mock(side_effect=error));pair.report=BrokenReport(pair.report)
        with self.assertRaises(ValueError) as caught:pair.observe('fixture',True)
        self.assertIs(caught.exception,error)
    def test_unrelated_error_keeps_report_unchanged(self):
        error=ValueError('Other predicate');pair=self.pair(Mock(side_effect=error));original=json.loads(json.dumps(pair.report))
        with self.assertRaises(ValueError) as caught:pair.observe('fixture',True)
        self.assertIs(caught.exception,error);self.assertEqual(pair.report,original)
    def test_healthy_observe_matches_predecessor(self):
        result={'connected':True,'listener':{},'owned':[],'tableSha256':{}}
        pair=self.pair(Mock(return_value=dict(result)));old=self.pair(Mock(return_value=dict(result)))
        self.assertEqual(pair.observe('fixture',True),predecessor().Pair.observe(old,'fixture',True))
        self.assertEqual(pair.report,old.report);self.assertNotIn('failed_peer_observation',pair.report)

class PreservationAndRealProcess(unittest.TestCase):
    def test_exact_predecessor_hash(self):
        original=without_failed_peer_diagnostic(Path(s.__file__).read_text())
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),PREDECESSOR_SHA256)
    def test_reverse_helper_rejects_changed_or_duplicate_delta(self):
        source=Path(s.__file__).read_text()
        for changed in (source+source,source.replace('candidate_limit = 4096, 8','candidate_limit = 4096, 9'),source.replace("raise\n        row['phase']","return\n        row['phase']")):
            with self.assertRaises(ValueError):without_failed_peer_diagnostic(changed)
    def test_dwell_listener_and_identity_code_remain_byte_identical(self):
        source=Path(s.__file__).read_text();old=without_failed_peer_diagnostic(source)
        def nodes(text):
            selected={}
            for node in ast.parse(text).body:
                if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ('CompletedReloadGate','verify_listeners'):
                    selected[node.name]=ast.get_source_segment(text,node)
                if isinstance(node,ast.ClassDef) and node.name in ('Pair','Proc'):
                    for method in node.body:
                        if isinstance(method,ast.FunctionDef) and method.name in ('wait_for_completed_reload','identity','same','inodes'):
                            selected[node.name+'.'+method.name]=ast.get_source_segment(text,method)
            return selected
        self.assertEqual(nodes(source),nodes(old));self.assertEqual(len(nodes(source)),6)
    def test_real_owned_child_stat_and_fd_census_with_synthetic_tables(self):
        # Real stat/FD census only. Server socket inodes and network rows are fixtures.
        child=REAL_POPEN([sys.executable,'-I','-S','-c','import signal,sys; signal.alarm(5); sys.stdout.write("ready\\n"); sys.stdout.flush(); sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            self.assertEqual(child.stdout.readline(),b'ready\n')
            proc=s.Proc();server=proc.identity(os.getpid());client=proc.identity(child.pid)
            real_inodes=proc.inodes;observed=[]
            def census(identity):
                actual=real_inodes(identity);observed.append((identity['pid'],actual))
                return actual|{'42','43'} if identity['pid']==server['pid'] else actual
            real_read=s.read_bounded;tables=sample()
            def read(path,limit):
                return tables[Path(path).name].encode('ascii') if Path(path).parent==Path('/proc/net') else real_read(path,limit)
            with patch.object(proc,'inodes',side_effect=census),patch.object(s,'read_bounded',side_effect=read),self.assertRaisesRegex(ValueError,'^'+ERROR+'$') as caught:
                proc.sockets(server,PORT,client)
            self.assertEqual([pid for pid,_ in observed],[server['pid'],client['pid']]);self.assertEqual(observed[-1][1],set())
            d=caught.exception.peer_sample_diagnostic;self.assertEqual(d['reverse_candidates'][0]['fd_membership'],'NEITHER')
            self.assertFalse(d['identity_verified']);self.assertFalse(d['admission_evidence'])
            child.communicate(input=b'x',timeout=2);self.assertEqual(child.returncode,0)
        finally:
            if child.poll() is None:child.kill()
            child.communicate(timeout=2)

if __name__=='__main__':unittest.main()
