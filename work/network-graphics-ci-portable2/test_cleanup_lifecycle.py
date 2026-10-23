"""Synthetic failure lifecycle tests; no native graphics or acceptance claim."""
import os, platform, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
import test_graphics_preflight as baseline
g=baseline.g
REVIEWED_CLEANUP_ADDITIONS = ['        cleanup_children = []\n', "                require(child.result is not None and type(child.result.get('returncode')) is int,\n                        'Owned graphics child lacks wait4 reaping evidence')\n                cleanup_children.append({'pid': child.pid, 'reaped': True,\n                                         'returncode': child.result['returncode']})\n", "        result['cleanup'] = {'collector_pid': os.getpid(), 'expected_children': len(children),\n                             'children': cleanup_children,\n                             'all_reaped': not cleanup_errors and len(cleanup_children) == len(children)}\n"]

def normalize_cleanup_reporting(source):
    for addition in REVIEWED_CLEANUP_ADDITIONS:
        if source.count(addition) != 1:
            raise ValueError('Expected exactly one reviewed cleanup addition')
        source = source.replace(addition, '')
    return source

class FailureCleanup(unittest.TestCase):
    def exercise(self, reaped=True, stop_error=False):
        s=Mock(); child=Mock(pid=12345)
        child.result={'returncode':-15} if reaped else None
        if stop_error: child.stop.side_effect=ValueError('failed stop')
        s.Proc.return_value.identity.side_effect=ValueError('deliberate validation failure')
        observed={}
        lock={'expected_runner':{'ImageOS':'ubuntu24','ImageVersion':'fixture','machine':platform.machine()},
              'display':':193','tools':{'xvfb':'/usr/bin/Xvfb','glxinfo':'/usr/bin/glxinfo'}}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'GITHUB_ACTIONS':'true','CI':'true','ImageOS':'ubuntu24','ImageVersion':'fixture'}),              patch.object(g,'OwnedChild',return_value=child), patch.object(g,'Logs'),              patch.object(g,'write_receipt',side_effect=lambda dest,name,value,*a:observed.update({name:value.copy()})):
            with self.assertRaises(ValueError):g.execute(lock,{},s,Path(d)/'fresh')
        return observed['lifecycle.json'],child
    def test_failed_acceptance_stays_failed_but_child_reaping_explicit(self):
        r,c=self.exercise();self.assertEqual(r['status'],'FAILED');self.assertFalse(r['pair_acceptance'])
        self.assertTrue(r['cleanup']['all_reaped']);self.assertEqual(r['cleanup']['expected_children'],1)
        self.assertEqual(r['cleanup']['children'],[{'pid':12345,'reaped':True,'returncode':-15}]);c.stop.assert_called_once()
    def test_unreaped_child_cannot_claim_cleanup(self):
        r,_=self.exercise(False);self.assertEqual(r['status'],'CLEANUP_FAILED');self.assertFalse(r['cleanup']['all_reaped'])
        self.assertEqual(r['cleanup']['children'],[])
    def test_stop_exception_cannot_claim_cleanup(self):
        r,_=self.exercise(stop_error=True);self.assertEqual(r['status'],'CLEANUP_FAILED');self.assertFalse(r['cleanup']['all_reaped'])
    def test_normalizer_rejects_missing_or_mutated_cleanup_proof(self):
        source=(Path(__file__).parent/'graphics_preflight.py').read_text()
        for addition in REVIEWED_CLEANUP_ADDITIONS:
            with self.assertRaises(ValueError):normalize_cleanup_reporting(source.replace(addition,''))
