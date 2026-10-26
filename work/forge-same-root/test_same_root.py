"""Data-only wiring tests; never a substitute for next CI javac/Gradle results."""
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
import same_root as s
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'work/network-pair-cold-glue'))
import ffapi_sources,runtime_restore

class Preparation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'consumer'
        ffapi_sources.prepare(REPO,self.root)
    def tearDown(self):self.temp.cleanup()
    def test_runtime_prepare_then_exact_derivative(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No JVM allowed')):
            runtime_restore.prepare(REPO,self.root)
            result=s.prepare(REPO,self.root)
            runtime_restore.verify_preparation(self.root/'work/api1')
        self.assertFalse(result['readyRuntimeBundle']);self.assertEqual(len(result['sourceFilesCopiedWithExactHashes']),809)
        self.assertEqual(result['candidateSourceArchive']['sha256'],s.CORE_SHA)
        for row in result['sourceFilesCopiedWithExactHashes']:
            self.assertEqual(s.sha(self.root/row['path']),row['sha256'])
        # Exact published candidate contains two modified files plus five additions.
        delta=json.loads((s.HERE/'core-delta.json').read_text())['exactDelta']
        for row in delta:
            self.assertEqual(s.sha(self.root/'work/api1/source-workspace/connector-four-loader'/row['path']),row['candidateSha256'])
        self.assertTrue((self.root/'work/forge-same-root/support/owner_completion_validation.py').is_file())
        self.assertTrue((self.root/'source-materialization.json').is_file())
    def test_changed_baseline_rejected_before_derivative(self):
        p=self.root/'work/api1/source-workspace/connector-four-loader/build.gradle.kts'
        p.write_text(p.read_text()+'\n// drift\n')
        with self.assertRaises(Exception):s.prepare(REPO,self.root)
        self.assertFalse((self.root/'work/forge-same-root').exists())
    def test_repeat_cannot_relabel_receipts(self):
        s.prepare(REPO,self.root)
        before=(self.root/'evidence/source-materialization.json').read_bytes()
        with self.assertRaises(Exception):s.prepare(REPO,self.root)
        self.assertEqual((self.root/'evidence/source-materialization.json').read_bytes(),before)
    def test_pipeline_refuses_unapproved_context(self):
        import pipeline
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError):pipeline.execute(REPO,self.root,0,'x')
        self.assertFalse((self.root/'evidence').exists())
if __name__=='__main__':unittest.main()
