"""Synthetic lifecycle proof rejection tests; no native graphics."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest import mock
import graphics_runner as g
class CleanupProof(unittest.TestCase):
    def proof(self):
        return {'schema':1,'status':'FAILED','pair_acceptance':False,'owner_cutoff':{'fixture':1},'cleanup_before_cutoff':True,'cleanup':{'collector_pid':321,'all_reaped':True,'expected_children':2,'children':[{'pid':322,'reaped':True,'returncode':-15},{'pid':323,'reaped':True,'returncode':0}]}}
    def stop(self,r):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'lifecycle.json';p.write_text(json.dumps(r));process=mock.Mock(pid=321);process.poll.return_value=1
            with mock.patch.object(g.os,'close'),mock.patch.object(g.signal,'pidfd_send_signal') as sig:
                result=g.stop({'process':process,'pidfd':41,'log':mock.Mock(),'lifecyclePath':str(p),'ownerCutoff':{'fixture':1}})
                sig.assert_not_called();return result
    def test_failure_cleanup_is_distinct_from_acceptance(self):
        r=self.proof();self.assertEqual(self.stop(r)['status'],'GRAPHICS_COLLECTOR_CLEANED');self.assertEqual(r['status'],'FAILED');self.assertFalse(r['pair_acceptance'])
    def test_missing_false_and_partial_proof_rejected(self):
        cases=[];r=self.proof();r.pop('cleanup');cases.append(r)
        for key,value in [('all_reaped',False),('children',[]),('expected_children',3),('collector_pid',999)]:
            r=self.proof();r['cleanup'][key]=value;cases.append(r)
        for key,value in [('schema',2),('schema',True),('pair_acceptance',True),('cleanup_errors',['failure']),('owner_cutoff',{'fixture':2}),('owner_cutoff',None),('cleanup_before_cutoff',False),('cleanup_before_cutoff',1)]:
            r=self.proof();r[key]=value;cases.append(r)
        for r in cases:
            with self.subTest(r=r),self.assertRaises(ValueError):self.stop(r)
    def test_unreaped_duplicate_and_bad_child_records_rejected(self):
        for key,value in [('reaped',False),('pid',True),('returncode',None),('pid',323)]:
            r=self.proof();r['cleanup']['children'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.stop(r)
    def test_stopped_requires_both_owned_children(self):
        r=self.proof();r['status']='STOPPED_BY_ORCHESTRATOR';r['cleanup']['children']=[];r['cleanup']['expected_children']=0
        with self.assertRaises(ValueError):self.stop(r)
    def test_failed_before_spawn_may_confirm_zero_children(self):
        r=self.proof();r['cleanup']['children']=[];r['cleanup']['expected_children']=0
        self.assertEqual(self.stop(r)['status'],'GRAPHICS_COLLECTOR_CLEANED')
